#pragma once
/*
 * greenhouse_logic.h — Greenhouse Climate Controller Logic
 * =========================================================
 *
 * THIS IS THE SINGLE SOURCE OF TRUTH for the greenhouse climate controller.
 * The exact same compiled code runs on:
 *   - ESP32 via ESPHome (#include in controls.yaml)
 *   - x86 native via g++ (unit tests + historical replay simulation)
 *
 * ZERO ESPHome dependencies. No id(), no ESP_LOG*, no hardware access.
 * Pure functions operating on structs. Fully testable.
 *
 * ARCHITECTURE: Mode-based control
 * ---------------------------------
 * The greenhouse operates in exactly ONE mode at a time. Each mode defines
 * a complete, consistent set of relay outputs. There are no override layers,
 * no post-hoc mutations, no "pattern table plus exceptions." The mode table
 * IS the truth.
 *
 * This eliminates three classes of bugs that plagued the previous 48-state
 * pattern table design:
 *   1. Open-vent misting (vent open while misters run — wastes 70% of water)
 *   2. Heater/vent oscillation (heater overshoots → vent opens → dumps heat)
 *   3. Fan without vent (negative pressure pulls humid air out through gaps)
 *
 * MODES (priority order, highest wins):
 *   SAFETY_COOL    — temp at absolute max, emergency: all fans + vent open
 *   SAFETY_HEAT    — temp at absolute min, emergency: both heaters, sealed
 *   SEALED_MIST    — VPD above crop band: seal greenhouse, run misters
 *   THERMAL_RELIEF — been sealed too long: brief mandatory vent burst
 *   VENTILATE      — temp above crop band: open vent, run fans
 *   DEHUM_VENT     — VPD below crop band: open vent to dump humidity
 *   IDLE           — everything in band: no active equipment (heaters if cold)
 *
 * KEY DESIGN CHOICE: VENTILATE and SEALED_MIST are mutually exclusive.
 * When VPD needs misting, the greenhouse seals (no cooling).
 * When temp needs cooling, the greenhouse vents (no misting).
 * THERMAL_RELIEF is the pressure valve between them — a brief vent burst
 * to dump accumulated heat before re-sealing.
 *
 * HYSTERESIS: Mode transitions use the crop band's vpd_hysteresis as the
 * EXIT condition. Entry is at the band ceiling; exit is at ceiling - hysteresis.
 * This prevents chattering at the boundary.
 *
 * PLANNER INTEGRATION: The AI planner (Claude Opus 4.6) controls the response
 * SHAPE via 24 Tier-1 tunables (dwell times, thresholds, biases). It does NOT
 * control the mode directly — the mode is determined by physics (sensor readings
 * vs. crop band). The planner adjusts HOW the controller responds.
 */

#include "greenhouse_types.h"

/*
 * determine_mode() — The core decision function.
 *
 * Called every 5 seconds on the ESP32. Takes current sensor readings and
 * setpoints, returns which mode the greenhouse should be in.
 *
 * This function mutates `state` (timers, stage tracking) but has no other
 * side effects. It does not touch hardware.
 *
 * Decision flow:
 *   1. Check safety overrides (temp extremes → immediate action)
 *   2. If in THERMAL_RELIEF, count down relief timer
 *   3. If in SEALED_MIST, check exit conditions (VPD resolved? sealed too long?)
 *   4. If VPD above band AND dwell complete → enter SEALED_MIST
 *   5. If VPD below band → DEHUM_VENT (humidity dump)
 *   6. If temp above band → VENTILATE (cooling)
 *   7. Otherwise → IDLE
 *
 * Parameters:
 *   in      — current sensor readings (temp, VPD, RH, zone sensors, etc.)
 *   sp      — active setpoints (crop band, planner tunables, safety limits)
 *   state   — persistent state across 5s cycles (timers, previous mode)
 *   dt_ms   — elapsed time since last call (typically 5000ms)
 *
 * Returns: the Mode enum value
 */
