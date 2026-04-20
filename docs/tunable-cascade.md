# Tunable Cascade — End-to-End Spec

**Status:** Skeleton 2026-04-20 (`1aadcec`). Control-loop rows completed 2026-04-20 (sprint-13). Non-control-loop rows (irrigation, grow lights, switches) still stubbed.

**Purpose:** Single source of truth mapping every tunable through every layer it touches. Pydantic schema → DB column → dispatcher route → firmware struct field → firmware use site → cfg_* readback → default value → valid range → owner (who sets it) → cascade timing.

**Why it exists now:** sprint-10 day/night incident + bias_heat drift + MIDNIGHT label-mismatch + sprint-12 edge-targeting rewrite are all symptoms of the same missing spec. Every sprint has added or rewired tunables without extending this table, and each silent-override bug has been a consequence.

## Known open issues (as of 2026-04-20)

### ✅ Edge-targeting bug — FIXED in sprint-12 (commit `49fbc6b`)

Pre-sprint-12 firmware targeted the **lower edge** of the band:
```c
// determine_mode() prior to sprint-12
bool needs_heating_s1 = in.temp_f < (Tlow + sp.heat_hysteresis);   // Tlow = temp_low + bias_heat
bool needs_cooling    = in.temp_f > (Thigh);                        // Thigh = temp_high + bias_cool
```

With `temp_low=62, bias_heat=0, heat_hysteresis=1`, effective heating target was 63°F — plants pinned at 61.9–62.2°F overnight 4/18 because the target was 1°F inside the lower edge.

Post-sprint-12 (`greenhouse_logic.h:117-124`, `greenhouse_logic.h:469-477`):
```c
const float band_width = std::max(2.0f, sp.temp_high - sp.temp_low);
const float Tlow  = sp.temp_low  + band_width * 0.25f + sp.bias_heat;   // interior
const float Thigh = sp.temp_high - band_width * 0.25f + sp.bias_cool;   // interior
const float vpd_width    = std::max(0.2f, sp.vpd_high - sp.vpd_low);
const float vpd_low_eff  = sp.vpd_low  + vpd_width * 0.25f;
const float vpd_high_eff = sp.vpd_high - vpd_width * 0.25f;
```

Heating target is now 25% inside the band from the lower edge, cooling 25% inside from the upper edge. Plants operate in the middle 50% of the dispatcher-pushed band. With `temp_low=62, temp_high=75`: heating target ≈ 65.25°F (was 63), cooling target ≈ 71.75°F (was 75). Same math applied to VPD.

**bias_heat / bias_cool semantics shift:** they now offset the INTERIOR target, not pull the edge trigger. Planner prompts must reflect this (see "Planner context pack" section below).

**Remaining follow-ups:** iterate the 25% fraction if 30-day post-sprint-12 data shows over- or under-shooting. Retire `bias_heat` / `bias_cool` once the planner is retrained.

### 🟡 Readback gap — 9 parameters push without verification

`d_heat_stage_2`, `d_cool_stage_2`, mister pulse/budget durations (`mister_pulse_on_s`, `mister_pulse_gap_s`, `mister_water_budget_gal`, `mister_on_s`, `mister_off_s`, `mister_all_on_s`, `mister_all_off_s`), fog escalation (`fog_burst_min`), relay burst timers. No `cfg_*` sensors → sprint-20 confirmation loop cannot verify. Silent push corruption is undetectable.

## Column reference

| Column | Meaning |
|---|---|
| Param | Canonical name in `verdify_schemas.tunables.ALL_TUNABLES` |
| Type | `num` (NUMERIC_TUNABLES) or `sw` (SWITCH_TUNABLES, 0.0/1.0) |
| Pydantic | Module where the value is validated (`plan.py PlanTransition`, `setpoint.py SetpointChange`, etc) |
| DB | Where it's persisted (`setpoint_changes`, `setpoint_plan`, `setpoint_snapshot`) |
| Dispatcher route | `PARAM_TO_ENTITY` / `SWITCH_TO_ENTITY` → ESP32 entity id |
| FW struct | `Setpoints.*` field in `firmware/lib/greenhouse_types.h` |
| FW use | Where `sp.*` is consumed in `greenhouse_logic.h` or `controls.yaml` |
| cfg_* readback | `CFG_READBACK_MAP` entry or NONE |
| Default | Compiled firmware default from `greenhouse_types.h::defaults_setpoints()` |
| Valid range | Clamp bounds on dispatcher push + firmware ingest |
| Owner | Who sets it: `planner` (Iris), `crop` (crop_target_profiles), `operator` (manual), `fw-default` |
| Cascade | Propagation speed: `immediate` (push → ESP32 within 5 min), `next-cycle`, `deferred` |

---

## Temperature band (5 tunables, all critical) — FULLY SPEC'D

Post-sprint-12 interior-target semantics: heating fires below `Tlow + heat_hysteresis` where `Tlow = temp_low + (temp_high - temp_low)*0.25 + bias_heat`. Cooling fires above `Thigh = temp_high - (temp_high - temp_low)*0.25 + bias_cool`. The interior target is always 25% of the band width inward from each edge.

