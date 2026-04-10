#pragma once
/*
 * greenhouse_logic.h — Core climate controller logic.
 *
 * THIS IS THE SINGLE SOURCE OF TRUTH for mode determination and equipment
 * resolution. The exact same code runs on:
 *   - ESP32 via ESPHome (controls.yaml includes this header)
 *   - x86 via GoogleTest (test harness compiles this natively)
 *
 * NO ESPHome dependencies. No id(), no ESP_LOG*, no hardware access.
 * Pure functions operating on structs.
 */

#include "greenhouse_types.h"

// ═══════════════════════════════════════════════════════════════════════
// MODE DETERMINATION
//
// Single priority-ordered decision. No override layers.
// Returns the new mode and mutates state (timers, stage).
// ═══════════════════════════════════════════════════════════════════════

inline Mode determine_mode(
    const SensorInputs& in,
    const Setpoints& sp,
    ControlState& state,
    uint32_t dt_ms
) {
    const float Thigh = sp.temp_high + sp.bias_cool;
    const float Tlow  = sp.temp_low  + sp.bias_heat;
    const float HV    = sp.vpd_hysteresis;

    // Conditions
    bool safety_cool    = in.temp_f >= sp.safety_max;
    bool safety_heat    = in.temp_f <= sp.safety_min;
    bool vpd_above_band = in.vpd_kpa > sp.vpd_high;
    bool vpd_below_exit = in.vpd_kpa < (sp.vpd_high - HV);
    bool vpd_too_low    = in.vpd_kpa < (sp.vpd_low - HV) && !sp.econ_block;
    bool needs_cooling  = in.temp_f > Thigh;
    bool in_thermal_relief = (state.mode_prev == THERMAL_RELIEF);
    bool was_sealed        = (state.mode_prev == SEALED_MIST);

    // VPD watch dwell: observe before committing to seal
    if (vpd_above_band && state.mode_prev != SEALED_MIST && state.mode_prev != THERMAL_RELIEF) {
        state.vpd_watch_timer_ms += dt_ms;
    } else if (!vpd_above_band && state.mode_prev != SEALED_MIST && state.mode_prev != THERMAL_RELIEF) {
        state.vpd_watch_timer_ms = 0;
    }
    bool vpd_watch_complete = state.vpd_watch_timer_ms >= sp.vpd_watch_dwell_ms;
    bool vpd_wants_seal = vpd_above_band && vpd_watch_complete;

    // ── Priority-ordered mode determination ──
    Mode mode = IDLE;

    if (safety_cool) {
        mode = SAFETY_COOL;
        state.sealed_timer_ms = 0;
        state.relief_timer_ms = 0;
    } else if (safety_heat) {
        mode = SAFETY_HEAT;
        state.sealed_timer_ms = 0;
    } else if (in_thermal_relief) {
        state.relief_timer_ms += dt_ms;
        if (state.relief_timer_ms >= sp.relief_duration_ms) {
            state.relief_timer_ms = 0;
            state.sealed_timer_ms = 0;
            mode = vpd_above_band ? SEALED_MIST : IDLE;
            if (mode == IDLE) state.vpd_watch_timer_ms = 0;
        } else {
            mode = THERMAL_RELIEF;
        }
    } else if (was_sealed) {
        if (vpd_below_exit) {
            mode = needs_cooling ? VENTILATE : IDLE;
            state.sealed_timer_ms = 0;
            state.mist_stage = MIST_WATCH;
            state.vpd_watch_timer_ms = 0;
        } else if (state.sealed_timer_ms >= sp.sealed_max_ms) {
            mode = THERMAL_RELIEF;
            state.relief_timer_ms = 0;
        } else {
            mode = SEALED_MIST;
            state.sealed_timer_ms += dt_ms;
        }
    } else if (vpd_wants_seal) {
        mode = SEALED_MIST;
        state.sealed_timer_ms = 0;
        state.mist_stage = MIST_S1;
    } else if (vpd_too_low) {
        mode = DEHUM_VENT;
    } else if (needs_cooling) {
        mode = VENTILATE;
    } else {
        mode = IDLE;
    }

    // Safety overrides on VPD extremes
    if (in.vpd_kpa > sp.vpd_max_safe && mode != SAFETY_COOL) {
        mode = SEALED_MIST;
        state.vpd_watch_timer_ms = sp.vpd_watch_dwell_ms;
        state.mist_stage = MIST_S1;
    }
    if (in.vpd_kpa < sp.vpd_min_safe && mode == IDLE) {
        mode = sp.econ_block ? IDLE : DEHUM_VENT;
    }

    state.mode = mode;
    state.mode_prev = mode;
    return mode;
}