inline Mode determine_mode(
    const SensorInputs& in,
    const Setpoints& sp,
    ControlState& state,
    uint32_t dt_ms
) {
    // ── Compute effective thresholds ──
    // bias_cool/bias_heat shift the band edges. The planner uses bias_cool=+3
    // on cold nights to widen the gap between temp_high and the VENTILATE trigger,
    // preventing heater-overshoot → vent-open oscillation.
    const float Thigh = sp.temp_high + sp.bias_cool;
    const float Tlow  = sp.temp_low  + sp.bias_heat;
    const float HV    = sp.vpd_hysteresis;

    // ── Evaluate conditions ──
    bool safety_cool    = in.temp_f >= sp.safety_max;   // absolute temp ceiling (default 95°F)
    bool safety_heat    = in.temp_f <= sp.safety_min;   // absolute temp floor (default 45°F)
    bool vpd_above_band = in.vpd_kpa > sp.vpd_high;    // VPD exceeds crop ceiling
    bool vpd_below_exit = in.vpd_kpa < (sp.vpd_high - HV);  // VPD dropped below exit threshold
    bool vpd_too_low    = in.vpd_kpa < (sp.vpd_low - HV) && !sp.econ_block;  // over-humidified
    bool needs_cooling  = in.temp_f > Thigh;            // temp above band (after bias)
    bool in_thermal_relief = (state.mode_prev == THERMAL_RELIEF);
    bool was_sealed        = (state.mode_prev == SEALED_MIST);

    // ── VPD watch dwell ──
    // Before sealing, observe VPD for vpd_watch_dwell_ms (default 60s).
    // This prevents sealing on transient VPD spikes from sensor noise or
    // momentary disturbances (door opening, mist settling).
    // The dwell timer only counts when not already sealed or in relief.
    if (vpd_above_band && state.mode_prev != SEALED_MIST && state.mode_prev != THERMAL_RELIEF) {
        state.vpd_watch_timer_ms += dt_ms;
    } else if (!vpd_above_band && state.mode_prev != SEALED_MIST && state.mode_prev != THERMAL_RELIEF) {
        state.vpd_watch_timer_ms = 0;
    }
    bool vpd_watch_complete = state.vpd_watch_timer_ms >= sp.vpd_watch_dwell_ms;
    bool vpd_wants_seal = vpd_above_band && vpd_watch_complete;

    // ── Priority-ordered mode determination ──
    // Highest priority wins. No fallthrough. No override layers.
    Mode mode = IDLE;

    if (safety_cool) {
        // EMERGENCY: temp at absolute max. Open everything.
        mode = SAFETY_COOL;
        state.sealed_timer_ms = 0;
        state.relief_timer_ms = 0;
    } else if (safety_heat) {
        // EMERGENCY: temp at absolute min. Seal and heat.
        mode = SAFETY_HEAT;
        state.sealed_timer_ms = 0;
    } else if (in_thermal_relief) {
        // We're in a mandatory vent burst. Count down the relief timer.
        // When it expires, return to SEALED_MIST if VPD is still high,
        // or IDLE if VPD resolved during relief.
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
        // We're sealed and misting. Check exit conditions.
        if (vpd_below_exit) {
            // VPD dropped below band - hysteresis → mission accomplished.
            // Exit to VENTILATE if temp is also high, else IDLE.
            mode = needs_cooling ? VENTILATE : IDLE;
            state.sealed_timer_ms = 0;
            state.mist_stage = MIST_WATCH;
            state.vpd_watch_timer_ms = 0;
        } else if (state.sealed_timer_ms >= sp.sealed_max_ms) {
            // Sealed too long (default 600s / 10 min). Mandatory thermal relief.
            // Without this, heat accumulates indefinitely in sealed mode.
            mode = THERMAL_RELIEF;
            state.relief_timer_ms = 0;
        } else {
            // Still sealed, VPD still high, haven't hit max time. Continue.
            mode = SEALED_MIST;
            state.sealed_timer_ms += dt_ms;
        }
    } else if (vpd_wants_seal) {
        // VPD above band and dwell complete. Seal the greenhouse and mist.
        mode = SEALED_MIST;
        state.sealed_timer_ms = 0;
        state.mist_stage = MIST_S1;
    } else if (vpd_too_low) {
        // VPD below band — too humid. Open vent to dump moisture.
        // Blocked if economiser says outdoor air is worse than indoor.
        mode = DEHUM_VENT;
    } else if (needs_cooling) {
        // Temp above band. Open vent and run fans.
        mode = VENTILATE;
    } else {
        // Everything is in band. Nothing to do.
        mode = IDLE;
    }

    // ── VPD safety overrides ──
    // These override the normal priority order for extreme conditions.
    if (in.vpd_kpa > sp.vpd_max_safe && mode != SAFETY_COOL) {
        // VPD at absolute maximum (default 3.0 kPa). Seal immediately,
        // bypass the normal dwell timer.
        mode = SEALED_MIST;
        state.vpd_watch_timer_ms = sp.vpd_watch_dwell_ms;
        state.mist_stage = MIST_S1;
    }
    if (in.vpd_kpa < sp.vpd_min_safe && mode == IDLE) {
        // VPD at absolute minimum (default 0.3 kPa). Vent to dump humidity,
        // unless economiser blocks.
        mode = sp.econ_block ? IDLE : DEHUM_VENT;
    }

    state.mode = mode;
    state.mode_prev = mode;
    return mode;
}