| Param | Type | Pydantic | DB | Dispatcher route | FW struct | FW use | cfg_* readback | Default | Valid range | Owner | Cascade |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `temp_low` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_plan`, `setpoint_changes` | `target_temp_low_f` | `Setpoints.temp_low` | `greenhouse_logic.h:117-118,471-472` band lower edge — heating target computed 25% inside this edge | `cfg_temp_low_f` | 40°F (wide; dispatcher narrows) | [30, 80] | crop (band) + planner (override, clamped) | immediate (≤5 min) |
| `temp_high` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_plan`, `setpoint_changes` | `target_temp_high_f` | `Setpoints.temp_high` | `greenhouse_logic.h:117,119,471,473` band upper edge — cooling target computed 25% inside this edge | `cfg_temp_high_f` | 95°F (wide; dispatcher narrows) | [40, 100] | crop (band) + planner (override, clamped) | immediate |
| `d_heat_stage_2` (aka `dH2`) | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_d_heat_stage_2_f` | `Setpoints.dH2` | `greenhouse_logic.h:143-152` S2 latch threshold — gas heater kicks in at `Tlow - dH2`, releases at `Tlow + heat_hysteresis` | ⚠️ **NONE** (readback gap) | 5.0°F | [0, 10] | operator / fw-default | immediate but unverified |
| `d_cool_stage_2` (aka `dC2`) | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_d_cool_stage_2_f` | `Setpoints.dC2` | `greenhouse_logic.h:521` second-fan threshold — fan2 engages at `Thigh + dC2` during VENTILATE | ⚠️ **NONE** (readback gap) | 3.0°F | [0, 10] | operator / fw-default | immediate but unverified |
| `temp_hysteresis` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_hyst_temp_f` | `Setpoints.temp_hysteresis` | `greenhouse_logic.h:138` ventilate-exit hysteresis (only applies if `was_ventilating`) — prevents churn near cooling target | `cfg_hyst_temp_f` | 1.5°F | [0.5, 3.0] | operator / fw-default | immediate |
| `heat_hysteresis` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_heat_hysteresis_f` | `Setpoints.heat_hysteresis` | `greenhouse_logic.h:153,472` S1 exit threshold + heat2 latch release — heater turns off when `temp ≥ Tlow + heat_hysteresis` | ⚠️ **NONE** (readback gap) | 1.0°F | [0, 3] | operator / fw-default | immediate but unverified |

## Bias / offsets (2 tunables, semantics changed in sprint-12) — FULLY SPEC'D

⚠️ **Sprint-12 semantics shift:** `bias_heat` / `bias_cool` now offset the INTERIOR target (25% inside the band), not the band edge itself. A `bias_heat=+2` shifts the heating target from `temp_low + band_width/4` to `temp_low + band_width/4 + 2`. To revert to edge-like targeting, operator can push `bias_heat = -band_width/4`. Pre-sprint-12 planner prompts that described "bias_heat pulls the edge trigger up" are now wrong.

| Param | Type | Pydantic | DB | Dispatcher route | FW struct | FW use | cfg_* readback | Default | Valid range | Owner | Cascade |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `bias_heat` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_bias_heat_f` | `Setpoints.bias_heat` | `greenhouse_logic.h:118,150,472` symmetric offset from interior heating target | `cfg_bias_heat_f` | 0°F | [-10, 10] | operator (sets once) + planner | immediate |
| `bias_cool` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_bias_cool_f` | `Setpoints.bias_cool` | `greenhouse_logic.h:120,473` symmetric offset from interior cooling target | `cfg_bias_cool_f` | 0°F | [-10, 10] | operator + planner | immediate |

## VPD band (3 tunables) — FULLY SPEC'D

Same sprint-12 interior-target math as temperature: SEALED_MIST fires above `vpd_high_eff = vpd_high - (vpd_high - vpd_low)*0.25`. DEHUM_VENT fires below `vpd_low_eff - HV` where `HV = min(vpd_hysteresis, vpd_high_eff * 0.5)`. Mist stage escalations (S1→S2, S2→FOG) use `vpd_high_eff`, not raw `vpd_high`.

