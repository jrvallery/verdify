#pragma once
/*
 * greenhouse_types.h — Shared types for greenhouse climate controller.
 * Used by both ESP32 firmware (via ESPHome) and native x86 tests.
 * NO ESPHome dependencies. Pure C++.
 *
 * All floats are single-precision by design — ESP32 has hardware FPU
 * for float but emulates double. Do not use double.
 */

#include <cstdint>
#include <cmath>
#include <algorithm>

// ── Greenhouse operating modes (mutually exclusive, priority-ordered) ──
enum Mode {
    SENSOR_FAULT,     // NaN/invalid sensor readings — safe default posture
    SAFETY_COOL,      // temp >= safety_max → vent open, both fans, fog allowed
    SAFETY_HEAT,      // temp <= safety_min → vent closed, both heaters
    SEALED_MIST,      // VPD > band ceiling → vent closed, fans off, misters pulsing
    THERMAL_RELIEF,   // sealed too long → mandatory vent burst for heat dump
    VENTILATE,        // temp > temp_high + bias_cool → vent open, fans on
    DEHUM_VENT,       // VPD < vpd_low → vent open for humidity dump
    IDLE              // everything in band → vent closed, no active equipment
};

static_assert(IDLE == 7, "Mode enum ordering changed — update MODE_NAMES and switch statements");

// Mister sub-stages within SEALED_MIST (owned by this code, not ESPHome)
enum MistStage { MIST_WATCH, MIST_S1, MIST_S2, MIST_FOG };

// Mode name lookup (same order as enum)
// C1 FIX: inline constexpr prevents per-TU duplication
inline constexpr const char* MODE_NAMES[] = {
    "SENSOR_FAULT", "SAFETY_COOL", "SAFETY_HEAT", "SEALED_MIST",
    "THERMAL_RELIEF", "VENTILATE", "DEHUM_VENT", "IDLE"
};
inline constexpr const char* MIST_NAMES[] = {"WATCH", "S1", "S2", "FOG"};

// ── Sensor inputs (ONLY actual sensor readings, no config) ──
struct SensorInputs {
    float temp_f;           // indoor average temperature (°F)
    float vpd_kpa;          // indoor average VPD (kPa)
    float rh_pct;           // indoor average RH (%)
    float dew_point_f;      // indoor dew point (°F)
    float outdoor_rh_pct;   // outdoor RH (%)
    float enthalpy_delta;   // outdoor - indoor enthalpy (kJ/kg)
    float vpd_south;        // zone VPD sensors (NaN-tolerant — checked where used)
    float vpd_west;
    float vpd_east;
    int   local_hour;       // 0-23, from SNTP
    bool  occupied;         // greenhouse occupancy (from Sentinel)
};

// ── Setpoints (band + planner tunables + firmware config) ──
struct Setpoints {
    // Band (from crop profiles, updated every 5 min by dispatcher)
    float temp_high;            // band ceiling (°F)
    float temp_low;             // band floor (°F)
    float vpd_high;             // VPD ceiling (kPa)
    float vpd_low;              // VPD floor (kPa)
    // Planner tunables
    float bias_cool;            // shift cooling threshold
    float bias_heat;            // shift heating threshold
    float vpd_hysteresis;       // exit hysteresis for sealed mist + dehum (kPa)
    float temp_hysteresis;      // exit hysteresis for VENTILATE (°F)
    float heat_hysteresis;      // entry offset for gas heater below temp_low (°F)
    float dH2;                  // heat stage 2 delta: electric pre-heat zone above temp_low
    float dC2;                  // cool stage 2 delta: aggressive cooling trigger above temp_high
    // Safety limits
    float safety_max;           // absolute temp ceiling (°F)
    float safety_min;           // absolute temp floor (°F)
    float vpd_max_safe;         // absolute VPD ceiling (kPa)
    float vpd_min_safe;         // absolute VPD floor (kPa)
    // Timing
    uint32_t sealed_max_ms;     // max sealed time before thermal relief
    uint32_t relief_duration_ms;// thermal relief vent-open duration
    uint32_t vpd_watch_dwell_ms;// observation dwell before sealing
    uint32_t mist_s2_delay_ms;  // time in S1 before escalating to S2
    // Fog configuration
    float fog_escalation_kpa;   // VPD above band ceiling that triggers fog
    float fog_rh_ceiling;       // firmware safety gate (%)
    float fog_min_temp;         // firmware safety gate (°F)
    int   fog_window_start;     // firmware safety gate (hour)
    int   fog_window_end;       // firmware safety gate (hour)
    // Dehumidification
    float dehum_aggressive_kpa; // VPD threshold for dual-fan dehum (default 0.6)
    // Occupancy
    bool  occupancy_inhibit;    // occupancy blocks fog/mist
    // Economiser
    bool  econ_block;           // economiser blocks venting
};

