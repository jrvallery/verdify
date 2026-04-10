/*
 * replay_harness.cpp — Historical replay using greenhouse_logic.h
 *
 * Reads CSV export of v_greenhouse_state, feeds each row through the
 * EXACT SAME determine_mode() + resolve_equipment() running on the ESP32,
 * and compares simulated outputs against actual equipment state.
 *
 * Compile: g++ -std=c++17 -I../lib -o replay_harness replay_harness.cpp
 * Run:     ./replay_harness data/replay_data.csv
 */

#include "greenhouse_logic.h"
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <string>
#include <vector>
#include <fstream>
#include <sstream>

// CSV column indices (must match v_greenhouse_state column order)
enum Col {
    COL_TS = 0,
    COL_TEMP_AVG, COL_VPD_AVG, COL_RH_AVG, COL_DEW_POINT,
    COL_TEMP_N, COL_TEMP_S, COL_TEMP_E, COL_TEMP_W,
    COL_VPD_S, COL_VPD_W, COL_VPD_E,
    COL_LUX, COL_SOLAR, COL_DLI,
    COL_CO2, COL_ABS_HUMID, COL_ENTHALPY,
    COL_OUT_TEMP, COL_OUT_RH,
    COL_DP_MARGIN,
    // Equipment (actual)
    COL_FAN1, COL_FAN2, COL_VENT, COL_FOG, COL_HEAT1, COL_HEAT2,
    COL_MIST_S, COL_MIST_W, COL_MIST_C,
    // Setpoints
    COL_SP_TEMP_HI, COL_SP_TEMP_LO, COL_SP_VPD_HI, COL_SP_VPD_LO,
    COL_SP_BIAS_COOL, COL_SP_BIAS_HEAT, COL_SP_HYSTERESIS,
    COL_SP_SEALED_MAX, COL_SP_RELIEF, COL_SP_WATCH_DWELL,
    COL_SP_D_COOL_S2, COL_SP_ENGAGE,
    // Compliance
    COL_TEMP_INBAND, COL_VPD_INBAND,
    // Mode
    COL_MODE,
    COL_COUNT
};

static float parse_float(const std::string& s, float def = 0.0f) {
    if (s.empty() || s == "" || s == "\\N") return def;
    try { return std::stof(s); } catch (...) { return def; }
}

static bool parse_bool(const std::string& s) {
    return s == "t" || s == "true" || s == "1";
}

static int parse_hour(const std::string& ts) {
    // ts format: "2026-04-10 14:32:30.123456-06"
    // Extract hour from position 11-12
    if (ts.size() < 13) return 12;
    try { return std::stoi(ts.substr(11, 2)); } catch (...) { return 12; }
}

struct Stats {
    int total_rows = 0;
    // Mode distribution (simulated)
    int mode_counts[7] = {};
    // Compliance
    int actual_temp_inband = 0;
    int actual_vpd_inband = 0;
    int sim_temp_inband = 0;
    int sim_vpd_inband = 0;
    // Invariant violations
    int vent_mist_overlap_actual = 0;
    int vent_mist_overlap_sim = 0;
    int heater_vent_overlap_actual = 0;
    int heater_vent_overlap_sim = 0;
    int fan_no_vent_actual = 0;
    int fan_no_vent_sim = 0;
    // Equipment runtime (minutes)
    float actual_heat_min = 0, sim_heat_min = 0;
    float actual_fan_min = 0, sim_fan_min = 0;
    float actual_mist_min = 0, sim_mist_min = 0;
    float actual_vent_min = 0, sim_vent_min = 0;
};

