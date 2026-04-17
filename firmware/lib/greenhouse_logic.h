#pragma once
/*
 * greenhouse_logic.h — Greenhouse Climate Controller Logic
 * =========================================================
 *
 * SINGLE SOURCE OF TRUTH. Same compiled code on ESP32 and x86.
 * ZERO ESPHome dependencies.
 *
 * determine_mode() mutates ControlState (timers, mode_prev, mist_stage).
 * resolve_equipment() is pure (reads only).
 *
 * HARDWARE DEPENDENCIES (enforced by caller, not here):
 *   - Relay min on/off times (ESPHome set_relay with min_on_ms/min_off_ms)
 *   - Gas heater min off time (MIN_HEAT_OFF_MS, typically 300s)
 *   - Vent actuator travel time (ESPHome min_vent_on_s/min_vent_off_s)
 *
 * SENSOR_FAULT: ALL relays off. Freeze protection must be handled by a
 * hardware thermostat wired in parallel, not blind software logic.
 * SENSOR_FAULT does NOT overwrite mode_prev — preserves hysteresis
 * context for graceful recovery from transient I2C glitches.
 *
 * OWNERSHIP: This code owns ControlState.mist_stage. ESPHome/controls.yaml
 * reads mist_stage to drive physical mister relays but does not write it.
 *
 * CONCURRENCY: This code is single-threaded. ControlState must not be
 * accessed from ISRs or other tasks without synchronization.
 */

#include "greenhouse_types.h"

// ── R2-4: Plausibility validation — catches NaN, inf, and garbage ──
inline bool sensors_plausible(const SensorInputs& in) noexcept {
    return std::isfinite(in.temp_f)  && in.temp_f  > -20.0f && in.temp_f  < 140.0f
        && std::isfinite(in.rh_pct)  && in.rh_pct  >= 0.0f  && in.rh_pct  <= 100.0f
        && std::isfinite(in.vpd_kpa) && in.vpd_kpa >= 0.0f  && in.vpd_kpa < 10.0f
        && in.local_hour >= 0        && in.local_hour <= 23;
}

// ── Occupancy blocks ALL moisture injection (fog + misters) ──
// When occupied, do not seal for misting and do not fire fog.
inline bool moisture_blocked_by_occupancy(const SensorInputs& in, const Setpoints& sp) noexcept {
    return sp.occupancy_inhibit && in.occupied;
}

