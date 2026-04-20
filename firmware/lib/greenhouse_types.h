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
    // Sprint-10 0.3: photoperiod flag for day/night setpoint selection.
    // Populated by controls.yaml as (in scheduled daylight window) OR
    // (tempest_lux >> ambient threshold) — hybrid so a cloudy winter day
    // still registers as "day" inside the window and a 2 AM LED test
    // doesn't flip it on outside the window.
    bool  is_photoperiod;
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
    // Sprint-10 0.4b: magic numbers extracted from greenhouse_logic.h.
    // Defaults in default_setpoints() match the pre-sprint-10 constants.
    uint32_t vent_latch_timeout_ms;    // was hardcoded 1800000 (30 min)
    float    safety_max_seal_margin_f; // was hardcoded 5.0 (two places)
    float    econ_heat_margin_f;       // was ECON_HEAT_MARGIN_F const
    // Sprint-10 0.3: day/night setpoint pairs. Legacy temp_high/temp_low/
    // vpd_high/vpd_low above remain as fallbacks (used when day/night are
    // unset, or when validate_setpoints has not been invoked — typical in
    // unit-test paths that construct Setpoints from default_setpoints and
    // modify only the generic fields). Production flow: the planner /
    // dispatcher pushes day/night-specific values every planner cycle.
    float temp_high_day,  temp_high_night;
    float temp_low_day,   temp_low_night;
    float vpd_high_day,   vpd_high_night;
    float vpd_low_day,    vpd_low_night;
};

static constexpr uint32_t STATE_SENTINEL = 0xBEEF0042;
// Sprint-10 0.4b: ECON_HEAT_MARGIN_F moved into Setpoints as
// econ_heat_margin_f (keeping the old constant removed intentionally to
// prevent accidental re-use). Same for the former `1800000` vent-latch
// timeout and the `5.0f` safety_max seal margin.

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
    // Sprint-9 P1#7: Stage-2 heater latch. Set when temp < Tlow - dH2.
    // Cleared when temp >= Tlow + heat_hysteresis (S1 satisfied). Prevents
    // gas-valve rapid cycling in the hysteresis band between the two
    // thresholds. Managed by determine_mode; read by resolve_equipment.
    bool heat2_latched;
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
        .occupancy_inhibit = false, .econ_block = false,
        // Sprint-10 0.4b: magic number defaults match pre-sprint-10 constants.
        .vent_latch_timeout_ms = 1800000u,  // 30 min
        .safety_max_seal_margin_f = 5.0f,
        .econ_heat_margin_f = 5.0f,
        // Sprint-10 0.3: day/night pairs default to 0 (unset). The band
        // resolver (resolve_active_band) falls back to the legacy generic
        // values in that case, so existing test paths that construct
        // Setpoints via default_setpoints() + modify only temp_high/etc.
        // continue to exercise the same thresholds. Production callers
        // invoke validate_setpoints() which back-fills the day/night
        // pairs from the legacy values explicitly.
        .temp_high_day = 0.0f,  .temp_high_night = 0.0f,
        .temp_low_day  = 0.0f,  .temp_low_night  = 0.0f,
        .vpd_high_day  = 0.0f,  .vpd_high_night  = 0.0f,
        .vpd_low_day   = 0.0f,  .vpd_low_night   = 0.0f
    };
}