| Param | Type | Pydantic | DB | Dispatcher route | FW struct | FW use | cfg_* readback | Default | Valid range | Owner | Cascade |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `vpd_low` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_plan`, `setpoint_changes` | `target_vpd_low_kpa` | `Setpoints.vpd_low` | `greenhouse_logic.h:122-123,475-476` band lower edge — DEHUM target 25% inside | `cfg_vpd_low_kpa` | 0.35 kPa (wide) | [0.1, 1.0] | crop (band) + planner (override, clamped) | immediate |
| `vpd_high` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_plan`, `setpoint_changes` | `target_vpd_high_kpa` | `Setpoints.vpd_high` | `greenhouse_logic.h:122,124,475,477` band upper edge — SEALED/mist target 25% inside | `cfg_vpd_high_kpa` | 2.80 kPa (wide) | [0.4, 3.0] | crop (band) + planner (override, clamped) | immediate |
| `vpd_hysteresis` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_hyst_vpd_kpa` | `Setpoints.vpd_hysteresis` | `greenhouse_logic.h:125` HV cap for seal/dehum exit — prevents mist-stage chatter around `vpd_high_eff` | `cfg_hyst_vpd_kpa` | 0.3 kPa | [0.05, 1.0] | operator / fw-default | immediate |
| `dehum_aggressive_kpa` | num | (hardcoded; no Pydantic entry) | — | — (firmware default) | `Setpoints.dehum_aggressive_kpa` | `greenhouse_logic.h:544` DEHUM_VENT fires both fans if `vpd < vpd_low_eff - dehum_aggressive_kpa` | ⚠️ **NONE** | 0.3 kPa | must be < vpd_low | fw-default | N/A (not dispatcher-pushable) |

## Safety rails (4 tunables, CANNOT be overridden past clamp bounds) — FULLY SPEC'D

Safety rails reference RAW `sp.safety_*` values (not interior-eff). They exist to stop the greenhouse from killing plants when the main control band fails or the dispatcher goes silent. If the dispatcher never pushes a band, the firmware defaults are permissively wide (temp 40–95°F, vpd 0.35–2.80 kPa) so safety rails are the only active constraint.

| Param | Type | Pydantic | DB | Dispatcher route | FW struct | FW use | cfg_* readback | Default | Valid range | Owner | Cascade |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `safety_min` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_plan`, `setpoint_changes` | `target_safety_min_f` | `Setpoints.safety_min` | `greenhouse_logic.h:128` SAFETY_HEAT fires both heaters + lead fan if `temp ≤ safety_min`. Validate clamp: `safety_min ≤ temp_low - 5` | `cfg_safety_min_f` | 35°F | [30, 60] clamped | operator (rarely changed) + planner (within range) | immediate |
| `safety_max` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_plan`, `setpoint_changes` | `target_safety_max_f` | `Setpoints.safety_max` | `greenhouse_logic.h:127` SAFETY_COOL fires both fans + vent if `temp ≥ safety_max`. Validate: `safety_max ≥ temp_high + 5` | `cfg_safety_max_f` | 100°F | [80, 110] clamped | operator | immediate |
| `safety_vpd_min` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_safety_vpd_min_kpa` | `Setpoints.vpd_min_safe` | `greenhouse_logic.h:320-334` DEHUM_VENT force trigger (overrides SEALED_MIST/IDLE); Validate: `vpd_min_safe ≤ vpd_low - 0.05` | `cfg_safety_vpd_min_kpa` | 0.3 kPa | [0.1, 1.5] | operator | immediate |
| `safety_vpd_max` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_safety_vpd_max_kpa` | `Setpoints.vpd_max_safe` | `greenhouse_logic.h:294` R2-3 dry override — firmware forces SEALED_MIST even without planner dwell if `vpd > vpd_max_safe`. Also fires fog in VENTILATE mode (`:528`). Validate: `vpd_max_safe ≥ vpd_high + 0.1` | `cfg_safety_vpd_max_kpa` | 3.0 kPa | [2.5, 3.0] | operator | immediate |

## Per-zone VPD targets (4 tunables) — FULLY SPEC'D

| Param | Type | Pydantic | DB | Dispatcher route | FW struct | FW use | cfg_* readback | Default | Valid range | Owner | Cascade |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `vpd_target_south` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_vpd_target_south_kpa` | `Setpoints.vpd_target_south` | Mister zone selection priority (south zone) | `cfg_vpd_target_south_kpa` | 1.5 | [0.3, 2.5] | crop (via `fn_zone_vpd_targets`) | immediate |
| `vpd_target_west` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_vpd_target_west_kpa` | `Setpoints.vpd_target_west` | Mister zone selection (west) | `cfg_vpd_target_west_kpa` | 1.5 | [0.3, 2.5] | crop | immediate |
| `vpd_target_east` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_vpd_target_east_kpa` | `Setpoints.vpd_target_east` | Mister zone selection (east) | `cfg_vpd_target_east_kpa` | 1.5 | [0.3, 2.5] | crop | immediate |
| `vpd_target_center` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_vpd_target_center_kpa` | `Setpoints.vpd_target_center` | Mister zone selection (center) | `cfg_vpd_target_center_kpa` | 1.5 | [0.3, 2.5] | crop | immediate |

## Mister engagement thresholds (2 tunables) — FULLY SPEC'D

These are zone-scoring tunables consumed by `controls.yaml`'s mister dispatcher, NOT by `determine_mode()`. Firmware uses them to decide WHICH zone to mist when SEALED_MIST is active, not WHETHER to enter SEALED_MIST.

| Param | Type | Pydantic | DB | Dispatcher route | FW struct | FW use | cfg_* readback | Default | Valid range | Owner | Cascade |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `mister_engage_kpa` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_mister_engage_kpa` | (controls.yaml global, not in Setpoints) | Zone-level mist engagement threshold in `controls.yaml` mister dispatcher | `cfg_mister_engage_kpa` | 1.6 kPa | [0.6, 2.5] | planner | immediate |
| `mister_all_kpa` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_mister_all_kpa` | (controls.yaml global) | Zone-level "fire all zones" threshold | `cfg_mister_all_kpa` | 1.9 kPa | [0.9, 3.0] | planner | immediate |

## Mist stage timers + thresholds (5 Setpoints fields, 2 dispatcher-pushable) — FULLY SPEC'D

Timers inside the SEALED_MIST state machine. Collectively they define how fast the firmware escalates from MIST_WATCH → MIST_S1 → MIST_S2 → MIST_FOG, how long a seal can run before THERMAL_RELIEF fires, and how long the watch-dwell holds before a seal is committed.

| Param | Type | Pydantic | DB | Dispatcher route | FW struct | FW use | cfg_* readback | Default | Valid range | Owner | Cascade |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `vpd_watch_dwell_s` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_vpd_watch_dwell_s` | `Setpoints.vpd_watch_dwell_ms` (×1000) | `greenhouse_logic.h:181-184` dwell required in VPD_WATCH before SEALED_MIST commits. Prevents seal from firing on transient VPD spikes | ⚠️ **NONE** | 60 s | [15, 120] | operator + planner | immediate but unverified |
| `mister_all_delay_s` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_mister_all_delay_s` | `Setpoints.mist_s2_delay_ms` (×1000) | `greenhouse_logic.h:346` dwell inside MIST_S1 before S2 escalation. Gas for "warn before escalating" | ⚠️ **NONE** | 300 s (5 min) | [60, 900] | operator + planner | immediate but unverified |
| `sealed_max_ms` | (FW-internal) | — | — | — | `Setpoints.sealed_max_ms` | `greenhouse_logic.h:232` max SEALED_MIST duration before forced THERMAL_RELIEF | ⚠️ **NONE** | 600 s (10 min) | [60, 1800] s | fw-default | N/A (dispatcher maps via `mist_max_closed_vent_s`) |
| `relief_duration_ms` | (FW-internal) | — | — | — | `Setpoints.relief_duration_ms` | `greenhouse_logic.h:206` minimum THERMAL_RELIEF duration before re-evaluation | ⚠️ **NONE** | 90 s | [15, 600] s | fw-default | N/A |
| `max_relief_cycles` | (FW-internal) | — | — | — | `Setpoints.max_relief_cycles` | `greenhouse_logic.h:243-261` max consecutive SEALED→RELIEF cycles before vent-latch forces VENTILATE (R2-6 cycle breaker) | ⚠️ **NONE** | 3 | [1, 10] | fw-default | N/A |
| `fog_escalation_kpa` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_fog_escalation_kpa` | `Setpoints.fog_escalation_kpa` | `greenhouse_logic.h:355,366` VPD delta above `vpd_high_eff` that escalates MIST_S2 → MIST_FOG | ⚠️ **NONE** | 0.4 kPa | [0.1, 1.0] | operator + planner | immediate but unverified |