// ═══════════════════════════════════════════════════════════════════════
// EQUIPMENT RESOLUTION
//
// Direct function of mode. No overrides. The table IS the truth.
//
// | Mode             | Vent | Fans      | Heat1 | Heat2 | Fog     |
// |------------------|------|-----------|-------|-------|---------|
// | SAFETY_COOL      | OPEN | BOTH      | off   | off   | allowed |
// | SAFETY_HEAT      | SHUT | off       | ON    | ON    | off     |
// | SEALED_MIST      | SHUT | off       | temp  | temp  | escal.  |
// | THERMAL_RELIEF   | OPEN | LEAD      | off   | off   | off     |
// | VENTILATE        | OPEN | 1 or 2    | off   | off   | off     |
// | DEHUM_VENT       | OPEN | LEAD      | off   | off   | off     |
// | IDLE             | SHUT | off       | temp  | temp  | off     |
// ═══════════════════════════════════════════════════════════════════════

inline RelayOutputs resolve_equipment(
    Mode mode,
    const SensorInputs& in,
    const Setpoints& sp,
    bool lead_is_fan1
) {
    const float Tlow = sp.temp_low + sp.bias_heat;
    const float Thigh = sp.temp_high + sp.bias_cool;
    bool needs_heating_s1 = in.temp_f < (Tlow + sp.dH2);
    bool needs_heating_s2 = in.temp_f < Tlow;

    RelayOutputs out = {false, false, false, false, false, false};

    switch (mode) {
        case SAFETY_COOL:
            out.vent = true;
            out.fan1 = true; out.fan2 = true;
            // Fog allowed as evaporative cooling assist
            {
                bool fog_ok = !(in.rh_pct > in.fog_rh_ceiling)
                    && !(in.temp_f < in.fog_min_temp)
                    && (in.local_hour >= in.fog_window_start)
                    && (in.local_hour < in.fog_window_end)
                    && !in.occupancy_inhibit;
                out.fog = fog_ok && in.vpd_kpa > sp.vpd_high;
            }
            break;

        case SAFETY_HEAT:
            out.heat1 = true; out.heat2 = true;
            break;

        case SEALED_MIST:
            if (needs_heating_s2) { out.heat1 = true; out.heat2 = true; }
            else if (needs_heating_s1) { out.heat1 = true; }
            // Fog escalation
            {
                bool fog_gated = (in.rh_pct > in.fog_rh_ceiling)
                    || (in.temp_f < in.fog_min_temp)
                    || (in.local_hour < in.fog_window_start)
                    || (in.local_hour >= in.fog_window_end);
                bool fog_escalation = (in.mister_state == 2)
                    && (in.humid_s2_duration_ms > in.mister_all_delay_ms)
                    && (in.vpd_kpa > sp.vpd_high + in.fog_escalation_kpa);
                out.fog = fog_escalation && !fog_gated && !in.occupancy_inhibit;
            }
            break;

        case THERMAL_RELIEF:
            out.vent = true;
            if (lead_is_fan1) out.fan1 = true; else out.fan2 = true;
            break;

        case VENTILATE: {
            out.vent = true;
            bool needs_both = in.temp_f > (Thigh + sp.dC2);
            if (lead_is_fan1) { out.fan1 = true; out.fan2 = needs_both; }
            else              { out.fan2 = true; out.fan1 = needs_both; }
            break;
        }

        case DEHUM_VENT:
            out.vent = true;
            if (in.vpd_kpa < sp.vpd_low - 2 * sp.vpd_hysteresis) {
                out.fan1 = true; out.fan2 = true;
            } else {
                if (lead_is_fan1) out.fan1 = true; else out.fan2 = true;
            }
            break;

        case IDLE:
            if (needs_heating_s2) { out.heat1 = true; out.heat2 = true; }
            else if (needs_heating_s1) { out.heat1 = true; }
            if (in.vpd_kpa < sp.vpd_low && sp.econ_block) {
                out.heat1 = true; out.heat2 = true;
            }
            break;
    }

    return out;
}
