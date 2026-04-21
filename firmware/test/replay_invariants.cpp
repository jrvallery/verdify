/*
 * replay_invariants.cpp — Phase-0 bulletproof-firmware harness.
 * Reads extended replay CSV and runs the 15 invariants from invariants.h.
 *
 * Sibling to replay_overrides.cpp (which replays evaluate_overrides counts).
 * This file focuses on the invariant suite; the dual-ref old-vs-new mode
 * diff lives in replay_diff.cpp (phase-0 second deliverable).
 *
 * Compile: g++ -std=c++17 -I../lib -o replay_invariants replay_invariants.cpp
 * Run:     ./replay_invariants data/replay_overrides.csv
 *
 * CSV columns (tab-separated, header row required). The extended Phase-0 export
 * script `scripts/export-replay-overrides.sh` produces all of these. Legacy
 * columns (sp_*) remain for compatibility with replay_overrides.cpp.
 *
 *   ts, temp_avg, vpd_avg, rh_avg, outdoor_rh_pct, enthalpy_delta,
 *   outdoor_temp_f, indoor_dew_point, solar_irradiance_w_m2,
 *   outdoor_data_age_s,
 *   sp_temp_high, sp_temp_low, sp_vpd_high, sp_vpd_low, sp_bias_cool,
 *   sp_vpd_hysteresis, sp_watch_dwell_s,
 *   occupied, greenhouse_state, mode_reason,
 *   eq_fog, eq_vent, eq_fan1, eq_fan2, eq_heat1, eq_heat2,
 *   eq_mister_south, eq_mister_west, eq_mister_center
 *
 * Exit code: 0 if all invariants pass, non-zero = count of distinct
 * invariants violated (so CI fails on any breach).
 */

#include "invariants.h"
#include "greenhouse_logic.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>
#include <ctime>

static float parse_float(const std::string& s, float def) {
    if (s.empty() || s == "\\N" || s == "NULL") return def;
    try { return std::stof(s); } catch (...) { return def; }
}

static int parse_int(const std::string& s, int def) {
    if (s.empty() || s == "\\N" || s == "NULL") return def;
    try { return std::stoi(s); } catch (...) { return def; }
}

static bool parse_bool(const std::string& s, bool def) {
    if (s.empty() || s == "\\N" || s == "NULL") return def;
    return s == "t" || s == "true" || s == "1";
}

// Parse ISO-8601 ts like "2026-04-21 10:55:48.223+00" → unix seconds
static uint64_t parse_ts_unix(const std::string& s) {
    if (s.size() < 19) return 0;
    struct tm tm{};
    // Expect "YYYY-MM-DD HH:MM:SS[.fff][tz]"
    if (sscanf(s.c_str(), "%d-%d-%d %d:%d:%d",
               &tm.tm_year, &tm.tm_mon, &tm.tm_mday,
               &tm.tm_hour, &tm.tm_min, &tm.tm_sec) != 6) return 0;
    tm.tm_year -= 1900;
    tm.tm_mon -= 1;
    return (uint64_t)timegm(&tm);
}

// Map column name → index (built from header row)
struct Header {
    std::unordered_map<std::string, size_t> idx;
    void parse(const std::string& line) {
        std::istringstream ss(line);
        std::string col;
        size_t i = 0;
        while (std::getline(ss, col, '\t')) {
            idx[col] = i++;
        }
    }
    size_t of(const std::string& name) const {
        auto it = idx.find(name);
        return it == idx.end() ? SIZE_MAX : it->second;
    }
};

// Per-row failure counter, keyed by invariant id, for summary report.
struct FailureStats {
    std::unordered_map<int, int> counts_by_id;
    std::unordered_map<int, std::string> first_row_by_id;
    int total = 0;
};

static FailureStats g_stats;

static void stats_report(int id, const char* name,
                         const invariants::TraceRow& row, const char* detail) {
    g_stats.counts_by_id[id]++;
    g_stats.total++;
    if (g_stats.first_row_by_id.find(id) == g_stats.first_row_by_id.end()) {
        char msg[256];
        std::snprintf(msg, sizeof(msg),
            "ts=%llu mode=%s reason=%s: %s",
            (unsigned long long)row.ts_unix_s,
            row.greenhouse_state.c_str(),
            row.mode_reason.c_str(),
            detail);
        g_stats.first_row_by_id[id] = msg;
        std::fprintf(stderr, "INVARIANT FAIL #%02d %s (first): %s\n", id, name, msg);
    }
}

