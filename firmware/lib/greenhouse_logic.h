#pragma once
/*
 * greenhouse_logic.h — Greenhouse Climate Controller Logic
 * =========================================================
 *
 * SINGLE SOURCE OF TRUTH. Same compiled code on ESP32 and x86.
 * ZERO ESPHome dependencies.
 *
 * NOTE: determine_mode() mutates ControlState (timers, mode_prev).
 * resolve_equipment() is pure (reads only, no side effects).
 *
 * HARDWARE DEPENDENCIES (not enforced here, must be enforced by caller):
 *   - Relay minimum on/off times (ESPHome set_relay with min_on_ms/min_off_ms)
 *   - Gas heater minimum off time (MIN_HEAT_OFF_MS, typically 300s)
 *   - Vent actuator travel time (1-5 min, ESPHome min_vent_on_s/min_vent_off_s)
 *
 * SENSOR_FAULT recovery note: when sensors return to valid after SENSOR_FAULT,
 * the next cycle re-evaluates from scratch (prev=SENSOR_FAULT matches no
 * stateful branch). Accumulated timers in ControlState are stale but harmless.
 */

#include "greenhouse_types.h"

// ═══════════════════════════════════════════════════════════════════
// determine_mode() — Core mode decision, called every 5s.
// Mutates state (timers, mode_prev, mist_stage). Not pure.
// ═══════════════════════════════════════════════════════════════════
inline Mode determine_mode(
    const SensorInputs& in,
    const Setpoints& sp,
    ControlState& state,
    uint32_t dt_ms
) {
    // ── C2: Sentinel check — detect state corruption ──
    if (state.sentinel != STATE_SENTINEL) {
        state = initial_state();
        // Corruption detected — start fresh from IDLE
    }

    // ── NaN guard — sensor fault takes highest priority ──
    if (std::isnan(in.temp_f) || std::isnan(in.vpd_kpa) || std::isnan(in.rh_pct)) {
        state.mode = SENSOR_FAULT;
        state.mode_prev = SENSOR_FAULT;
        return SENSOR_FAULT;
    }

    // ── Capture previous mode BEFORE any logic ──
    const Mode prev = state.mode_prev;

    const float Thigh = sp.temp_high + sp.bias_cool;
    const float Tlow  = sp.temp_low  + sp.bias_heat;
    // R2 FIX: Clamp hysteresis to prevent contradictory exit conditions
    const float HV    = std::min(sp.vpd_hysteresis, sp.vpd_high * 0.5f);

    // ── Evaluate conditions ──
    bool safety_cool    = in.temp_f >= sp.safety_max;
    bool safety_heat    = in.temp_f <= sp.safety_min;
    bool vpd_above_band = in.vpd_kpa > sp.vpd_high;
    bool vpd_below_exit = in.vpd_kpa < (sp.vpd_high - HV);

    bool vpd_too_low_enter = in.vpd_kpa < (sp.vpd_low - HV) && !sp.econ_block;
    bool vpd_dehum_exit    = in.vpd_kpa >= sp.vpd_low;

    bool was_ventilating = (prev == VENTILATE);
    bool needs_cooling   = was_ventilating
        ? in.temp_f > (Thigh - sp.temp_hysteresis)
        : in.temp_f > Thigh;

    bool was_sealed = (prev == SEALED_MIST);
    bool was_dehum  = (prev == DEHUM_VENT);
    bool in_thermal_relief = (prev == THERMAL_RELIEF);

    // ── VPD watch timer — suspended during safety modes ──
    if (vpd_above_band
        && prev != SEALED_MIST && prev != THERMAL_RELIEF
        && prev != SAFETY_COOL && prev != SAFETY_HEAT) {
        state.vpd_watch_timer_ms = sat_add(state.vpd_watch_timer_ms, dt_ms);  // C5 FIX
    } else if (!vpd_above_band
        && prev != SEALED_MIST && prev != THERMAL_RELIEF) {
        state.vpd_watch_timer_ms = 0;
    }
    bool vpd_wants_seal = vpd_above_band && state.vpd_watch_timer_ms >= sp.vpd_watch_dwell_ms;

    // ── Priority-ordered mode determination ──
    Mode mode = IDLE;
    bool relief_just_expired = false;

    if (safety_cool) {
        mode = SAFETY_COOL;
        state.sealed_timer_ms = 0;
        state.relief_timer_ms = 0;
    } else if (safety_heat) {
        mode = SAFETY_HEAT;
        state.sealed_timer_ms = 0;
    } else if (in_thermal_relief) {
        state.relief_timer_ms = sat_add(state.relief_timer_ms, dt_ms);  // C5 FIX
        if (state.relief_timer_ms >= sp.relief_duration_ms) {
            state.relief_timer_ms = 0;
            state.sealed_timer_ms = 0;
            state.vpd_watch_timer_ms = 0;
            relief_just_expired = true;
        } else {
            mode = THERMAL_RELIEF;
        }
    }

    if (mode != SAFETY_COOL && mode != SAFETY_HEAT && mode != THERMAL_RELIEF) {
        if (was_sealed && !relief_just_expired) {
            if (vpd_below_exit) {
                mode = needs_cooling ? VENTILATE : IDLE;
                state.sealed_timer_ms = 0;
                state.vpd_watch_timer_ms = 0;
                state.mist_stage = MIST_WATCH;
                state.mist_stage_timer_ms = 0;
            } else if (state.sealed_timer_ms >= sp.sealed_max_ms) {
                mode = THERMAL_RELIEF;
                state.relief_timer_ms = 0;
            } else {
                mode = SEALED_MIST;
                state.sealed_timer_ms = sat_add(state.sealed_timer_ms, dt_ms);  // C5 FIX
            }
        } else if (vpd_wants_seal) {
            mode = SEALED_MIST;
            state.sealed_timer_ms = dt_ms;
            state.mist_stage = MIST_S1;
            state.mist_stage_timer_ms = 0;
        } else if (vpd_too_low_enter) {
            mode = DEHUM_VENT;
        } else if (was_dehum && !vpd_dehum_exit) {
            mode = DEHUM_VENT;
        } else if (needs_cooling) {
            mode = VENTILATE;
        } else {
            mode = IDLE;
        }
    }

    // ── VPD safety overrides — cannot stomp safety or relief ──
    if (in.vpd_kpa > sp.vpd_max_safe
        && mode != SAFETY_COOL
        && mode != SAFETY_HEAT
        && mode != THERMAL_RELIEF) {
        mode = SEALED_MIST;
        state.vpd_watch_timer_ms = sp.vpd_watch_dwell_ms;
        state.sealed_timer_ms = 0;
        state.mist_stage = MIST_S1;
        state.mist_stage_timer_ms = 0;
    }
    if (in.vpd_kpa < sp.vpd_min_safe && mode == IDLE) {
        mode = sp.econ_block ? IDLE : DEHUM_VENT;
    }

    // ── Mist stage progression ──
    if (mode == SEALED_MIST) {
        state.mist_stage_timer_ms = sat_add(state.mist_stage_timer_ms, dt_ms);  // C5 FIX
        switch (state.mist_stage) {
            case MIST_WATCH:
                state.mist_stage = MIST_S1;
                state.mist_stage_timer_ms = 0;
                break;
            case MIST_S1:
                if (state.mist_stage_timer_ms >= sp.mist_s2_delay_ms
                    && in.vpd_kpa > sp.vpd_high) {
                    state.mist_stage = MIST_S2;
                    state.mist_stage_timer_ms = 0;
                }
                break;
            case MIST_S2:
                if (in.vpd_kpa > sp.vpd_high + sp.fog_escalation_kpa) {
                    state.mist_stage = MIST_FOG;
                    state.mist_stage_timer_ms = 0;
                }
                // R4 FIX: De-escalate with hysteresis (not raw vpd_high)
                if (in.vpd_kpa < sp.vpd_high - HV) {
                    state.mist_stage = MIST_S1;
                    state.mist_stage_timer_ms = 0;
                }
                break;
            case MIST_FOG:
                if (in.vpd_kpa <= sp.vpd_high + sp.fog_escalation_kpa) {
                    state.mist_stage = MIST_S2;
                    state.mist_stage_timer_ms = 0;
                }
                break;
            default:  // C3 FIX: Corrupted mist_stage → reset
                state.mist_stage = MIST_WATCH;
                state.mist_stage_timer_ms = 0;
                break;
        }
    } else {
        if (state.mist_stage != MIST_WATCH) {
            state.mist_stage = MIST_WATCH;
            state.mist_stage_timer_ms = 0;
        }
    }

    state.mode = mode;
    state.mode_prev = mode;
    return mode;
}

