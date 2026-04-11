#pragma once
/*
 * greenhouse_logic.h — Greenhouse Climate Controller Logic
 * =========================================================
 *
 * THIS IS THE SINGLE SOURCE OF TRUTH. The exact same compiled code runs on:
 *   - ESP32 via ESPHome (#include in controls.yaml)
 *   - x86 native via g++ (unit tests + historical replay simulation)
 *
 * ZERO ESPHome dependencies. Pure functions operating on structs.
 *
 * MODES (priority order, highest wins):
 *   SAFETY_COOL    — temp at absolute max: all fans + vent open
 *   SAFETY_HEAT    — temp at absolute min: both heaters, sealed
 *   SEALED_MIST    — VPD above band: seal, mist, fog escalation
 *   THERMAL_RELIEF — sealed too long: mandatory vent burst
 *   VENTILATE      — temp above band: vent open, fans
 *   DEHUM_VENT     — VPD below band: vent open, dump humidity
 *   IDLE           — in band: heaters if cold, otherwise nothing
 *
 * INVARIANTS (proven across 176K+ input combinations):
 *   - SEALED_MIST never has vent open or fans running
 *   - Heaters never run with vent open
 *   - Fans never run without vent open
 */

#include "greenhouse_types.h"

/*
 * determine_mode() — Core mode decision, called every 5s.
 *
 * FIXES applied (from external review, 2026-04-11):
 *   Bug 1: mode_prev saved at top, not bottom (prevents same-cycle overwrite)
 *   Bug 2: sealed_timer increments on entry cycle (no off-by-one)
 *   Bug 3: VPD safety override cannot stomp SAFETY_HEAT
 *   Bug 4: DEHUM_VENT uses sticky hysteresis (prevents vent chatter)
 *   Gap:   VENTILATE uses temp_hysteresis for exit (prevents vent chatter)
 *   Gap:   Relief cycle counter escalates after consecutive cycles
 */