## Fog gates (4 tunables, all ops-facing) — FULLY SPEC'D

Fog requires all four gates open. Each gate blocks fog independently and fires a distinct `override_events` row via `evaluate_overrides()` when the state machine wanted to escalate but was blocked.

| Param | Type | Pydantic | DB | Dispatcher route | FW struct | FW use | cfg_* readback | Default | Valid range | Owner | Cascade |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `fog_rh_ceiling_pct` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_fog_rh_ceiling_pct` | `Setpoints.fog_rh_ceiling` | `greenhouse_logic.h:69-71,426` fog blocked if `rh_pct > fog_rh_ceiling` — prevents fog from driving condensation | ⚠️ **NONE** | 90 % | [75, 98] | operator | immediate but unverified |
| `fog_min_temp_f` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_fog_min_temp_f` | `Setpoints.fog_min_temp` | `greenhouse_logic.h:70,427` fog blocked if `temp < fog_min_temp` — prevents chilling cold air | ⚠️ **NONE** | 55 °F | [40, 65] | operator | immediate but unverified |
| `fog_window_start` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_fog_window_start` | `Setpoints.fog_window_start` | `greenhouse_logic.h:61-63,429` fog blocked outside `[fog_window_start, fog_window_end)` — midnight-wrap-aware | ⚠️ **NONE** | 7 (7 AM) | [0, 23] | operator | immediate but unverified |
| `fog_window_end` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_fog_window_end` | `Setpoints.fog_window_end` | Same as above — end of fog-permitted hour window | ⚠️ **NONE** | 17 (5 PM) | [0, 23] | operator | immediate but unverified |

## Seal / VPD safety margin timers (sprint-10 0.4b extractions) — FULLY SPEC'D

These three fields were hardcoded constants pre-sprint-10; now Setpoints fields. Clamped by `validate_setpoints` but still dispatcher-pushable via the planner.

| Param | Type | Pydantic | DB | Dispatcher route | FW struct | FW use | cfg_* readback | Default | Valid range | Owner | Cascade |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `vent_latch_timeout_s` | (FW-internal, sprint-10-pushable) | — | — | (no route yet) | `Setpoints.vent_latch_timeout_ms` (÷1000) | `greenhouse_logic.h:254-259` FW-8 relief-cycle-breaker timeout — resets `relief_cycle_count` after `vent_latch_timeout` if still in forced VENTILATE | ⚠️ **NONE** | 1800 s (30 min) | [60, 3600] s | fw-default | N/A (not yet routed) |
| `safety_max_seal_margin_f` | (FW-internal) | — | — | (no route yet) | `Setpoints.safety_max_seal_margin_f` | `greenhouse_logic.h:232,248,439` firmware refuses to close vents for SEALED_MIST when `temp ≥ safety_max - margin` (default 5°F below safety_max) | ⚠️ **NONE** | 5.0 °F | [2, 15] | fw-default | N/A |
| `econ_heat_margin_f` | (FW-internal) | — | — | (no route yet) | `Setpoints.econ_heat_margin_f` | `greenhouse_logic.h:565` IDLE econ heat fires electric heat if `vpd < vpd_low_eff && econ_block && temp < Thigh - econ_heat_margin`. Reduces wasted heat at the top of the band | ⚠️ **NONE** | 5.0 °F | [2, 15] | fw-default | N/A |

## Occupancy + economizer flags (2 tunables, control-loop blockers) — FULLY SPEC'D

Boolean switches that completely block moisture or venting. Firmware reads these every cycle.