// ═══════════════════════════════════════════════════════════════════
// resolve_equipment() — Map mode to relay outputs. Pure function.
// ═══════════════════════════════════════════════════════════════════
inline RelayOutputs resolve_equipment(
    Mode mode,
    const SensorInputs& in,
    const Setpoints& sp,
    const ControlState& state,
    bool lead_is_fan1
) {
    const float Tlow = sp.temp_low + sp.bias_heat;
    const float Thigh = sp.temp_high + sp.bias_cool;

    bool needs_heating_s1 = in.temp_f < (Tlow + sp.dH2);
    bool needs_heating_s2 = in.temp_f < (Tlow - sp.heat_hysteresis);

    RelayOutputs out = {false, false, false, false, false, false};

    switch (mode) {
        case SENSOR_FAULT:
            out.heat1 = true;  // keep warm, don't cook
            break;

        case SAFETY_COOL:
            out.vent = true;
            out.fan1 = true; out.fan2 = true;
            {
                bool fog_ok = !(in.rh_pct > sp.fog_rh_ceiling)
                    && !(in.temp_f < sp.fog_min_temp)
                    && (in.local_hour >= sp.fog_window_start)
                    && (in.local_hour < sp.fog_window_end)
                    && !sp.occupancy_inhibit;
                out.fog = fog_ok && in.vpd_kpa > sp.vpd_high;
            }
            break;

        case SAFETY_HEAT:
            out.heat1 = true; out.heat2 = true;
            break;

        case SEALED_MIST:
            if (needs_heating_s2) { out.heat1 = true; out.heat2 = true; }
            else if (needs_heating_s1) { out.heat1 = true; }
            {
                bool fog_gated = (in.rh_pct > sp.fog_rh_ceiling)
                    || (in.temp_f < sp.fog_min_temp)
                    || (in.local_hour < sp.fog_window_start)
                    || (in.local_hour >= sp.fog_window_end);
                out.fog = (state.mist_stage == MIST_FOG) && !fog_gated && !sp.occupancy_inhibit;
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
            if (in.vpd_kpa < sp.vpd_low - sp.dehum_aggressive_kpa) {
                out.fan1 = true; out.fan2 = true;
            } else {
                if (lead_is_fan1) out.fan1 = true; else out.fan2 = true;
            }
            break;

        case IDLE:
            if (needs_heating_s2) { out.heat1 = true; out.heat2 = true; }
            else if (needs_heating_s1) { out.heat1 = true; }
            if (in.vpd_kpa < sp.vpd_low && sp.econ_block && in.temp_f < Thigh - ECON_HEAT_MARGIN_F) {
                out.heat1 = true;
            }
            break;

        default:  // C4 FIX: Corrupted mode → fail warm
            out.heat1 = true;
            break;
    }

    return out;
}
