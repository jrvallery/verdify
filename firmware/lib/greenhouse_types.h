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
    SENSOR_FAULT,     // NaN/invalid/implausible sensor readings — ALL relays off
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
    float temp_high;
    float temp_low;
    float vpd_high;
    float vpd_low;
    float bias_cool;
    float bias_heat;
    float vpd_hysteresis;
    float temp_hysteresis;
    float heat_hysteresis;
    float dH2;
    float dC2;
    float safety_max;
    float safety_min;
    float vpd_max_safe;
    float vpd_min_safe;
    uint32_t sealed_max_ms;
    uint32_t relief_duration_ms;
    uint32_t vpd_watch_dwell_ms;
    uint32_t mist_s2_delay_ms;
    uint32_t max_relief_cycles;   // R2-6: consecutive sealed→relief cycles before forced vent
    float fog_escalation_kpa;
    float fog_rh_ceiling;
    float fog_min_temp;
    int   fog_window_start;
    int   fog_window_end;
    float dehum_aggressive_kpa;
    bool  occupancy_inhibit;
    bool  econ_block;
};

static constexpr uint32_t STATE_SENTINEL = 0xBEEF0042;
static constexpr float ECON_HEAT_MARGIN_F = 5.0f;

// ── Persistent control state ──
struct ControlState {
    uint32_t sentinel;
    Mode mode;
    Mode mode_prev;
    MistStage mist_stage;
    uint32_t sealed_timer_ms;
    uint32_t relief_timer_ms;
    uint32_t vpd_watch_timer_ms;
    uint32_t mist_stage_timer_ms;
    uint32_t relief_cycle_count;
    uint32_t vent_latch_timer_ms;  // FW-8: tracks time in relief-exhausted VENTILATE latch
    // OBS-1e (Sprint 16 patch): set by determine_mode() R2-3 dry-override path
    // on cycles where the firmware forces a SEAL the planner's dwell hadn't
    // yet sanctioned. Read by evaluate_overrides() — cannot be reconstructed
    // post-hoc because R2-3 mutates vpd_watch_timer_ms in the same cycle.
    bool dry_override_active;
};

struct RelayOutputs {
    bool heat1;
    bool heat2;
    bool fan1;
    bool fan2;
    bool fog;
    bool vent;
};

// ── OBS-1e: firmware silent-override audit (Sprint 16) ──
// Each flag captures a specific firmware-side decision that negates or
// blocks planner intent without going through a planner-visible channel.
// Evaluated after determine_mode() by evaluate_overrides(); published to
// ingestor as a comma-separated string, routed to override_events table.
struct OverrideFlags {
    bool occupancy_blocks_moisture;  // occupancy inhibit active while mist was wanted
    bool fog_gate_rh;                // fog wanted but in.rh_pct > fog_rh_ceiling
    bool fog_gate_temp;              // fog wanted but in.temp_f < fog_min_temp
    bool fog_gate_window;            // fog wanted but outside fog_window_start/end
    bool relief_cycle_breaker;       // seal wanted but relief_cycle_count maxed → forced VENTILATE
    bool seal_blocked_temp;          // seal wanted but within 5°F of safety_max
    bool vpd_dry_override;           // firmware sealed for VPD safety without planner dwell
};

// ── Saturating addition (prevents uint32_t overflow at 49.7 days) ──
inline uint32_t sat_add(uint32_t a, uint32_t b) noexcept {
    return (a > UINT32_MAX - b) ? UINT32_MAX : a + b;
}

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
        .max_relief_cycles = 3,
        .fog_escalation_kpa = 0.4f, .fog_rh_ceiling = 90.0f,
        .fog_min_temp = 55.0f, .fog_window_start = 7, .fog_window_end = 17,
        .dehum_aggressive_kpa = 0.6f,
        .occupancy_inhibit = false, .econ_block = false
    };
}

// Caller must invoke before passing setpoints to determine_mode().
// This function is NOT called automatically — the contract is explicit.
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
    sp.max_relief_cycles = std::max(uint32_t(1), std::min(uint32_t(10), sp.max_relief_cycles));
}

inline ControlState initial_state() {
    return {
        .sentinel = STATE_SENTINEL,
        .mode = IDLE, .mode_prev = IDLE,
        .mist_stage = MIST_WATCH,
        .sealed_timer_ms = 0, .relief_timer_ms = 0,
        .vpd_watch_timer_ms = 0, .mist_stage_timer_ms = 0,
        .relief_cycle_count = 0, .vent_latch_timer_ms = 0,
        .dry_override_active = false
    };
}