| Param | Type | Pydantic | DB | Dispatcher route | FW struct | FW use | cfg_* readback | Default | Valid range | Owner | Cascade |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `sw_occupancy_inhibit` | sw | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `switch.occupancy_inhibit` | `Setpoints.occupancy_inhibit` (computed with `in.occupied`) | `greenhouse_logic.h:45-47` blocks ALL moisture injection (mist + fog) when greenhouse is occupied; fires `override_events.occupancy_blocks_moisture` when mist was wanted | `cfg_occupancy_inhibit` | false | bool | operator | immediate |
| `sw_economiser_enabled` | sw | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `switch.economiser_enabled` | (controls.yaml computes `econ_block`) | When enabled + outdoor enthalpy gate closed, firmware's `Setpoints.econ_block` = true. Blocks DEHUM_VENT entry; allows electric-only econ heat | `cfg_economiser_enabled` | true | bool | operator | immediate |

## Remaining tunables — TBD (not control-loop-critical; stubbed for later)

The remaining ~50 tunables are organized below by category. Each needs the full row treatment. **Default values, ranges, FW use sites, and cfg_* readback presence will be filled in week of 2026-04-20.**

### Mister pulse + timing (9 tunables, readback gap suspected)
- `mister_engage_delay_s`, `mister_all_delay_s`, `mister_on_s`, `mister_off_s`, `mister_all_on_s`, `mister_all_off_s`, `mister_pulse_on_s`, `mister_pulse_gap_s`, `mister_max_runtime_min`
- `mister_water_budget_gal`, `mister_vpd_weight`

### Equipment timing — relay min on/off (8 tunables)
- `min_heat_on_s`, `min_heat_off_s`, `min_fan_on_s`, `min_fan_off_s`, `min_vent_on_s`, `min_vent_off_s`, `lead_rotate_s`, `fan_burst_min`, `vent_bypass_min`, `fog_burst_min`

### Firmware internal (1 tunable)
- `fallback_window_s` — sensor staleness → firmware reboot threshold

### Economiser (3 tunables)
- `enthalpy_open`, `enthalpy_close`, `site_pressure_hpa`

### Irrigation — wall (7 tunables)
- `irrig_wall_start_hour`, `irrig_wall_start_min`, `irrig_wall_duration_min`, `irrig_wall_fert_duration_min`, `irrig_wall_fert_every_n`, `irrig_wall_flush_min`, `irrig_wall_interval_days`

### Irrigation — center (7 tunables)
- `irrig_center_start_hour`, `irrig_center_start_min`, `irrig_center_duration_min`, `irrig_center_fert_duration_min`, `irrig_center_fert_every_n`, `irrig_center_flush_min`, `irrig_center_interval_days`

### VPD boost (2 tunables)
- `irrig_vpd_boost_pct`, `irrig_vpd_boost_threshold_hrs`

### Grow lights (4 tunables)
- `gl_dli_target`, `gl_lux_threshold`, `gl_sunrise_hour`, `gl_sunset_hour`

### Switches (7 tunables, 0.0/1.0)
- `sw_economiser_enabled`, `sw_fog_closes_vent`, `sw_gl_auto_mode`, `sw_irrigation_enabled`, `sw_irrigation_wall_enabled`, `sw_irrigation_center_enabled`, `sw_irrigation_weather_skip`, `sw_occupancy_inhibit`

### Known routing gaps
- `sw_mister_closes_vent` — exists as ESP32 switch + cfg readback, NOT in SETPOINT_MAP. Dispatcher cannot push. Sprint-21 follow-up unresolved.

## Historical impact (30-day observed behavior, pre-sprint-12)

Data pulled 2026-04-20 from `setpoint_snapshot`, `equipment_state`, `override_events`, `daily_summary`, and `climate` over the trailing 30 days. Everything below is **pre-sprint-12 behavior** — the sprint-12 shift to interior targeting will change these numbers materially over the next 30 days; this section is the baseline to compare against.

### Observed parameter ranges (`setpoint_snapshot`, 30 d, n ≈ 33 732 samples each)

| Param | Min | Avg | Max | Std dev | Note |
|---|---:|---:|---:|---:|---|
| `temp_low` | 55.0°F | 62.4°F | 75.5°F | 5.1 | Dispatcher actively modulates with crop phase / diurnal pattern. |
| `temp_high` | 0°F | 76.1°F | 82.0°F | 6.7 | Min=0 indicates ≥1 pre-clamp push of 0 reached the snapshot. Needs follow-up. |
| `vpd_low` | 0 | 0.31 kPa | 0.95 | 0.30 | Same 0-min concern. |
| `vpd_high` | 0.60 | 1.32 kPa | 2.50 | 0.54 | Reasonable. |
| `temp_hysteresis` | 1.0 | 1.60 | 2.0 | 0.48 | Within expected range. |
| `vpd_hysteresis` | 0.10 | 0.29 | 0.40 | 0.05 | Tight. |
| `bias_heat` | 0 | **0.73** | 5.0 | 1.32 | ⚠️ Frequently 0. When zero on a heating-dominated night, the pre-sprint-12 controller pins at the lower edge. Root cause of the 4/18 overnight incident. |
| `bias_cool` | −1.0 | 1.07 | 5.0 | 1.56 | Negative values observed — planner was apparently compensating for edge-targeting by pushing bias_cool below zero on some days. |
| `safety_min` | 0 | 27.9 | 45.0 | 18.7 | Min=0 suggests stale pushes. Real operational value ~40. |
| `safety_max` | 0 | 93.3 | 100.0 | 10.3 | Same 0-min anomaly. |
| `safety_vpd_min` | 0 | 0.27 | 0.30 | 0.07 | Mostly 0.30 with rare pre-clamp zeros. |
| `safety_vpd_max` | 0 | 2.57 | 3.0 | 0.41 | Mostly 3.0. |
| `mister_engage_kpa` | 0.6 | 1.48 | 2.2 | 0.17 | Pushed from crop profile — tracks crop stress targets. |
| `mister_all_kpa` | 0.9 | 1.82 | 2.6 | 0.20 | Tracks mister_engage_kpa with ~0.3 offset. |
| `vpd_target_south` | 1.00 | 1.24 | 1.84 | 0.28 | Pushed by `fn_zone_vpd_targets` per active crop profile. |
| `vpd_target_west` | 1.20 | 1.20 | 1.20 | 0.00 | ⚠️ Stuck at 1.20 — `fn_zone_vpd_targets` may not be pushing west dynamically. |
| `vpd_target_east` | 0.55 | 0.89 | 1.40 | 0.31 | Dynamic. |
| `vpd_target_center` | 0.58 | 0.82 | 1.20 | 0.23 | Dynamic. |