// ═══════════════════════════════════════════════════════════════════
// determine_mode()
// ═══════════════════════════════════════════════════════════════════
inline Mode determine_mode(
    const SensorInputs& in,
    const Setpoints& sp,
    ControlState& state,
    uint32_t dt_ms
) {
    // ── Sentinel check — detect state corruption ──
    if (state.sentinel != STATE_SENTINEL) {
        state = initial_state();
    }

    // ── R2-4: Plausibility guard ──
    if (!sensors_plausible(in)) {
        state.mode = SENSOR_FAULT;
        // R2-2: Preserve mode_prev for recovery hysteresis.
        // But scrub ALL active control state — especially mist_stage,
        // because ESPHome reads mist_stage to drive physical relays.
        // A stale MIST_S2 during SENSOR_FAULT = misters running with no feedback.
        state.mist_stage = MIST_WATCH;
        state.sealed_timer_ms = 0;
        state.relief_timer_ms = 0;
        state.vpd_watch_timer_ms = 0;
        state.mist_stage_timer_ms = 0;
        state.relief_cycle_count = 0;
        return SENSOR_FAULT;
    }

    // ── Capture previous mode BEFORE any logic ──
    const Mode prev = state.mode_prev;

    const float Thigh = sp.temp_high + sp.bias_cool;
    const float HV    = std::min(sp.vpd_hysteresis, sp.vpd_high * 0.5f);

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
        state.vpd_watch_timer_ms = sat_add(state.vpd_watch_timer_ms, dt_ms);
    } else if (!vpd_above_band
        && prev != SEALED_MIST && prev != THERMAL_RELIEF) {
        state.vpd_watch_timer_ms = 0;
        // VPD is below band and we're not in a sealed/relief cycle.
        // Reset the relief cycle breaker so misting can re-engage next time.
        // Without this, hitting max_relief_cycles permanently latches
        // VENTILATE and the greenhouse can never mist again.
        state.relief_cycle_count = 0;
        state.vent_latch_timer_ms = 0;  // FW-8
    }
    bool vpd_wants_seal = vpd_above_band && state.vpd_watch_timer_ms >= sp.vpd_watch_dwell_ms;

    // ── Priority-ordered mode determination ──
    Mode mode = IDLE;
    bool relief_just_expired = false;

    if (safety_cool) {
        mode = SAFETY_COOL;
        state.sealed_timer_ms = 0;
        state.relief_timer_ms = 0;
        state.relief_cycle_count = 0;
        state.vent_latch_timer_ms = 0;  // FW-8
    } else if (safety_heat) {
        mode = SAFETY_HEAT;
        state.sealed_timer_ms = 0;
        state.relief_cycle_count = 0;
    } else if (in_thermal_relief) {
        state.relief_timer_ms = sat_add(state.relief_timer_ms, dt_ms);
        if (state.relief_timer_ms >= sp.relief_duration_ms) {
            state.relief_timer_ms = 0;
            state.sealed_timer_ms = 0;
            state.vpd_watch_timer_ms = 0;
            relief_just_expired = true;
            if (vpd_above_band) state.relief_cycle_count++;
            else state.relief_cycle_count = 0;
        } else {
            mode = THERMAL_RELIEF;
        }
    }

    const bool moisture_blocked = moisture_blocked_by_occupancy(in, sp);

    if (mode != SAFETY_COOL && mode != SAFETY_HEAT && mode != THERMAL_RELIEF) {
        if (was_sealed && !relief_just_expired) {
            // Exit sealed if: VPD resolved, sealed too long, OR someone is present
            if (vpd_below_exit || moisture_blocked) {
                mode = needs_cooling ? VENTILATE : IDLE;
                state.sealed_timer_ms = 0;
                state.vpd_watch_timer_ms = 0;
                state.relief_cycle_count = 0;
                state.vent_latch_timer_ms = 0;  // FW-8
                state.mist_stage = MIST_WATCH;
                state.mist_stage_timer_ms = 0;
            } else if (state.sealed_timer_ms >= sp.sealed_max_ms
                       || in.temp_f >= (sp.safety_max - 5.0f)) {  // FW-7: bail if too hot
                mode = THERMAL_RELIEF;
                state.relief_timer_ms = 0;
            } else {
                mode = SEALED_MIST;
                state.sealed_timer_ms = sat_add(state.sealed_timer_ms, dt_ms);
            }
        // R2-6: Gate seal entry by relief cycle count AND occupancy
        // FW-7: Also gate by temperature — don't seal when within 5°F of safety_max
        } else if (vpd_wants_seal && !moisture_blocked
                   && state.relief_cycle_count < sp.max_relief_cycles
                   && in.temp_f < (sp.safety_max - 5.0f)) {
            mode = SEALED_MIST;
            state.sealed_timer_ms = dt_ms;
            state.mist_stage = MIST_S1;
            state.mist_stage_timer_ms = 0;
            state.vent_latch_timer_ms = 0;  // FW-8: reset on successful seal entry
        } else if (vpd_wants_seal && state.relief_cycle_count >= sp.max_relief_cycles) {
            // R2-6: Exceeded max consecutive sealed→relief. Force vent to break cycle.
            mode = VENTILATE;
            // FW-8: Timeout — if latched >30 min with VPD still above band, try again
            state.vent_latch_timer_ms = sat_add(state.vent_latch_timer_ms, dt_ms);
            if (state.vent_latch_timer_ms >= 1800000) {  // 30 minutes
                state.relief_cycle_count = 0;
                state.vent_latch_timer_ms = 0;
            }
        } else if (vpd_too_low_enter) {
            mode = DEHUM_VENT;
        } else if (was_dehum && !vpd_dehum_exit && !sp.econ_block) {
            // R2-8: Sticky dehum respects econ_block changes mid-cycle
            mode = DEHUM_VENT;
        } else if (needs_cooling) {
            mode = VENTILATE;
        } else {
            mode = IDLE;
        }
    }

    // ── R2-3: VPD dry override — cannot stomp active cooling or safety ──
    {
        const bool can_seal_for_dryness =
            (mode != SAFETY_COOL)
            && (mode != SAFETY_HEAT)
            && (mode != THERMAL_RELIEF)
            && (mode != VENTILATE)
            && !needs_cooling
            && !moisture_blocked
            && (in.temp_f < (Thigh - sp.temp_hysteresis));

        // OBS-1e patch: capture pre-override mode so we can tell whether
        // R2-3 forced a seal the planner's dwell hadn't yet sanctioned.
        const Mode pre_r23_mode = mode;
        state.dry_override_active = false;

        if (in.vpd_kpa > sp.vpd_max_safe && can_seal_for_dryness) {
            mode = SEALED_MIST;
            state.vpd_watch_timer_ms = sp.vpd_watch_dwell_ms;
            state.sealed_timer_ms = dt_ms;
            state.mist_stage = MIST_S1;
            state.mist_stage_timer_ms = 0;
            // Firmware-forced seal: only count as a dry override when the
            // transition was actually forced — if we were already SEALED_MIST
            // via the planner-sanctioned dwell, this R2-3 branch is a no-op
            // and not an override.
            state.dry_override_active = (pre_r23_mode != SEALED_MIST);
        }
    }
    if (in.vpd_kpa < sp.vpd_min_safe && mode == IDLE) {
        mode = sp.econ_block ? IDLE : DEHUM_VENT;
    }

    // ── Mist stage progression ──
    if (mode == SEALED_MIST) {
        // Occupancy blocks ALL moisture — freeze mist stage if occupied
        if (moisture_blocked) {
            state.mist_stage = MIST_WATCH;
            state.mist_stage_timer_ms = 0;
        } else {
            state.mist_stage_timer_ms = sat_add(state.mist_stage_timer_ms, dt_ms);
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
                case MIST_S2: {
                    bool fog_gated = (in.rh_pct > sp.fog_rh_ceiling)
                        || (in.temp_f < sp.fog_min_temp)
                        || (in.local_hour < sp.fog_window_start)
                        || (in.local_hour >= sp.fog_window_end)
                        || moisture_blocked_by_occupancy(in, sp);
                    if (in.vpd_kpa > sp.vpd_high + sp.fog_escalation_kpa && !fog_gated) {
                        state.mist_stage = MIST_FOG;
                        state.mist_stage_timer_ms = 0;
                    }
                    if (in.vpd_kpa < sp.vpd_high - HV) {
                        state.mist_stage = MIST_S1;
                        state.mist_stage_timer_ms = 0;
                    }
                    break;
                }
                case MIST_FOG:
                    if (in.vpd_kpa <= sp.vpd_high + sp.fog_escalation_kpa) {
                        state.mist_stage = MIST_S2;
                        state.mist_stage_timer_ms = 0;
                    }
                    break;
                default:
                    state.mist_stage = MIST_WATCH;
                    state.mist_stage_timer_ms = 0;
                    break;
            }
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
// evaluate_overrides() — Pure function. OBS-1e (Sprint 16).
//
// Inspects the just-resolved mode + state + inputs and flags each
// firmware-side decision that blocks or supersedes planner intent.
// Every flag is "desire-triggered" — only fires when the planner
// would have wanted the blocked action, not every cycle the
// condition technically holds. Evaluator is pure: no state mutation.
// ═══════════════════════════════════════════════════════════════════
inline OverrideFlags evaluate_overrides(
    const SensorInputs& in,
    const Setpoints& sp,
    const ControlState& state,
    Mode mode
) noexcept {
    OverrideFlags f{};
    if (!sensors_plausible(in)) return f;

    const float HV = std::min(sp.vpd_hysteresis, sp.vpd_high * 0.5f);
    const bool vpd_above_band = in.vpd_kpa > sp.vpd_high;
    const bool vpd_wants_seal =
        vpd_above_band && state.vpd_watch_timer_ms >= sp.vpd_watch_dwell_ms;
    const bool moisture_blocked = moisture_blocked_by_occupancy(in, sp);

    // Occupancy: fired when a seal is active OR the dwell has matured and
    // misting WOULD have started — but occupancy is blocking moisture.
    f.occupancy_blocks_moisture =
        moisture_blocked && (mode == SEALED_MIST || vpd_wants_seal);

    // Fog gates — only meaningful while in MIST_S2 and VPD has climbed far
    // enough that the firmware would escalate to MIST_FOG. Any one of the
    // three gates blocks that transition.
    const bool fog_wanted =
        (mode == SEALED_MIST)
        && (state.mist_stage == MIST_S2)
        && (in.vpd_kpa > sp.vpd_high + sp.fog_escalation_kpa);
    f.fog_gate_rh     = fog_wanted && (in.rh_pct  > sp.fog_rh_ceiling);
    f.fog_gate_temp   = fog_wanted && (in.temp_f  < sp.fog_min_temp);
    f.fog_gate_window = fog_wanted
        && ((in.local_hour <  sp.fog_window_start)
         || (in.local_hour >= sp.fog_window_end));

    // Relief-cycle breaker: firmware forces VENTILATE instead of the seal
    // the planner's dwell was setting up.
    f.relief_cycle_breaker =
        vpd_wants_seal && state.relief_cycle_count >= sp.max_relief_cycles;

    // Seal blocked by temp: within 5°F of safety_max means the firmware
    // refuses to close the vents for VPD misting.
    f.seal_blocked_temp =
        vpd_wants_seal && in.temp_f >= (sp.safety_max - 5.0f);

    // VPD dry override: read the flag determine_mode() sets in its R2-3
    // path. Cannot be reconstructed post-hoc because R2-3 matures the
    // dwell timer in the same cycle it fires, so `!vpd_wants_seal` is
    // false by the time evaluate_overrides() sees state.
    f.vpd_dry_override = state.dry_override_active;

    (void)HV;  // reserved for future hysteresis-sensitive gates
    return f;
}

// ═══════════════════════════════════════════════════════════════════
// resolve_equipment() — Pure function. No side effects.
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

    bool needs_heating_s1 = in.temp_f < (Tlow + sp.heat_hysteresis);
    bool needs_heating_s2 = in.temp_f < (Tlow - sp.dH2);

    RelayOutputs out = {false, false, false, false, false, false};

    switch (mode) {
        case SENSOR_FAULT:
            // R2-1: ALL relays off. No actuator should run without sensor feedback.
            // Freeze protection: hardware thermostat wired in parallel.
            break;

        case SAFETY_COOL:
            out.vent = true;
            out.fan1 = true; out.fan2 = true;
            {
                // R2-5: Check live occupancy, not just config flag
                bool fog_ok = !(in.rh_pct > sp.fog_rh_ceiling)
                    && !(in.temp_f < sp.fog_min_temp)
                    && (in.local_hour >= sp.fog_window_start)
                    && (in.local_hour < sp.fog_window_end)
                    && !moisture_blocked_by_occupancy(in, sp);
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
                // R2-5: Check live occupancy for fog output
                out.fog = (state.mist_stage == MIST_FOG) && !fog_gated
                    && !moisture_blocked_by_occupancy(in, sp);
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
            // FW-9b: VPD emergency — fire fog even while venting (full battery)
            if (in.vpd_kpa > sp.vpd_max_safe && !moisture_blocked_by_occupancy(in, sp)) {
                bool fog_ok = !(in.rh_pct > sp.fog_rh_ceiling)
                    && !(in.temp_f < sp.fog_min_temp)
                    && (in.local_hour >= sp.fog_window_start)
                    && (in.local_hour < sp.fog_window_end);
                out.fog = fog_ok;
            }
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

        default:
            // Corrupted mode — all off (same as SENSOR_FAULT)
            break;
    }

    return out;
}