// Caller must invoke before passing setpoints to determine_mode().
// This function is NOT called automatically — the contract is explicit.
//
// Sprint-9 P2#8: extended with relational asserts so one mis-entered HA
// number can't silently create unreachable modes or mode thrash. Each
// relational clamp picks the "safe side" when the input is inverted so
// the controller stays responsive while logs flag the violation.
inline void validate_setpoints(Setpoints& sp) {
    // --- individual-value clamps (pre-sprint-9) ---
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

    // --- sprint-9 P2#8: relational asserts + previously-unclamped scalars ---
    // vpd_min_safe and vpd_max_safe were completely unclamped before
    // sprint-9, which meant bad HA values could make either bound useless.
    sp.vpd_max_safe = std::max(sp.vpd_high + 0.1f, std::min(8.0f, sp.vpd_max_safe));
    sp.vpd_min_safe = std::max(0.05f, std::min(sp.vpd_low - 0.05f, sp.vpd_min_safe));
    // Full ordering: vpd_min_safe < vpd_low < vpd_high < vpd_max_safe.
    // The three clamps above already enforce adjacent pairs; no further
    // fix-up needed as long as vpd_low stayed strictly < vpd_high.

    // Thigh + dC2 must be below safety_max or the planner can demand
    // aggressive cooling right up to the safety threshold with no buffer.
    sp.dC2 = std::max(1.0f, std::min(sp.safety_max - sp.temp_high - 1.0f, sp.dC2));
    if (sp.dC2 < 1.0f) sp.dC2 = 1.0f;  // floor after the relational clamp
    sp.dH2 = std::max(1.0f, std::min(20.0f, sp.dH2));

    // Relief must complete inside the sealed window, else the was_sealed
    // branch's THERMAL_RELIEF backstop can't meaningfully gate re-seal.
    if (sp.relief_duration_ms >= sp.sealed_max_ms) {
        sp.relief_duration_ms = sp.sealed_max_ms / 4;  // 25% of seal window
        if (sp.relief_duration_ms < 15000) sp.relief_duration_ms = 15000;
    }

    // Fog window: if start == end the window is zero-width (fog always
    // gated) or always-open depending on which comparison wins. Force
    // the default 7-17 window as a recovery point.
    if (sp.fog_window_start == sp.fog_window_end) {
        sp.fog_window_start = 7;
        sp.fog_window_end = 17;
    }
    // Clamp hours to [0, 23] individually (wrap-aware — start > end is
    // valid for midnight-crossing windows).
    sp.fog_window_start = std::max(0, std::min(23, sp.fog_window_start));
    sp.fog_window_end   = std::max(0, std::min(23, sp.fog_window_end));

    // vpd_watch_dwell and mist_s2_delay need non-zero values; zero would
    // make the watchdog fire on every cycle and the S1→S2 promotion
    // happen instantly.
    sp.vpd_watch_dwell_ms = std::max(uint32_t(1000), std::min(uint32_t(600000), sp.vpd_watch_dwell_ms));
    sp.mist_s2_delay_ms   = std::max(uint32_t(1000), std::min(uint32_t(1800000), sp.mist_s2_delay_ms));

    // Fog-specific clamps
    sp.fog_escalation_kpa = std::max(0.05f, std::min(2.0f, sp.fog_escalation_kpa));
    sp.fog_rh_ceiling     = std::max(30.0f, std::min(100.0f, sp.fog_rh_ceiling));
    sp.fog_min_temp       = std::max(30.0f, std::min(100.0f, sp.fog_min_temp));

    // Dehum aggressiveness delta must fit under vpd_low so the
    // "dehum_aggressive" engage threshold (vpd_low - dehum_aggressive_kpa)
    // is positive.
    sp.dehum_aggressive_kpa = std::max(0.05f, std::min(sp.vpd_low - 0.05f, sp.dehum_aggressive_kpa));

    // --- sprint-10 0.4b: magic-number clamps ---
    sp.vent_latch_timeout_ms = std::max(uint32_t(60000),
                                        std::min(uint32_t(7200000), sp.vent_latch_timeout_ms));
    sp.safety_max_seal_margin_f = std::max(1.0f, std::min(15.0f, sp.safety_max_seal_margin_f));
    sp.econ_heat_margin_f       = std::max(1.0f, std::min(15.0f, sp.econ_heat_margin_f));

    // --- sprint-10 0.3: back-fill day/night from legacy, then enforce
    // relational ordering within each pair. Back-fill only when the
    // day/night field is unset (== 0) — an explicit push of 0 for a
    // day/night setpoint is invalid input and we treat it as "not set."
    if (sp.temp_high_day   <= 0.0f) sp.temp_high_day   = sp.temp_high;
    if (sp.temp_high_night <= 0.0f) sp.temp_high_night = sp.temp_high;
    if (sp.temp_low_day    <= 0.0f) sp.temp_low_day    = sp.temp_low;
    if (sp.temp_low_night  <= 0.0f) sp.temp_low_night  = sp.temp_low;
    if (sp.vpd_high_day    <= 0.0f) sp.vpd_high_day    = sp.vpd_high;
    if (sp.vpd_high_night  <= 0.0f) sp.vpd_high_night  = sp.vpd_high;
    if (sp.vpd_low_day     <= 0.0f) sp.vpd_low_day     = sp.vpd_low;
    if (sp.vpd_low_night   <= 0.0f) sp.vpd_low_night   = sp.vpd_low;
    // Pair ordering: low < high within each photoperiod.
    if (sp.temp_low_day    >= sp.temp_high_day)   sp.temp_low_day    = sp.temp_high_day   - 5.0f;
    if (sp.temp_low_night  >= sp.temp_high_night) sp.temp_low_night  = sp.temp_high_night - 5.0f;
    if (sp.vpd_low_day     >= sp.vpd_high_day)    sp.vpd_low_day     = sp.vpd_high_day    - 0.1f;
    if (sp.vpd_low_night   >= sp.vpd_high_night)  sp.vpd_low_night   = sp.vpd_high_night  - 0.1f;
}

inline ControlState initial_state() {
    return {
        .sentinel = STATE_SENTINEL,
        .mode = IDLE, .mode_prev = IDLE,
        .mist_stage = MIST_WATCH,
        .sealed_timer_ms = 0, .relief_timer_ms = 0,
        .vpd_watch_timer_ms = 0, .mist_stage_timer_ms = 0,
        .relief_cycle_count = 0, .vent_latch_timer_ms = 0,
        .dry_override_active = false,
        .heat2_latched = false
    };
}

// ── Sprint-10 0.3: active band resolver ───────────────────────────
// Picks day or night setpoints based on in.is_photoperiod. Falls back
// to the legacy sp.{temp_high,temp_low,vpd_high,vpd_low} if the
// day/night fields are unset (zero) — this preserves existing test
// behavior that constructs Setpoints from default_setpoints() and
// modifies only the generic fields. In production these are always
// populated (validate_setpoints back-fills if needed).
struct ActiveBand {
    float temp_high, temp_low;
    float vpd_high, vpd_low;
};

inline ActiveBand resolve_active_band(const SensorInputs& in, const Setpoints& sp) noexcept {
    auto pick = [](float day, float night, float fallback, bool is_day) {
        float v = is_day ? day : night;
        return (v > 0.0f) ? v : fallback;
    };
    ActiveBand a;
    a.temp_high = pick(sp.temp_high_day, sp.temp_high_night, sp.temp_high, in.is_photoperiod);
    a.temp_low  = pick(sp.temp_low_day,  sp.temp_low_night,  sp.temp_low,  in.is_photoperiod);
    a.vpd_high  = pick(sp.vpd_high_day,  sp.vpd_high_night,  sp.vpd_high,  in.is_photoperiod);
    a.vpd_low   = pick(sp.vpd_low_day,   sp.vpd_low_night,   sp.vpd_low,   in.is_photoperiod);
    return a;
}