int main(int argc, char** argv) {
    if (argc < 2) {
        std::fprintf(stderr, "Usage: %s <replay.csv>\n", argv[0]);
        return 2;
    }
    std::ifstream f(argv[1]);
    if (!f) { std::fprintf(stderr, "Cannot open %s\n", argv[1]); return 2; }

    std::string line;
    if (!std::getline(f, line)) { std::fprintf(stderr, "Empty file\n"); return 2; }
    Header h;
    h.parse(line);

    // Required columns for the invariant suite
    const char* required[] = {
        "ts", "temp_avg", "vpd_avg", "rh_avg", "occupied",
        "greenhouse_state", "mode_reason",
        "eq_fog", "eq_vent", "eq_fan1", "eq_fan2",
        "eq_heat1", "eq_heat2",
        "eq_mister_south", "eq_mister_west", "eq_mister_center"
    };
    for (auto name : required) {
        if (h.of(name) == SIZE_MAX) {
            std::fprintf(stderr, "Missing required column: %s\n", name);
            std::fprintf(stderr, "Run scripts/export-replay-overrides.sh to regenerate CSV.\n");
            return 2;
        }
    }

    // Canonical setpoints we'll apply uniformly. In a future revision, pull
    // from setpoint_snapshot as-of-ts, but for Phase-0 invariant check the
    // current band is representative.
    invariants::Runner runner;
    long rows = 0;
    while (std::getline(f, line)) {
        std::vector<std::string> cols;
        {
            std::istringstream ss(line);
            std::string tok;
            while (std::getline(ss, tok, '\t')) cols.push_back(std::move(tok));
        }
        auto get = [&](const std::string& name, const std::string& def = "") -> std::string {
            size_t i = h.of(name);
            return (i == SIZE_MAX || i >= cols.size()) ? def : cols[i];
        };

        invariants::TraceRow r{};
        std::string ts = get("ts");
        r.ts_unix_s = parse_ts_unix(ts);
        if (ts.size() >= 13) {
            try { r.local_hour = std::stoi(ts.substr(11, 2)); } catch (...) { r.local_hour = 12; }
        }

        r.temp_f  = parse_float(get("temp_avg"), 70.0f);
        r.rh_pct  = parse_float(get("rh_avg"), 50.0f);
        r.vpd_kpa = parse_float(get("vpd_avg"), 0.8f);
        r.dew_point_f = parse_float(get("indoor_dew_point"), r.temp_f - 10.0f);

        r.outdoor_temp_f     = parse_float(get("outdoor_temp_f"), NAN);
        r.outdoor_rh_pct     = parse_float(get("outdoor_rh_pct"), NAN);
        r.outdoor_dewpoint_f = parse_float(get("outdoor_dewpoint_f"), NAN);
        r.outdoor_data_age_s = parse_int  (get("outdoor_data_age_s"), -1);
        r.solar_w_m2         = parse_float(get("solar_irradiance_w_m2"), 0.0f);

        // Canonical setpoints — the band the firmware is currently configured with.
        // Derived from recent setpoint_snapshot. Phase-1 will load these per-row
        // from a time-aligned setpoints CSV for higher fidelity.
        r.temp_low  = parse_float(get("sp_temp_low"),  62.4f);
        r.temp_high = parse_float(get("sp_temp_high"), 66.4f);
        r.vpd_low   = parse_float(get("sp_vpd_low"),   0.3f);
        r.vpd_high  = parse_float(get("sp_vpd_high"),  0.6f);
        r.temp_hysteresis = parse_float(get("sp_vpd_hysteresis"), 1.5f); /* legacy name reused */
        r.vpd_hysteresis  = parse_float(get("sp_vpd_hysteresis"), 0.3f);
        r.vpd_max_safe    = 2.5f;
        r.vpd_min_safe    = 0.3f;
        r.safety_max      = 100.0f;
        r.safety_min      = 35.0f;
        r.bias_heat       = 3.0f;
        r.bias_cool       = parse_float(get("sp_bias_cool"), 5.0f);
        r.sealed_max_ms   = 600000u;       // 10 min
        r.relief_duration_ms = 90000u;     // 90 s
        r.outdoor_staleness_max_s = 600u;  // post-sprint-15.1

        r.greenhouse_state = get("greenhouse_state");
        r.mode_reason      = get("mode_reason");

        r.eq_fog  = parse_int(get("eq_fog"),  0);
        r.eq_vent = parse_int(get("eq_vent"), 0);
        r.eq_fan1 = parse_int(get("eq_fan1"), 0);
        r.eq_fan2 = parse_int(get("eq_fan2"), 0);
        r.eq_heat1 = parse_int(get("eq_heat1"), 0);
        r.eq_heat2 = parse_int(get("eq_heat2"), 0);
        r.eq_mister_south  = parse_int(get("eq_mister_south"),  0);
        r.eq_mister_west   = parse_int(get("eq_mister_west"),   0);
        r.eq_mister_center = parse_int(get("eq_mister_center"), 0);

        r.occupied = parse_bool(get("occupied"), false);

        runner.run(r, stats_report);
        rows++;
    }

    // Summary
    std::printf("\n═══ Invariant summary — %ld rows ═══\n", rows);
    if (g_stats.counts_by_id.empty()) {
        std::printf("  ✓ All 15 invariants passed.\n");
        return 0;
    }
    std::printf("  %d total violations across %zu distinct invariants.\n",
                g_stats.total, g_stats.counts_by_id.size());
    for (auto& [id, count] : g_stats.counts_by_id) {
        std::printf("    invariant #%02d: %d violations\n", id, count);
        auto it = g_stats.first_row_by_id.find(id);
        if (it != g_stats.first_row_by_id.end()) {
            std::printf("      first: %s\n", it->second.c_str());
        }
    }
    return (int)g_stats.counts_by_id.size();
}