**Follow-ups identified by the range scan:**
1. `temp_high`, `vpd_low`, `safety_*` have min=0 in setpoint_snapshot. Most likely from the ~1 min immediately after reboot before first dispatcher push. If those values actually reached determine_mode() they'd have driven the controller hard. Sprint-13 task: dispatcher should mark pre-first-push snapshots as `source='uninitialized'` and exclude from range reports.
2. `vpd_target_west` has 0 variance over 30 days. Either it's truly constant for the current crop, or the dispatcher route is broken. Cross-check with `fn_zone_vpd_targets(now())` expected output.
3. `bias_heat` mean 0.73 is lower than the intended operational mean of ~3–5°F. Confirms the 4/18 overnight root cause: bias was not reliably pushed.

### Equipment duty (`daily_summary`, 14-day trailing)

| Date | heat1 h | heat2 h | fan h | vent h | fog h | cycles heat1/heat2 | cycles fog/vent | tmin-tmax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026-04-20 | 12.19 | 9.00 | 6.95 | 4.93 | 1.71 | 8 / 8 | 0 / 6 | 54–90 |
| 2026-04-19 | 11.91 | 3.93 | 6.67 | 4.81 | 1.64 | 15 / 44 | 62 / 39 | 54–90 |
| 2026-04-18 | 15.61 | 4.98 | 2.92 | 2.13 | 0.61 | 9 / 44 | 30 / 29 | 60–89 |
| 2026-04-17 | **20.90** | 11.11 | 1.95 | 1.32 | 0.00 | 30 / 60 | 0 / 29 | 52–78 |
| 2026-04-16 | 7.81 | 0.89 | 3.99 | 3.20 | 0.77 | 17 / 14 | 38 / 50 | 59–91 |
| 2026-04-15 | **21.00** | 3.40 | 0.67 | 0.36 | 0.00 | 13 / 34 | 47 / 30 | 58–92 |
| 2026-04-14 | **21.41** | 2.87 | 1.45 | 1.04 | 0.00 | 24 / 42 | 0 / 24 | 59–74 |
| 2026-04-13 | 6.41 | 1.76 | 3.96 | 3.03 | 0.50 | 27 / 29 | 20 / 44 | 61–91 |
| 2026-04-12 | 8.07 | 2.40 | 3.67 | 2.07 | 1.06 | 27 / 35 | 35 / 63 | 61–81 |
| 2026-04-11 | 11.97 | 4.05 | 4.24 | 3.22 | 0.41 | **77 / 48** | 13 / 95 | 62–81 |

**Observations:**
- heat1 (electric) ran 4–21 h/day, mean ≈12 h. That's ~50% of the day with heat on. Consistent with the edge-targeting bug: temp pinned at lower edge meant heater kept cycling just to hold there.
- Three days (04/14, 04/15, 04/17) had heat1 > 20 h — pathological. Temp_min on those days 52–59°F. Plants were being held at the bottom of the band.
- Cycle counts per day for heat (S2): 15–60. THERMAL_RELIEF + SEALED_MIST cycling driving a lot of gas-heater transitions.
- Sprint-12 expectation: heat1 drops 20–40% (target is 3°F higher), heat2 drops similarly, compliance rises.

### Override events (`override_events`, 30 d)

| Override type | Fires | First seen | Last seen |
|---|---:|---|---|
| `relief_cycle_breaker` | 7 | 2026-04-18 | 2026-04-20 |
| (everything else) | 0 | — | — |

7 fires in 30 days is low. Firmware is not silently overriding planner intent often. The 7 `relief_cycle_breaker` fires are legitimate — R2-6 breaker correctly tripped on sustained high VPD with no evap capacity.

### Mode distribution (`system_state.greenhouse_state`, 30 d)

Labels span both the pre-sprint-8 composite naming (`COOL_S1_HUM_IDLE`, `HEAT_S2_HUMID_S1`, etc.) and the post-sprint-8 bare naming (`SEALED_MIST_S1`, `VENTILATE`). Highest post-sprint-8 buckets:
- `SEALED_MIST_S1`: 10.5 %, `SEALED_MIST_S2`: 9.6 %, `IDLE`: 7.1 %, `VENTILATE`: 3.2 %
- `THERMAL_RELIEF`: 5.3 %, `SAFETY_COOL`: 0.8 %, `DEHUM_VENT`: 0.8 %
- No `SAFETY_HEAT` events in 30 days — safety rail held.