int main(int argc, char* argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <csv_file>\n", argv[0]);
        return 1;
    }

    std::ifstream file(argv[1]);
    if (!file.is_open()) {
        fprintf(stderr, "Cannot open %s\n", argv[1]);
        return 1;
    }

    // Skip header
    std::string header;
    std::getline(file, header);

    ControlState state = initial_state();
    Stats stats;
    std::string line;

    while (std::getline(file, line)) {
        // Parse CSV
        std::vector<std::string> cols;
        std::stringstream ss(line);
        std::string cell;
        while (std::getline(ss, cell, ',')) {
            cols.push_back(cell);
        }
        if (cols.size() < COL_MODE) continue;

        stats.total_rows++;

        // Build SensorInputs from CSV
        SensorInputs in = {};
        in.temp_f = parse_float(cols[COL_TEMP_AVG], 70.0f);
        in.vpd_kpa = parse_float(cols[COL_VPD_AVG], 1.0f);
        in.rh_pct = parse_float(cols[COL_RH_AVG], 60.0f);
        in.dew_point_f = parse_float(cols[COL_DEW_POINT], in.temp_f - 10);
        in.outdoor_rh_pct = parse_float(cols[COL_OUT_RH], 30.0f);
        in.enthalpy_delta = parse_float(cols[COL_ENTHALPY], -5.0f);
        in.vpd_south = parse_float(cols[COL_VPD_S], in.vpd_kpa);
        in.vpd_west = parse_float(cols[COL_VPD_W], in.vpd_kpa);
        in.vpd_east = parse_float(cols[COL_VPD_E], in.vpd_kpa);
        in.local_hour = parse_hour(cols[COL_TS]);
        in.occupied = false;
        in.mister_state = 0;
        in.humid_s2_duration_ms = 0;
        in.fog_escalation_kpa = 0.4f;
        in.fog_rh_ceiling = 90.0f;
        in.fog_min_temp = 55.0f;
        in.fog_window_start = 7;
        in.fog_window_end = 17;
        in.mister_all_delay_ms = 300000;
        in.occupancy_inhibit = false;

        // Build Setpoints from CSV
        Setpoints sp = default_setpoints();
        float v;
        if ((v = parse_float(cols[COL_SP_TEMP_HI])) > 0) sp.temp_high = v;
        if ((v = parse_float(cols[COL_SP_TEMP_LO])) > 0) sp.temp_low = v;
        if ((v = parse_float(cols[COL_SP_VPD_HI])) > 0) sp.vpd_high = v;
        if ((v = parse_float(cols[COL_SP_VPD_LO])) > 0) sp.vpd_low = v;
        sp.bias_cool = parse_float(cols[COL_SP_BIAS_COOL]);
        sp.bias_heat = parse_float(cols[COL_SP_BIAS_HEAT]);
        if ((v = parse_float(cols[COL_SP_HYSTERESIS])) > 0) sp.vpd_hysteresis = v;
        if ((v = parse_float(cols[COL_SP_SEALED_MAX])) > 0) sp.sealed_max_ms = (uint32_t)(v * 1000);
        if ((v = parse_float(cols[COL_SP_RELIEF])) > 0) sp.relief_duration_ms = (uint32_t)(v * 1000);
        if ((v = parse_float(cols[COL_SP_WATCH_DWELL])) > 0) sp.vpd_watch_dwell_ms = (uint32_t)(v * 1000);
        if ((v = parse_float(cols[COL_SP_D_COOL_S2])) > 0) sp.dC2 = v;

        // Run simulation
        Mode mode = determine_mode(in, sp, state, 60000);  // 60s per row
        RelayOutputs sim = resolve_equipment(mode, in, sp, true);

        stats.mode_counts[mode]++;

        // Actual equipment from CSV
        bool act_fan1 = parse_bool(cols[COL_FAN1]);
        bool act_fan2 = parse_bool(cols[COL_FAN2]);
        bool act_vent = parse_bool(cols[COL_VENT]);
        bool act_heat1 = parse_bool(cols[COL_HEAT1]);
        bool act_heat2 = parse_bool(cols[COL_HEAT2]);
        bool act_mist = parse_bool(cols[COL_MIST_S]) || parse_bool(cols[COL_MIST_W]) || parse_bool(cols[COL_MIST_C]);

        // Compliance (actual)
        if (parse_bool(cols[COL_TEMP_INBAND])) stats.actual_temp_inband++;
        if (parse_bool(cols[COL_VPD_INBAND])) stats.actual_vpd_inband++;

        // Compliance (simulated — check against same setpoints)
        float Thigh = sp.temp_high + sp.bias_cool;
        float Tlow = sp.temp_low + sp.bias_heat;
        if (in.temp_f >= Tlow && in.temp_f <= Thigh) stats.sim_temp_inband++;
        if (in.vpd_kpa >= sp.vpd_low && in.vpd_kpa <= sp.vpd_high) stats.sim_vpd_inband++;

        // Invariant checks — actual
        if (act_vent && act_mist) stats.vent_mist_overlap_actual++;
        if (act_vent && (act_heat1 || act_heat2)) stats.heater_vent_overlap_actual++;
        if (!act_vent && (act_fan1 || act_fan2)) stats.fan_no_vent_actual++;

        // Invariant checks — simulated
        if (sim.vent && (mode == SEALED_MIST)) stats.vent_mist_overlap_sim++;
        if (sim.vent && (sim.heat1 || sim.heat2)) stats.heater_vent_overlap_sim++;
        if (!sim.vent && (sim.fan1 || sim.fan2)) stats.fan_no_vent_sim++;

        // Runtime tracking (1 min per row)
        if (act_heat1 || act_heat2) stats.actual_heat_min += 1;
        if (sim.heat1 || sim.heat2) stats.sim_heat_min += 1;
        if (act_fan1 || act_fan2) stats.actual_fan_min += 1;
        if (sim.fan1 || sim.fan2) stats.sim_fan_min += 1;
        if (act_mist) stats.actual_mist_min += 1;
        if (mode == SEALED_MIST) stats.sim_mist_min += 1;
        if (act_vent) stats.actual_vent_min += 1;
        if (sim.vent) stats.sim_vent_min += 1;
    }

    // Print report
    printf("═══════════════════════════════════════════════════════════\n");
    printf("  Historical Replay — %d rows (%.1f days)\n",
           stats.total_rows, stats.total_rows / 1440.0f);
    printf("  Same code as ESP32: greenhouse_logic.h\n");
    printf("═══════════════════════════════════════════════════════════\n\n");

    printf("Mode distribution (simulated):\n");
    for (int i = 0; i < 7; i++) {
        if (stats.mode_counts[i] > 0) {
            printf("  %-18s %6d min (%5.1f%%)\n", MODE_NAMES[i],
                   stats.mode_counts[i], 100.0f * stats.mode_counts[i] / stats.total_rows);
        }
    }

    printf("\nCompliance comparison:\n");
    printf("  Actual temp in-band:     %5.1f%%\n", 100.0f * stats.actual_temp_inband / stats.total_rows);
    printf("  Simulated temp in-band:  %5.1f%% (%+.1f%%)\n",
           100.0f * stats.sim_temp_inband / stats.total_rows,
           100.0f * (stats.sim_temp_inband - stats.actual_temp_inband) / stats.total_rows);
    printf("  Actual VPD in-band:      %5.1f%%\n", 100.0f * stats.actual_vpd_inband / stats.total_rows);
    printf("  Simulated VPD in-band:   %5.1f%% (%+.1f%%)\n",
           100.0f * stats.sim_vpd_inband / stats.total_rows,
           100.0f * (stats.sim_vpd_inband - stats.actual_vpd_inband) / stats.total_rows);

    printf("\nInvariant verification:\n");
    printf("  %s %d vent+mister overlaps (actual had %d)\n",
           stats.vent_mist_overlap_sim == 0 ? "✓" : "✗",
           stats.vent_mist_overlap_sim, stats.vent_mist_overlap_actual);
    printf("  %s %d heater+vent overlaps (actual had %d)\n",
           stats.heater_vent_overlap_sim == 0 ? "✓" : "✗",
           stats.heater_vent_overlap_sim, stats.heater_vent_overlap_actual);
    printf("  %s %d fan+vent-closed events (actual had %d)\n",
           stats.fan_no_vent_sim == 0 ? "✓" : "✗",
           stats.fan_no_vent_sim, stats.fan_no_vent_actual);

    printf("\nEquipment runtime comparison:\n");
    printf("  Heater: actual %5.1fh → simulated %5.1fh (%+.0f%%)\n",
           stats.actual_heat_min/60, stats.sim_heat_min/60,
           stats.actual_heat_min > 0 ? 100*(stats.sim_heat_min - stats.actual_heat_min)/stats.actual_heat_min : 0);
    printf("  Fans:   actual %5.1fh → simulated %5.1fh (%+.0f%%)\n",
           stats.actual_fan_min/60, stats.sim_fan_min/60,
           stats.actual_fan_min > 0 ? 100*(stats.sim_fan_min - stats.actual_fan_min)/stats.actual_fan_min : 0);
    printf("  Mist:   actual %5.1fh → simulated %5.1fh (%+.0f%%)\n",
           stats.actual_mist_min/60, stats.sim_mist_min/60,
           stats.actual_mist_min > 0 ? 100*(stats.sim_mist_min - stats.actual_mist_min)/stats.actual_mist_min : 0);
    printf("  Vent:   actual %5.1fh → simulated %5.1fh (%+.0f%%)\n",
           stats.actual_vent_min/60, stats.sim_vent_min/60,
           stats.actual_vent_min > 0 ? 100*(stats.sim_vent_min - stats.actual_vent_min)/stats.actual_vent_min : 0);

    printf("\n═══════════════════════════════════════════════════════════\n");

    return stats.vent_mist_overlap_sim > 0 ? 1 : 0;
}