/*
 * resolve_equipment() — Map mode to relay outputs.
 *
 * Pure function: given a mode and current conditions, returns which relays
 * should be on. No side effects.
 *
 * EQUIPMENT TABLE (the mode table IS the truth):
 *
 * | Mode             | Vent | Fans      | Heat1 | Heat2 | Fog     |
 * |------------------|------|-----------|-------|-------|---------|
 * | SAFETY_COOL      | OPEN | BOTH      | off   | off   | allowed |
 * | SAFETY_HEAT      | SHUT | off       | ON    | ON    | off     |
 * | SEALED_MIST      | SHUT | off       | temp  | temp  | escal.  |
 * | THERMAL_RELIEF   | OPEN | LEAD      | off   | off   | off     |
 * | VENTILATE        | OPEN | 1 or 2    | off   | off   | off     |
 * | DEHUM_VENT       | OPEN | LEAD      | off   | off   | off     |
 * | IDLE             | SHUT | off       | temp  | temp  | off     |
 *
 * "temp" = heaters are temperature-dependent within the mode:
 *   Heat1 (electric, 1500W): fires when temp < temp_low + dH2 (pre-heat zone)
 *   Heat2 (gas, 54K BTU):    fires when temp < temp_low (at crop floor)
 *
 * "LEAD" = the current lead fan (rotates every 600s to equalize wear)
 * "1 or 2" = lead fan always on; lag fan added if temp > temp_high + dC2
 *
 * FOG: Only fires as escalation from failed misting (SEALED_MIST mode),
 * gated by: time window (7-17h), RH ceiling (90%), temp floor (55°F),
 * and occupancy. Fog is also allowed in SAFETY_COOL as evaporative assist.
 *
 * Parameters:
 *   mode          — current greenhouse mode
 *   in            — sensor readings (for fog gating and heating decisions)
 *   sp            — setpoints (for heating thresholds)
 *   lead_is_fan1  — which fan is currently lead (rotates every 600s)
 */
inline RelayOutputs resolve_equipment(
    Mode mode,
    const SensorInputs& in,
    const Setpoints& sp,
    bool lead_is_fan1
) {
    // Effective thresholds (same as determine_mode)
    const float Tlow = sp.temp_low + sp.bias_heat;
    const float Thigh = sp.temp_high + sp.bias_cool;

    // Heating sub-decisions (used by SEALED_MIST and IDLE)
    // Heat1 (electric): pre-heats when temp is within dH2 degrees of floor
    // Heat2 (gas): fires at or below the crop floor
    bool needs_heating_s1 = in.temp_f < (Tlow + sp.dH2);
    bool needs_heating_s2 = in.temp_f < Tlow;

    RelayOutputs out = {false, false, false, false, false, false};

    switch (mode) {
        case SAFETY_COOL:
            // Emergency cooling: everything open, all fans, fog as evaporative assist
            out.vent = true;
            out.fan1 = true; out.fan2 = true;
            {
                // Fog allowed during safety cool as evaporative cooling
                // Still gated by time window, RH ceiling, and occupancy
                bool fog_ok = !(in.rh_pct > in.fog_rh_ceiling)
                    && !(in.temp_f < in.fog_min_temp)
                    && (in.local_hour >= in.fog_window_start)
                    && (in.local_hour < in.fog_window_end)
                    && !in.occupancy_inhibit;
                out.fog = fog_ok && in.vpd_kpa > sp.vpd_high;
            }
            break;

        case SAFETY_HEAT:
            // Emergency heating: both heaters, sealed
            out.heat1 = true; out.heat2 = true;
            break;

        case SEALED_MIST:
            // Sealed mode: vent closed, fans off, misters pulsing (controlled
            // by the mister state machine in controls.yaml section 12).
            // Heaters can coexist if temp is also low (cold + dry conditions).
            if (needs_heating_s2) { out.heat1 = true; out.heat2 = true; }
            else if (needs_heating_s1) { out.heat1 = true; }
            // Fog escalation: fires when misters alone can't control VPD
            // Requires: mister_state == S2, duration exceeded, VPD > band + escalation_kpa
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
            // Brief mandatory vent burst to dump accumulated heat.
            // One fan runs to move air. No heating, no misting.
            out.vent = true;
            if (lead_is_fan1) out.fan1 = true; else out.fan2 = true;
            break;

        case VENTILATE: {
            // Cooling mode: vent open, fans on. No misting (vent is open).
            out.vent = true;
            // Second fan added when temp exceeds temp_high + dC2 (stage 2 cooling)
            bool needs_both = in.temp_f > (Thigh + sp.dC2);
            if (lead_is_fan1) { out.fan1 = true; out.fan2 = needs_both; }
            else              { out.fan2 = true; out.fan1 = needs_both; }
            break;
        }

        case DEHUM_VENT:
            // Humidity dump: vent open, fan(s) to move air out.
            // Both fans for extreme over-humidification.
            out.vent = true;
            if (in.vpd_kpa < sp.vpd_low - 2 * sp.vpd_hysteresis) {
                out.fan1 = true; out.fan2 = true;
            } else {
                if (lead_is_fan1) out.fan1 = true; else out.fan2 = true;
            }
            break;

        case IDLE:
            // Nothing to do. Heaters if temp is low (vent stays closed —
            // heater/vent oscillation is structurally impossible because
            // IDLE never opens the vent).
            if (needs_heating_s2) { out.heat1 = true; out.heat2 = true; }
            else if (needs_heating_s1) { out.heat1 = true; }
            // If VPD is low but economiser blocks venting, heat to raise
            // air temp (warmer air holds more moisture → RH drops → VPD rises)
            if (in.vpd_kpa < sp.vpd_low && sp.econ_block) {
                out.heat1 = true; out.heat2 = true;
            }
            break;
    }

    return out;
}