Post-sprint-12 initial sample (45 min): SEALED_MIST_S2=38.9 %, S1=22.2 %, FOG=16.7 %, VENTILATE=16.7 %, IDLE=5.6 %. Reasonable for a hot April day (outdoor 75°F, lux 14 800) where the greenhouse is running at the top of the band.

## Planner context pack (ready-to-paste into Iris prompts)

This section is written so genai can copy-paste it verbatim into the Iris system prompt (or any planner-facing context-builder). Keeps the language planner-native, not firmware-internal.

### Planner context — how the firmware interprets what you push

> **The firmware enforces a two-band model.** Safety rails (`safety_min`, `safety_max`, `safety_vpd_min`, `safety_vpd_max`) are hard backstops — if they activate, something has gone badly wrong upstream. The operational band is `(temp_low, temp_high)` + `(vpd_low, vpd_high)` — that's what the controller actually aims at. Day/night phasing, solar-driven tightening, crop-phase shifts — all your job. The firmware does not model time-of-day or phase internally.
>
> **The controller targets the INTERIOR of the band, not the edges** (sprint-12, 2026-04-20). Given band `(temp_low, temp_high)`:
>
> - Heating fires when temp drops below `temp_low + (temp_high - temp_low) × 0.25 + bias_heat + heat_hysteresis`.
> - Cooling fires when temp rises above `temp_high − (temp_high - temp_low) × 0.25 + bias_cool`.
> - **Effective operating zone is the middle 50% of the band you push.** The bottom and top 25% are deadbands where no heating or cooling engages.
>
> Example: if you push `(temp_low=62, temp_high=75)`, the controller holds temp roughly between 65.3°F and 71.8°F.
>
> **VPD behaves the same way**: SEALED_MIST fires above `vpd_high − (vpd_high − vpd_low) × 0.25`, DEHUM_VENT fires below `vpd_low + (vpd_high − vpd_low) × 0.25`. With `(vpd_low=0.8, vpd_high=1.4)`, the controller aims to hold VPD between ~0.95 and ~1.25.
>
> **To tighten the operating zone**: narrow the band. Pushing `(temp_low=66, temp_high=70)` gives a 4°F band → operating zone is 67–69°F.
>
> **To shift the operating zone without changing band width**: use `bias_heat` / `bias_cool`. Both are symmetric offsets from the interior target. `bias_heat=+2` pushes the heating trigger 2°F higher (more aggressive heat). `bias_cool=−2` pushes the cooling trigger 2°F lower (more aggressive cooling). These are operator-level nudges; the clean way is to push a different `(temp_low, temp_high)` pair.
>
> **What each action the firmware takes means for equipment:**
>
> - **IDLE** — no relays active. Target condition.
> - **VENTILATE** — vent open + lead fan. Fan2 joins when `temp > Thigh + d_cool_stage_2` (default +3°F). If VPD is also above `vpd_max_safe`, fog fires alongside.
> - **SEALED_MIST** — vent closed, fans off, misters pulsing on the worst-stressed zone. Escalates MIST_WATCH → S1 → S2 → FOG as VPD climbs further above `vpd_high_eff`.
> - **DEHUM_VENT** — vent open to dump humidity. Both fans when `vpd < vpd_low_eff − dehum_aggressive_kpa` (default 0.3 kPa below).
> - **THERMAL_RELIEF** — forced vent burst after SEALED_MIST runs for `sealed_max_ms` (default 10 min). Both fans, vent open. Max 3 consecutive sealed→relief cycles before R2-6 latches VENTILATE.
> - **SAFETY_COOL / SAFETY_HEAT** — rails activated. All cooling / all heating.
> - **SENSOR_FAULT** — all relays off. Hardware thermostat takes over. If you see this, escalate.
>
> **Runtime expectations** (pre-sprint-12 baseline; expect 20–40% reductions for heat/cool after sprint-12):
>
> - Heat1 (electric, lead): 4–21 h/day depending on outdoor temp and band width.
> - Heat2 (gas, backup): 0–11 h/day. Fires when temp drops to `Tlow - d_heat_stage_2` (default 5°F below heating target) and latches until temp ≥ heating target + heat_hysteresis.
> - Fan1+Fan2: 1–7 h/day combined. Correlates with peak-sun hours.
> - Vent: 1–5 h/day. Same.
> - Fog: 0–2 h/day. Only inside `[fog_window_start, fog_window_end)` (default 7–17), only if `rh_pct ≤ fog_rh_ceiling` (default 90%) and `temp ≥ fog_min_temp` (default 55°F).
>
> **Dispatcher push → firmware read loop**: dispatcher pushes every 60 s if a tunable changed. Firmware reads new values within ≤5 min via its `/setpoints` poll. ESP32 re-publishes values to `setpoint_snapshot` within ~60 s. Sprint-24.7 confirmation monitor alerts `setpoint_unconfirmed` if a push doesn't show up in the snapshot within 5 min (and critical after 15 min). A new tunable that lacks a `cfg_*` readback (⚠️ flagged rows above) cannot be confirmed — silent corruption is undetectable there.
>
> **Override flags (OBS-1e) you should pay attention to**:
>
> - `occupancy_blocks_moisture` — someone is in the greenhouse; mist + fog inhibited until occupancy clears. Expected.
> - `fog_gate_rh` / `fog_gate_temp` / `fog_gate_window` — fog was wanted but blocked. Tune `fog_rh_ceiling`, `fog_min_temp`, or the window if you need more fog hours.
> - `relief_cycle_breaker` — firmware forced VENTILATE after 3 consecutive SEALED→RELIEF cycles. You're pushing the controller past its thermal-dump capacity; either widen VPD band, push `fog_escalation_kpa` lower, or accept the vent purge.
> - `seal_blocked_temp` — firmware refused to close vent for SEALED_MIST because temp was within 5°F of `safety_max`. Lower `temp_high` or raise `safety_max`.
> - `vpd_dry_override` — R2-3 force-sealed without your dwell sanction because VPD exceeded `vpd_max_safe`. Your planning signal missed a real stress event; use as a retrospective alert.
>
> **Known constraints you cannot override:**
>
> - `safety_min ≤ temp_low − 5` (validate_setpoints clamp)
> - `safety_max ≥ temp_high + 5`
> - `vpd_min_safe ≤ vpd_low − 0.05`
> - `vpd_max_safe ≥ vpd_high + 0.1`
> - `dehum_aggressive_kpa` must stay < `vpd_low` (firmware-internal default 0.3 kPa, not dispatcher-pushable)
>
> If you try to push past these, `setpoint_clamps` logs the truncation and the firmware receives the clamped value. Assume your pushes are being modified if they violate these invariants.