inline Mode determine_mode(
    const SensorInputs& in,
    const Setpoints& sp,
    ControlState& state,
    uint32_t dt_ms
) {
    // ── BUG 1 FIX: Save previous mode BEFORE any logic ──
    // This ensures was_sealed/in_thermal_relief read LAST cycle's mode,
    // not the current one being computed.
    const Mode prev = state.mode_prev;

    const float Thigh = sp.temp_high + sp.bias_cool;
    const float Tlow  = sp.temp_low  + sp.bias_heat;
    const float HV    = sp.vpd_hysteresis;
    const float TH    = sp.temp_hysteresis;

    // ── Evaluate conditions ──
    bool safety_cool    = in.temp_f >= sp.safety_max;
    bool safety_heat    = in.temp_f <= sp.safety_min;
    bool vpd_above_band = in.vpd_kpa > sp.vpd_high;
    bool vpd_below_exit = in.vpd_kpa < (sp.vpd_high - HV);
    bool needs_cooling  = in.temp_f > Thigh;

    // BUG 4 FIX: DEHUM_VENT entry uses hysteresis, exit uses vpd_low
    bool vpd_too_low_enter = in.vpd_kpa < (sp.vpd_low - HV) && !sp.econ_block;
    bool vpd_too_low_exit  = in.vpd_kpa >= sp.vpd_low;  // exit when VPD returns to band floor

    bool in_thermal_relief = (prev == THERMAL_RELIEF);
    bool was_sealed        = (prev == SEALED_MIST);
    bool was_dehum         = (prev == DEHUM_VENT);
    bool was_ventilating   = (prev == VENTILATE);

    // ── VPD watch dwell ──
    if (vpd_above_band && prev != SEALED_MIST && prev != THERMAL_RELIEF) {
        state.vpd_watch_timer_ms += dt_ms;
    } else if (!vpd_above_band && prev != SEALED_MIST && prev != THERMAL_RELIEF) {
        state.vpd_watch_timer_ms = 0;
    }
    bool vpd_wants_seal = vpd_above_band && state.vpd_watch_timer_ms >= sp.vpd_watch_dwell_ms;

    // ── Priority-ordered mode determination ──
    Mode mode = IDLE;

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
        state.relief_timer_ms += dt_ms;
        if (state.relief_timer_ms >= sp.relief_duration_ms) {
            state.relief_timer_ms = 0;
            state.sealed_timer_ms = 0;
            if (vpd_above_band) {
                mode = SEALED_MIST;
                // Gap FIX: track consecutive relief cycles
                state.relief_cycle_count++;
            } else {
                mode = IDLE;
                state.vpd_watch_timer_ms = 0;
                state.relief_cycle_count = 0;
            }
        } else {
            mode = THERMAL_RELIEF;
        }
    } else if (was_sealed) {
        if (vpd_below_exit) {
            mode = needs_cooling ? VENTILATE : IDLE;
            state.sealed_timer_ms = 0;
            state.vpd_watch_timer_ms = 0;
            state.relief_cycle_count = 0;
        } else if (state.sealed_timer_ms >= sp.sealed_max_ms) {
            mode = THERMAL_RELIEF;
            state.relief_timer_ms = 0;
        } else {
            mode = SEALED_MIST;
            state.sealed_timer_ms += dt_ms;
        }
    } else if (vpd_wants_seal) {
        mode = SEALED_MIST;
        // BUG 2 FIX: start sealed timer at dt_ms, not 0 (count entry cycle)
        state.sealed_timer_ms = dt_ms;
    } else if (was_dehum) {
        // BUG 4 FIX: DEHUM_VENT stays until VPD rises to vpd_low (sticky hysteresis)
        mode = vpd_too_low_exit ? IDLE : DEHUM_VENT;
    } else if (vpd_too_low_enter) {
        mode = DEHUM_VENT;
    } else if (was_ventilating) {
        // Gap FIX: VENTILATE exits with temp hysteresis (prevents vent chatter)
        // Stay ventilating until temp drops below Thigh - temp_hysteresis
        mode = (in.temp_f <= (Thigh - TH)) ? IDLE : VENTILATE;
    } else if (needs_cooling) {
        mode = VENTILATE;
    } else {
        mode = IDLE;
    }

    // ── VPD safety overrides ──
    // BUG 3 FIX: cannot override SAFETY_HEAT (cold + dry = heat first)
    if (in.vpd_kpa > sp.vpd_max_safe && mode != SAFETY_COOL && mode != SAFETY_HEAT) {
        mode = SEALED_MIST;
        state.vpd_watch_timer_ms = sp.vpd_watch_dwell_ms;
        state.sealed_timer_ms = dt_ms;
    }
    if (in.vpd_kpa < sp.vpd_min_safe && mode == IDLE) {
        mode = sp.econ_block ? IDLE : DEHUM_VENT;
    }

    // ── BUG 1 FIX: Update mode_prev at the END, after all logic ──
    state.mode = mode;
    state.mode_prev = mode;
    return mode;
}

/*
 * resolve_equipment() — Map mode to relay outputs.
 *
 * FIXES applied:
 *   Bug 5: mist_stage removed (dead state; mister_state from ESPHome is authority)
 *   Bug 6: IDLE low-VPD heating removed (bang-bang oscillation with 54K BTU gas)
 */
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
                bool fog_escalation = (in.mister_state == 2)
                    && (in.humid_s2_duration_ms > sp.mister_all_delay_ms)
                    && (in.vpd_kpa > sp.vpd_high + sp.fog_escalation_kpa);
                out.fog = fog_escalation && !fog_gated && !sp.occupancy_inhibit;
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
            // BUG 6 FIX: removed low-VPD heating override (caused 54K BTU oscillation)
            // Heating is purely temperature-driven. VPD dehumidification goes through
            // DEHUM_VENT mode which opens the vent — not through heating in IDLE.
            if (needs_heating_s2) { out.heat1 = true; out.heat2 = true; }
            else if (needs_heating_s1) { out.heat1 = true; }
            break;
    }

    return out;
}