// C2 FIX: Sentinel for corruption detection
static constexpr uint32_t STATE_SENTINEL = 0xBEEF0042;

// ── Persistent control state (survives across 5s evaluation cycles) ──
struct ControlState {
    uint32_t sentinel;          // C2: must equal STATE_SENTINEL or state is corrupt
    Mode mode;                  // current mode (written at end of determine_mode)
    Mode mode_prev;             // previous cycle's mode (read at top of determine_mode)
    MistStage mist_stage;       // mister escalation stage (owned by this code)
    uint32_t sealed_timer_ms;   // time spent in current sealed period
    uint32_t relief_timer_ms;   // time spent in current relief period
    uint32_t vpd_watch_timer_ms;// dwell timer before sealing
    uint32_t mist_stage_timer_ms;// time in current mist stage (for escalation)
};

// ── Relay outputs (computed from mode, applied to hardware) ──
struct RelayOutputs {
    bool heat1;
    bool heat2;
    bool fan1;
    bool fan2;
    bool fog;
    bool vent;
};

// ── Saturating addition for timers (C5 FIX) ──
inline uint32_t sat_add(uint32_t a, uint32_t b) {
    uint32_t result = a + b;
    return (result < a) ? UINT32_MAX : result;  // overflow → cap at max
}

// Q2 FIX: Named constant for econ heat margin
static constexpr float ECON_HEAT_MARGIN_F = 5.0f;

// ── Defaults ──
inline Setpoints default_setpoints() {
    return {
        .temp_high = 82.0f, .temp_low = 58.0f,
        .vpd_high = 1.2f, .vpd_low = 0.5f,
        .bias_cool = 0.0f, .bias_heat = 0.0f,
        .vpd_hysteresis = 0.3f, .temp_hysteresis = 1.5f, .heat_hysteresis = 1.0f,
        .dH2 = 5.0f, .dC2 = 3.0f,
        .safety_max = 95.0f, .safety_min = 45.0f,
        .vpd_max_safe = 3.0f, .vpd_min_safe = 0.3f,
        .sealed_max_ms = 600000, .relief_duration_ms = 90000,
        .vpd_watch_dwell_ms = 60000, .mist_s2_delay_ms = 300000,
        .fog_escalation_kpa = 0.4f, .fog_rh_ceiling = 90.0f,
        .fog_min_temp = 55.0f, .fog_window_start = 7, .fog_window_end = 17,
        .dehum_aggressive_kpa = 0.6f,
        .occupancy_inhibit = false, .econ_block = false
    };
}

// R7 FIX: Clamp setpoints to sane ranges (call before determine_mode)
inline void validate_setpoints(Setpoints& sp) {
    sp.temp_high = std::max(50.0f, std::min(110.0f, sp.temp_high));
    sp.temp_low = std::max(30.0f, std::min(90.0f, sp.temp_low));
    if (sp.temp_low >= sp.temp_high) sp.temp_low = sp.temp_high - 5.0f;
    sp.vpd_high = std::max(0.3f, std::min(5.0f, sp.vpd_high));
    sp.vpd_low = std::max(0.1f, std::min(sp.vpd_high - 0.1f, sp.vpd_low));
    sp.vpd_hysteresis = std::max(0.05f, std::min(sp.vpd_high * 0.5f, sp.vpd_hysteresis));
    sp.temp_hysteresis = std::max(0.5f, std::min(5.0f, sp.temp_hysteresis));
    sp.heat_hysteresis = std::max(0.0f, std::min(3.0f, sp.heat_hysteresis));
    sp.safety_max = std::max(sp.temp_high + 5.0f, std::min(120.0f, sp.safety_max));
    sp.safety_min = std::max(30.0f, std::min(sp.temp_low - 5.0f, sp.safety_min));
    sp.sealed_max_ms = std::max(uint32_t(60000), std::min(uint32_t(1800000), sp.sealed_max_ms));
    sp.relief_duration_ms = std::max(uint32_t(15000), std::min(uint32_t(600000), sp.relief_duration_ms));
}

inline ControlState initial_state() {
    return {
        .sentinel = STATE_SENTINEL,
        .mode = IDLE, .mode_prev = IDLE,
        .mist_stage = MIST_WATCH,
        .sealed_timer_ms = 0, .relief_timer_ms = 0,
        .vpd_watch_timer_ms = 0, .mist_stage_timer_ms = 0
    };
}
