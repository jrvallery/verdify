#pragma once
/*
 * greenhouse_logic.h — Greenhouse Climate Controller Logic
 * =========================================================
 *
 * SINGLE SOURCE OF TRUTH. Same compiled code on ESP32 and x86.
 * ZERO ESPHome dependencies. Pure functions on structs.
 *
 * This code OWNS all control state including mist_stage.
 * ESPHome/controls.yaml is an I/O bridge, not the authority.
 *
 * Fixes applied (from 4-LLM review synthesis, 2026-04-11):
 *   1. mode_prev captured at top, written at bottom
 *   2. VPD safety cannot override SAFETY_HEAT or THERMAL_RELIEF
 *   3. Temperature hysteresis for VENTILATE exit + heater exit
 *   4. DEHUM_VENT sticky exit hysteresis
 *   5. Relief exit re-runs full cascade (no inline mini-decision)
 *   6. IDLE econ heating: electric only, temp-capped
 *   7. VPD watch timer suspended during safety modes
 *   8. NaN guard → SENSOR_FAULT mode
 *   9. mist_stage is the authority (not in.mister_state)
 *  10. DEHUM_VENT dual-fan threshold is tunable
 *  11. Config moved from SensorInputs to Setpoints
 */

#include "greenhouse_types.h"

// ═══════════════════════════════════════════════════════════════════
// determine_mode() — Core mode decision, called every 5s.
// ═══════════════════════════════════════════════════════════════════
inline Mode determine_mode(
    const SensorInputs& in,
    const Setpoints& sp,
    ControlState& state,
    uint32_t dt_ms
) {
    // ── FIX 8: NaN guard — sensor fault takes highest priority ──
    if (std::isnan(in.temp_f) || std::isnan(in.vpd_kpa) || std::isnan(in.rh_pct)) {
        state.mode = SENSOR_FAULT;
        state.mode_prev = SENSOR_FAULT;
        return SENSOR_FAULT;
    }

    // ── FIX 1: Capture previous mode BEFORE any logic ──
    const Mode prev = state.mode_prev;

    const float Thigh = sp.temp_high + sp.bias_cool;
    const float Tlow  = sp.temp_low  + sp.bias_heat;
    const float HV    = sp.vpd_hysteresis;

    // ── Evaluate conditions ──
    bool safety_cool    = in.temp_f >= sp.safety_max;
    bool safety_heat    = in.temp_f <= sp.safety_min;
    bool vpd_above_band = in.vpd_kpa > sp.vpd_high;
    bool vpd_below_exit = in.vpd_kpa < (sp.vpd_high - HV);

    // FIX 4: DEHUM_VENT entry vs exit thresholds (sticky hysteresis)
    bool vpd_too_low_enter = in.vpd_kpa < (sp.vpd_low - HV) && !sp.econ_block;
    bool vpd_dehum_exit    = in.vpd_kpa >= sp.vpd_low;

    // FIX 3: VENTILATE entry vs exit (temperature hysteresis)
    bool was_ventilating = (prev == VENTILATE);
    bool needs_cooling   = was_ventilating
        ? in.temp_f > (Thigh - sp.temp_hysteresis)
        : in.temp_f > Thigh;

    bool was_sealed = (prev == SEALED_MIST);
    bool was_dehum  = (prev == DEHUM_VENT);
    bool in_thermal_relief = (prev == THERMAL_RELIEF);

    // ── FIX 7: VPD watch timer — suspended during safety modes ──
    if (vpd_above_band
        && prev != SEALED_MIST && prev != THERMAL_RELIEF
        && prev != SAFETY_COOL && prev != SAFETY_HEAT) {
        state.vpd_watch_timer_ms += dt_ms;
    } else if (!vpd_above_band
        && prev != SEALED_MIST && prev != THERMAL_RELIEF) {
        state.vpd_watch_timer_ms = 0;
    }
    bool vpd_wants_seal = vpd_above_band && state.vpd_watch_timer_ms >= sp.vpd_watch_dwell_ms;

    // ── Priority-ordered mode determination ──
    Mode mode = IDLE;

    // FIX 5: Relief exit flag — when relief expires, fall through to full cascade
    bool relief_just_expired = false;

    if (safety_cool) {
        mode = SAFETY_COOL;
        state.sealed_timer_ms = 0;
        state.relief_timer_ms = 0;
        state.relief_cycle_count = 0;
    } else if (safety_heat) {
        mode = SAFETY_HEAT;
        state.sealed_timer_ms = 0;
        state.relief_cycle_count = 0;
    } else if (in_thermal_relief) {
        // FIX 5: When relief expires, DON'T pick mode inline — fall through
        state.relief_timer_ms += dt_ms;
        if (state.relief_timer_ms >= sp.relief_duration_ms) {
            state.relief_timer_ms = 0;
            state.sealed_timer_ms = 0;
            state.vpd_watch_timer_ms = 0;
            relief_just_expired = true;
            // Track consecutive cycles
            if (vpd_above_band) state.relief_cycle_count++;
            else state.relief_cycle_count = 0;
            // Don't set mode — fall through to cascade below
        } else {
            mode = THERMAL_RELIEF;
        }
    }

    // The rest of the cascade runs if we haven't landed on a mode yet
    if (mode != SAFETY_COOL && mode != SAFETY_HEAT && mode != THERMAL_RELIEF) {
        // FIX 5: Skip was_sealed on the tick relief just expired
        if (was_sealed && !relief_just_expired) {
            if (vpd_below_exit) {
                mode = needs_cooling ? VENTILATE : IDLE;
                state.sealed_timer_ms = 0;
                state.vpd_watch_timer_ms = 0;
                state.relief_cycle_count = 0;
                state.mist_stage = MIST_WATCH;
                state.mist_stage_timer_ms = 0;
            } else if (state.sealed_timer_ms >= sp.sealed_max_ms) {
                mode = THERMAL_RELIEF;
                state.relief_timer_ms = 0;
            } else {
                mode = SEALED_MIST;
                state.sealed_timer_ms += dt_ms;
            }
        } else if (vpd_wants_seal) {
            mode = SEALED_MIST;
            state.sealed_timer_ms = dt_ms;  // FIX 2 (off-by-one): count entry tick
            state.mist_stage = MIST_S1;
            state.mist_stage_timer_ms = 0;
        } else if (vpd_too_low_enter) {
            mode = DEHUM_VENT;
        } else if (was_dehum && !vpd_dehum_exit) {
            // FIX 4: Stay in DEHUM_VENT until VPD recovers to vpd_low
            mode = DEHUM_VENT;
        } else if (needs_cooling) {
            mode = VENTILATE;
        } else {
            mode = IDLE;
        }
    }

    // ── FIX 2: VPD safety overrides — cannot stomp safety or relief ──
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

    // ── FIX 9: Mist stage progression (this code is the authority) ──
    if (mode == SEALED_MIST) {
        state.mist_stage_timer_ms += dt_ms;
        switch (state.mist_stage) {
            case MIST_WATCH:
                // Should not be in WATCH while sealed — promote to S1
                state.mist_stage = MIST_S1;
                state.mist_stage_timer_ms = 0;
                break;
            case MIST_S1:
                // Escalate to S2 after mist_s2_delay_ms
                if (state.mist_stage_timer_ms >= sp.mist_s2_delay_ms
                    && in.vpd_kpa > sp.vpd_high) {
                    state.mist_stage = MIST_S2;
                    state.mist_stage_timer_ms = 0;
                }
                break;
            case MIST_S2:
                // Escalate to FOG if VPD exceeds ceiling + fog_escalation_kpa
                if (in.vpd_kpa > sp.vpd_high + sp.fog_escalation_kpa) {
                    state.mist_stage = MIST_FOG;
                    state.mist_stage_timer_ms = 0;
                }
                // De-escalate to S1 if VPD drops below band ceiling
                if (in.vpd_kpa < sp.vpd_high) {
                    state.mist_stage = MIST_S1;
                    state.mist_stage_timer_ms = 0;
                }
                break;
            case MIST_FOG:
                // De-escalate to S2 if VPD drops below fog threshold
                if (in.vpd_kpa <= sp.vpd_high + sp.fog_escalation_kpa) {
                    state.mist_stage = MIST_S2;
                    state.mist_stage_timer_ms = 0;
                }
                break;
        }
    } else {
        // Not sealed — reset mist state
        if (state.mist_stage != MIST_WATCH) {
            state.mist_stage = MIST_WATCH;
            state.mist_stage_timer_ms = 0;
        }
    }

    // ── FIX 1: Write mode_prev at the END ──
    state.mode = mode;
    state.mode_prev = mode;
    return mode;
}

