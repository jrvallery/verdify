#pragma once
/*
 * greenhouse_types.h — Shared types for greenhouse climate controller.
 * Used by both ESP32 firmware (via ESPHome) and native x86 tests.
 * NO ESPHome dependencies. Pure C++.
 */

#include <cstdint>
#include <cmath>

// ── Greenhouse operating modes (mutually exclusive, priority-ordered) ──
enum Mode {
    SAFETY_COOL,      // temp >= safety_max → vent open, both fans, fog allowed
    SAFETY_HEAT,      // temp <= safety_min → vent closed, both heaters
    SEALED_MIST,      // VPD > band ceiling → vent closed, fans off, misters pulsing
    THERMAL_RELIEF,   // sealed too long → mandatory vent burst for heat dump
    VENTILATE,        // temp > temp_high + bias_cool → vent open, fans on
    DEHUM_VENT,       // VPD < vpd_low → vent open for humidity dump
    IDLE              // everything in band → vent closed, no active equipment
};

// Mister sub-states within SEALED_MIST
enum MistStage { MIST_WATCH, MIST_S1, MIST_S2, MIST_FOG };

// Mode name lookup (same order as enum)
static const char* MODE_NAMES[] = {
    "SAFETY_COOL", "SAFETY_HEAT", "SEALED_MIST",
    "THERMAL_RELIEF", "VENTILATE", "DEHUM_VENT", "IDLE"
};
static const char* MIST_NAMES[] = {"WATCH", "S1", "S2", "FOG"};

// ── Sensor inputs (read-only, populated by ESPHome or test harness) ──
struct SensorInputs {
    float temp_f;           // indoor average temperature (°F)
    float vpd_kpa;          // indoor average VPD (kPa)
    float rh_pct;           // indoor average RH (%)
    float dew_point_f;      // indoor dew point (°F)
    float outdoor_rh_pct;   // outdoor RH (%)
    float enthalpy_delta;   // outdoor - indoor enthalpy (kJ/kg)
    float vpd_south;        // zone VPD sensors
    float vpd_west;
    float vpd_east;
    int   local_hour;       // 0-23, from SNTP
    bool  occupied;         // greenhouse occupancy (from Sentinel)
    int   mister_state;     // current mister state machine stage (0=off, 1=S1, 2=S2)
    uint32_t humid_s2_duration_ms;  // how long in S2 (for fog escalation)
    float fog_escalation_kpa;       // planner tunable
    float fog_rh_ceiling;           // firmware safety gate
    float fog_min_temp;             // firmware safety gate
    int   fog_window_start;         // firmware safety gate (hour)
    int   fog_window_end;           // firmware safety gate (hour)
    uint32_t mister_all_delay_ms;   // S2 delay for fog escalation
    bool  occupancy_inhibit;        // occupancy blocks fog
};

// ── Setpoints (band-driven + planner tunables) ──
struct Setpoints {
    float temp_high;        // band ceiling (°F)
    float temp_low;         // band floor (°F)
    float vpd_high;         // VPD ceiling (kPa)
    float vpd_low;          // VPD floor (kPa)
    float bias_cool;        // planner shift on cooling threshold
    float bias_heat;        // planner shift on heating threshold
    float vpd_hysteresis;   // exit hysteresis for misting
    float dH2;              // heat stage 2 delta (electric pre-heat zone)
    float dC2;              // cool stage 2 delta (aggressive cooling trigger)
    float safety_max;       // absolute temp ceiling (°F)
    float safety_min;       // absolute temp floor (°F)
    float vpd_max_safe;     // absolute VPD ceiling (kPa)
    float vpd_min_safe;     // absolute VPD floor (kPa)
    uint32_t sealed_max_ms;       // max sealed time before thermal relief
    uint32_t relief_duration_ms;  // thermal relief vent-open duration
    uint32_t vpd_watch_dwell_ms;  // observation dwell before sealing
    bool econ_block;        // economiser blocks venting
};

// ── Persistent control state (survives across 5s evaluation cycles) ──
struct ControlState {
    Mode mode;
    Mode mode_prev;
    MistStage mist_stage;
    uint32_t sealed_timer_ms;
    uint32_t relief_timer_ms;
    uint32_t vpd_watch_timer_ms;
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

// ── Default setpoints (safe fallback) ──
inline Setpoints default_setpoints() {
    return {
        .temp_high = 82.0f, .temp_low = 58.0f,
        .vpd_high = 1.2f, .vpd_low = 0.5f,
        .bias_cool = 0.0f, .bias_heat = 0.0f,
        .vpd_hysteresis = 0.3f,
        .dH2 = 5.0f, .dC2 = 3.0f,
        .safety_max = 95.0f, .safety_min = 45.0f,
        .vpd_max_safe = 3.0f, .vpd_min_safe = 0.3f,
        .sealed_max_ms = 600000, .relief_duration_ms = 90000,
        .vpd_watch_dwell_ms = 60000,
        .econ_block = false
    };
}

inline ControlState initial_state() {
    return {
        .mode = IDLE, .mode_prev = IDLE,
        .mist_stage = MIST_WATCH,
        .sealed_timer_ms = 0, .relief_timer_ms = 0,
        .vpd_watch_timer_ms = 0
    };
}
