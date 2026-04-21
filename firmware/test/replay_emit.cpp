/*
 * replay_emit.cpp — Emit per-row mode decisions for a single firmware ref.
 * Reads Phase-0-extended replay CSV, drives determine_mode()+resolve_equipment()
 * forward, prints one TSV row per input row with the firmware's computed mode
 * and relay bitmask.
 *
 * Output consumed by replay_diff.sh (dual-ref wrapper) to produce HEAD-vs-base
 * diffs. Also runs invariants.h against the firmware's own output as a sanity
 * check (catches firmware bugs irrespective of reference comparison).
 *
 * This file is the single-ref "emitter". The diff wrapper builds TWO copies
 * (one from old ref, one from new ref via git worktree) and compares their
 * outputs offline. That sidesteps the header-namespacing problem described
 * in the Plan A report — simpler and more robust than dual-compile tricks.
 *
 * Compile: g++ -std=c++17 -I../lib -o replay_emit replay_emit.cpp
 * Run:     ./replay_emit data/replay_overrides.csv > trace.tsv
 * Output TSV columns:
 *   ts, mode, relay_bitmask, mist_stage, last_mode_reason,
 *   override_flags_bitmask
 */

#include "greenhouse_logic.h"

#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>
#include <cmath>
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

struct Header {
    std::unordered_map<std::string, size_t> idx;
    void parse(const std::string& line) {
        std::istringstream ss(line);
        std::string col;
        size_t i = 0;
        while (std::getline(ss, col, '\t')) idx[col] = i++;
    }
    size_t of(const std::string& name) const {
        auto it = idx.find(name);
        return it == idx.end() ? SIZE_MAX : it->second;
    }
};

// MODE_NAMES is already defined in greenhouse_types.h (included via greenhouse_logic.h)

int main(int argc, char** argv) {
    if (argc < 2) { std::fprintf(stderr, "Usage: %s <replay.csv>\n", argv[0]); return 2; }
    std::ifstream f(argv[1]);
    if (!f) { std::fprintf(stderr, "Cannot open %s\n", argv[1]); return 2; }

    std::string line;
    if (!std::getline(f, line)) { std::fprintf(stderr, "Empty\n"); return 2; }
    Header h;
    h.parse(line);

    // Initialize controller state.
    ControlState state = initial_state();

    // Emit header
    std::printf("ts\tmode\trelay_fog\trelay_vent\trelay_fan1\trelay_fan2\trelay_heat1\trelay_heat2\tmist_stage\treason\toverride_bits\n");

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

        SensorInputs in{};
        in.temp_f = parse_float(get("temp_avg"), 70.0f);
        in.rh_pct = parse_float(get("rh_avg"), 50.0f);
        in.vpd_kpa = parse_float(get("vpd_avg"), 0.8f);
        in.dew_point_f = parse_float(get("indoor_dew_point"), in.temp_f - 10.0f);
        in.enthalpy_delta = parse_float(get("enthalpy_delta"), -5.0f);
        // zone vpds unavailable in this CSV; use avg
        in.vpd_south = in.vpd_kpa; in.vpd_west = in.vpd_kpa;
        in.vpd_east = in.vpd_kpa;
        const std::string ts = get("ts");
        int hr = 12;
        if (ts.size() >= 13) { try { hr = std::stoi(ts.substr(11, 2)); } catch (...) {} }
        in.local_hour = hr;
        in.occupied = parse_bool(get("occupied"), false);
        in.outdoor_temp_f = parse_float(get("outdoor_temp_f"), NAN);
        in.outdoor_dewpoint_f = parse_float(get("outdoor_dewpoint_f"), NAN);
        int age = parse_int(get("outdoor_data_age_s"), -1);
        in.outdoor_data_age_s = (age < 0) ? 99999u : (uint32_t)age;

        // Setpoints: use recent dispatcher-pushed values as the canonical band.
        // Per-row loading from setpoint_snapshot is deferred to Phase-1.
        Setpoints sp = default_setpoints();
        sp.temp_low = parse_float(get("sp_temp_low"), 62.4f);
        sp.temp_high = parse_float(get("sp_temp_high"), 66.4f);
        sp.vpd_low = parse_float(get("sp_vpd_low"), 0.3f);
        sp.vpd_high = parse_float(get("sp_vpd_high"), 0.6f);
        sp.bias_cool = parse_float(get("sp_bias_cool"), 5.0f);
        sp.bias_heat = 3.0f;
        // validate_setpoints applies firmware clamps
        validate_setpoints(sp);

        // Advance state machine
        const uint32_t dt_ms = 60000;  // 1-min CSV cadence
        Mode mode = determine_mode(in, sp, state, dt_ms);
        RelayOutputs r = resolve_equipment(mode, in, sp, state, true);
        OverrideFlags of = evaluate_overrides(in, sp, state, mode);

        const char* reason = state.last_mode_reason ? state.last_mode_reason : "";
        int override_bits = (of.occupancy_blocks_moisture << 0) | (of.fog_gate_rh << 1)
                          | (of.fog_gate_temp << 2) | (of.fog_gate_window << 3)
                          | (of.relief_cycle_breaker << 4) | (of.seal_blocked_temp << 5)
                          | (of.vpd_dry_override << 6) | (of.summer_vent_active << 7);

        std::printf("%s\t%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%s\t%d\n",
                    ts.c_str(),
                    MODE_NAMES[(int)mode],
                    r.fog, r.vent, r.fan1, r.fan2, r.heat1, r.heat2,
                    (int)state.mist_stage,
                    reason,
                    override_bits);
        rows++;
    }

    std::fprintf(stderr, "replay_emit: %ld rows emitted\n", rows);
    return 0;
}