// ═══════════════════════════════════════════════════════════════════
// resolve_equipment() — Map mode to relay outputs.
// FIX 9: Takes ControlState for mist_stage authority.
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

    // FIX 3: Heater thresholds with asymmetric hysteresis
    // Heat2 (gas) requires temp BELOW Tlow by heat_hysteresis (avoid gas short-cycle)
    bool needs_heating_s1 = in.temp_f < (Tlow + sp.dH2);
    bool needs_heating_s2 = in.temp_f < (Tlow - sp.heat_hysteresis);

    RelayOutputs out = {false, false, false, false, false, false};

    switch (mode) {
        case SENSOR_FAULT:
            // FIX 8: Safe posture — heat1 on (keep warm), everything else off
            out.heat1 = true;
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
            // FIX 9: Fog based on mist_stage (this code is authority)
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
            // FIX 10: Tunable dual-fan threshold
            if (in.vpd_kpa < sp.vpd_low - sp.dehum_aggressive_kpa) {
                out.fan1 = true; out.fan2 = true;
            } else {
                if (lead_is_fan1) out.fan1 = true; else out.fan2 = true;
            }
            break;

        case IDLE:
            if (needs_heating_s2) { out.heat1 = true; out.heat2 = true; }
            else if (needs_heating_s1) { out.heat1 = true; }
            // FIX 6: Econ heating — electric only, temp-capped (no gas oscillation)
            if (in.vpd_kpa < sp.vpd_low && sp.econ_block && in.temp_f < Thigh - 5.0f) {
                out.heat1 = true;
            }
            break;
    }

    return out;
}