### Cheat-sheet: common planner actions → firmware outcomes

| Planner action | Expected firmware response | Things to watch |
|---|---|---|
| Narrow `(temp_low, temp_high)` by 2°F | Operating zone shrinks 1°F, heater and cooling duty both rise. | Sustained >15 h/day heat1 = too tight for current outdoor conditions. |
| Raise `vpd_low` by 0.1 | DEHUM_VENT fires sooner; less saturated-air holding. | If RH rises too fast, check if `occupancy_inhibit` is firing. |
| Lower `fog_escalation_kpa` by 0.1 | Fog engages earlier in mist escalation. | Watch `fog_gate_*` — if gates block, the setpoint change accomplishes nothing. |
| Push `bias_heat` from 0 to +3 | Heating target rises 3°F. On a cold day, heater runs longer. | Pre-sprint-12 this also moved the S2 latch threshold. Post-sprint-12 same semantics but anchored to interior. |
| Enable `sw_occupancy_inhibit` with someone in the greenhouse | ALL misters + fog locked out. | Operator-overrideable only by toggling off the switch. |
| Raise `safety_max` from 95 to 100 | Firmware will close vent for SEALED_MIST at higher temperatures (more mist in hot conditions). | Don't raise above 105 — hardware-limit on relay coil ratings. |

## Process for updating this doc

1. When anyone adds a new tunable: also add a row here in the same PR.
2. When a tunable's use site changes in firmware: bump the "FW use" column.
3. When the readback gap closes for any 🔴 row: remove the flag.
4. Enforce via drift guard: a test asserts every tunable in `ALL_TUNABLES` has a row here. (Follow-up test to add.)

## References

- `verdify_schemas/tunables.py` — canonical tunable list (`NUMERIC_TUNABLES`, `SWITCH_TUNABLES`, `ALL_TUNABLES`)
- `verdify_schemas/plan.py` — `PlanTransition.params` validates keys against `ALL_TUNABLES`
- `verdify_schemas/setpoint.py` — `SetpointChange.parameter` validates via `TunableParameter`
- `ingestor/entity_map.py` — `SETPOINT_MAP`, `CFG_READBACK_MAP`, `PARAM_TO_ENTITY`, `SWITCH_TO_ENTITY`
- `ingestor/tasks.py::setpoint_dispatcher` — per-cycle push logic (lines 1080-1314)
- `firmware/lib/greenhouse_types.h` — `Setpoints` struct + `defaults_setpoints()` + `validate_setpoints()`
- `firmware/lib/greenhouse_logic.h` — mode controller, use sites for every tunable
- `firmware/greenhouse/controls.yaml:1210-1351` — HTTP pull handler that writes ESP32 globals
- `firmware/greenhouse/sensors.yaml` — cfg_* readback sensor definitions

## Related incidents this spec would have prevented

- **2026-04-19/20 overnight** — firmware sprint-10 day/night pairs: the 8 new tunables (`temp_day/night_low/high`, `vpd_day/night_low/high`) had no rows here. Nobody caught that `resolve_active_band()` prioritized day/night over the legacy band until plants had 10h of stress. Fixed in sprint-11 by removing the parameters; the doc would have required documenting precedence up-front.
- **Edge-targeting (2026-04-18 overnight, sprint-12 fix)** — heating target was `temp_low + bias_heat + heat_hysteresis`, anchored to the lower edge. When bias_heat wasn't pushed reliably (mean=0.73 over 30 days despite 5°F being operationally intended), plants pinned at 62°F with `temp_low=62`. Sprint-12 rewrites targets to band interior. The doc would have flagged "temp_low used as the target, not as a tolerance bound" as a design smell.
- **bias_heat drift** — dispatcher pushed 5, firmware read 4. Would have surfaced via the spec's "valid range" + confirmation check + the 30-day range scan above (min=0, avg=0.73).
- **vpd_target_west stuck at 1.20** — 30-day snapshot shows zero variance. Would have been caught with the first range-scan table; now surfaced for follow-up.
- **MIDNIGHT label dispatch** — `TRANSITION:midnight_posture` had no entry in whatever dispatched send_to_iris calls. Architecturally similar: no up-front mapping.
