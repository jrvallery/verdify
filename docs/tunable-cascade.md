# Tunable Cascade — End-to-End Spec

**Status:** IN PROGRESS — started 2026-04-20 pre-Jason-departure. Critical control-loop rows filled; registry coverage is now complete as of the 2026-04-27 firmware control-contract audit.

**Purpose:** Single source of truth mapping every tunable through every layer it touches. Pydantic schema → DB column → dispatcher route → firmware struct field → firmware use site → cfg_* readback → default value → valid range → owner (who sets it) → cascade timing.

**Why it exists now:** sprint-10 day/night incident + bias_heat drift + MIDNIGHT label-mismatch are all symptoms of the same missing spec. Every sprint has added tunables without extending this table, and each silent-override bug has been a consequence.

**Canonical machine-readable source:** `verdify_schemas/tunable_registry.py`.
This markdown is the human-readable cascade narrative; drift guards enforce the
registry against firmware, schemas, entity_map, cfg readbacks, and MCP.

**Current contract doc:** `docs/firmware-control-contract.md`.

## Known open issues

### Resolved 2026-04-28 — v2 heating edge-targeting bug

Pre-fix, heating demand used the lower edge/interior-lower edge of the band
instead of the band midpoint:
```c
bool needs_heating_s1 = in.temp_f < (Tlow + sp.heat_hysteresis);
```
and gas-stage latch used `Tlow - d_heat_stage_2`.

This let v2 sit below `temp_low` until the `d_heat_stage_2` margin was
exceeded. With the 2026-04-28 live morning band (`temp_low=65.5`,
`temp_high=72.7`, `d_heat_stage_2=5`), heat2 waited until roughly `62F`,
which directly explained poor lower-band compliance.

Fix: controller v2 now targets `(temp_low + temp_high) / 2` for heat1 and
latches heat2 immediately when `temp_f < temp_low`; heat2 clears once the
midpoint is recovered. Legacy cascade behavior is unchanged until it is retired.

Open follow-up: cooling still uses the legacy 25%-inside upper target and should
get the same first-principles review before summer heat ramps.

### 2026-04-27 Setpoints literal audit

The live ESPHome Setpoints builder no longer assigns controller policy fields
from literals. These params now have the full schema → DB → dispatcher → ESPHome
Number → `/setpoints` handler → `Setpoints` field → cfg readback path:

- `heat_hysteresis`
- `max_relief_cycles`
- `dehum_aggressive_kpa`
- `vent_latch_timeout_ms`
- `safety_max_seal_margin_f`
- `econ_heat_margin_f`
- `gl_lux_hysteresis`

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

| Param | Type | Pydantic | DB | Dispatcher route | FW struct | FW use | cfg_* readback | Default | Valid range | Owner | Cascade |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `temp_low` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_plan`, `setpoint_changes` | `target_temp_low_f` | `Setpoints.temp_low` | `greenhouse_logic.h:439` Tlow calc; band-compliance; mode transitions | `cfg_temp_low_f` | 58°F | [30, 80] | crop (band) + planner (override, clamped to band) | immediate (5 min) |
| `temp_high` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_plan`, `setpoint_changes` | `target_temp_high_f` | `Setpoints.temp_high` | `greenhouse_logic.h:119` VENTILATE trigger; band-compliance | `cfg_temp_high_f` | 82°F | [40, 100] | crop (band) + planner (override, clamped) | immediate |
| `d_heat_stage_2` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_d_heat_stage_2_f` | `Setpoints.d_heat_stage_2` | Legacy cascade S2 latch threshold (`Tlow - d_heat_stage_2`); controller v2 ignores this for gas-stage entry and latches heat2 at raw `temp_low` | `cfg_d_heat_stage_2_f` | 2.0°F | [0, 5] | operator / fw-default | immediate |
| `d_cool_stage_2` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_d_cool_stage_2_f` | `Setpoints.d_cool_stage_2` | `greenhouse_logic.h:494` 2nd-fan threshold (fan2 engages at `Thigh + d_cool_stage_2`) | ⚠️ **NONE** (readback gap) | 2.0°F | [0, 5] | operator / fw-default | immediate but unverified |
| `temp_hysteresis` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_hyst_temp_f` | `Setpoints.temp_hysteresis` | `greenhouse_logic.h:120,136,262` mode transition hysteresis (prevents churn near boundary) | `cfg_hyst_temp_f` | 1.5°F | [0.5, 3.0] | operator / fw-default | immediate |

## Bias / offsets (2 tunables, edge-targeting-bug-related) — FULLY SPEC'D

| Param | Type | Pydantic | DB | Dispatcher route | FW struct | FW use | cfg_* readback | Default | Valid range | Owner | Cascade |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `bias_heat` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_bias_heat_f` | `Setpoints.bias_heat` | Legacy cascade heating offset; controller v2 derives heat1 target from the raw temp-band midpoint and heat2 entry from raw `temp_low` | `cfg_bias_heat_f` | 0°F | [0, 10] | operator (sets once) | immediate |
| `bias_cool` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_bias_cool_f` | `Setpoints.bias_cool` | `greenhouse_logic.h` subtracts from `temp_high` for internal Thigh (symmetric counterpart to bias_heat) | `cfg_bias_cool_f` | 0°F | [0, 10] | operator | immediate |

## VPD band (3 tunables) — FULLY SPEC'D

| Param | Type | Pydantic | DB | Dispatcher route | FW struct | FW use | cfg_* readback | Default | Valid range | Owner | Cascade |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `vpd_low` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_plan`, `setpoint_changes` | `target_vpd_low_kpa` | `Setpoints.vpd_low` | DEHUM_VENT trigger; band-compliance | `cfg_vpd_low_kpa` | 0.35 | [0.1, 1.0] | crop (band) + planner (override, clamped) | immediate |
| `vpd_high` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_plan`, `setpoint_changes` | `target_vpd_high_kpa` | `Setpoints.vpd_high` | SEALED_MIST trigger; band-compliance | `cfg_vpd_high_kpa` | 2.8 | [0.4, 3.0] | crop (band) + planner (override, clamped) | immediate |
| `vpd_hysteresis` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_hyst_vpd_kpa` | `Setpoints.vpd_hysteresis` | VPD mode transition hysteresis (`greenhouse_logic.h:108`) | `cfg_hyst_vpd_kpa` | 0.3 | [0.05, 1.0] | operator / fw-default | immediate |

## Safety rails (4 tunables, CANNOT be overridden past clamp bounds) — FULLY SPEC'D

| Param | Type | Pydantic | DB | Dispatcher route | FW struct | FW use | cfg_* readback | Default | Valid range | Owner | Cascade |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `safety_min` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_plan`, `setpoint_changes` | `target_safety_min_f` | `Setpoints.safety_min` | SAFETY_HEAT trigger (`greenhouse_logic.h:111`). Hard clamp: safety_min ≤ temp_low - 5. | `cfg_safety_min_f` | 35°F | [30, 60] clamped | operator (set once; planner can override within range) | immediate |
| `safety_max` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_plan`, `setpoint_changes` | `target_safety_max_f` | `Setpoints.safety_max` | SAFETY_COOL trigger (`greenhouse_logic.h:110`). Hard clamp: safety_max ≥ temp_high + 5. | `cfg_safety_max_f` | 100°F | [80, 110] clamped | operator | immediate |
| `safety_vpd_min` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_safety_vpd_min_kpa` | `Setpoints.vpd_min_safe` | DEHUM_VENT force trigger (`greenhouse_logic.h:295-309`) | `cfg_safety_vpd_min_kpa` | 0.3 kPa | [0.1, 1.5] | operator | immediate |
| `safety_vpd_max` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_safety_vpd_max_kpa` | `Setpoints.vpd_max_safe` | R2-3 dry override seal trigger (`greenhouse_logic.h:269-287`) | `cfg_safety_vpd_max_kpa` | 3.0 kPa | [2.5, 3.0] | operator | immediate |

## Per-zone VPD targets (4 tunables) — FULLY SPEC'D

| Param | Type | Pydantic | DB | Dispatcher route | FW struct | FW use | cfg_* readback | Default | Valid range | Owner | Cascade |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `vpd_target_south` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_vpd_target_south_kpa` | `Setpoints.vpd_target_south` | Mister zone selection priority (south zone) | `cfg_vpd_target_south_kpa` | 1.5 | [0.3, 2.5] | crop (via `fn_zone_vpd_targets`) | immediate |
| `vpd_target_west` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_vpd_target_west_kpa` | `Setpoints.vpd_target_west` | Mister zone selection (west) | `cfg_vpd_target_west_kpa` | 1.5 | [0.3, 2.5] | crop | immediate |
| `vpd_target_east` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_vpd_target_east_kpa` | `Setpoints.vpd_target_east` | Mister zone selection (east) | `cfg_vpd_target_east_kpa` | 1.5 | [0.3, 2.5] | crop | immediate |
| `vpd_target_center` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_vpd_target_center_kpa` | `Setpoints.vpd_target_center` | Mister zone selection (center) | `cfg_vpd_target_center_kpa` | 1.5 | [0.3, 2.5] | crop | immediate |

## Mister engagement thresholds (2 tunables) — FULLY SPEC'D

| Param | Type | Pydantic | DB | Dispatcher route | FW struct | FW use | cfg_* readback | Default | Valid range | Owner | Cascade |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `mister_engage_kpa` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_mister_engage_kpa` | `Setpoints.mister_engage_kpa` | SEALED_MIST S1 entry threshold | `cfg_mister_engage_kpa` | 1.2 | [0.6, 2.5] | planner | immediate |
| `mister_all_kpa` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_mister_all_kpa` | `Setpoints.mister_all_kpa` | SEALED_MIST S2 escalation threshold | `cfg_mister_all_kpa` | 1.8 | [0.9, 3.0] | planner | immediate |
| `mister_engage_delay_s` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_mister_engage_delay_s` | ESPHome global `mister_engage_delay_s` | S1 dwell before first mister pulse | `cfg_mister_engage_delay_s` | 30s | [5, 300] | planner | immediate |
| `mister_all_delay_s` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_mister_all_delay_s` | `Setpoints.mist_s2_delay_ms` + ESPHome global | S2/all-zone dwell before escalation | `cfg_mister_all_delay_s` | 60s | [10, 600] | planner | immediate |
| `mister_pulse_on_s` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_mister_pulse_on_s` | ESPHome global `mister_pulse_on_s` | per-zone pulse duration | `cfg_mister_pulse_on_s` | 45s | [10, 120] | planner | immediate |
| `mister_pulse_gap_s` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `target_mister_pulse_gap_s` | ESPHome global `mister_pulse_gap_s` | gap between mister pulses | `cfg_mister_pulse_gap_s` | 60s | [10, 300] | planner | immediate |

## Summer thermal-driven vent gate (sprint-15, 5 tunables + 2 readback-only) — FULLY SPEC'D

See `docs/firmware-sprint-15-summer-vent-spec.md` for design rationale. Gate fires in `determine_mode()` above VPD-seal precedence when outdoor is cooler + drier than indoor and outdoor data is fresh.

| name | type | emitted via | table | entity_id (HA) | FW struct field | FW use site | cfg_* readback | default | range | authority | push path |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `sw_summer_vent_enabled` | switch | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `switch.summer_vent_enabled` | `Setpoints.sw_summer_vent_enabled` | `greenhouse_logic.h::determine_mode()` master enable for summer-vent gate | `cfg_summer_vent_enabled` | 1 (on) | {0, 1} | operator (opt-out; winter) | immediate |
| `vent_prefer_temp_delta_f` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `number.vent_prefer_temp_delta_f` | `Setpoints.vent_prefer_temp_delta_f` | gate: `outdoor_temp_f < indoor_temp_f - delta` | `cfg_vent_prefer_temp_delta_f` | 5.0°F | [2, 15] | planner | immediate |
| `vent_prefer_dp_delta_f` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `number.vent_prefer_dp_delta_f` | `Setpoints.vent_prefer_dp_delta_f` | gate: `outdoor_dewpoint_f < indoor_dewpoint_f - delta` | `cfg_vent_prefer_dp_delta_f` | 5.0°F | [2, 15] | planner | immediate |
| `outdoor_staleness_max_s` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `number.outdoor_staleness_max_s` | `Setpoints.outdoor_staleness_max_s` | gate: disables when outdoor reading > N seconds old | `cfg_outdoor_staleness_max_s` | 300 s | [60, 1800] | operator | immediate |
| `summer_vent_min_runtime_s` | num | `PlanTransition.params`, `SetpointChange` | `setpoint_changes` | `number.summer_vent_min_runtime_s` | `Setpoints.summer_vent_min_runtime_s` | VENTILATE min dwell after gate fires (anti-flap near threshold) | `cfg_summer_vent_min_runtime_s` | 180 s | [60, 600] | operator | immediate |
| `outdoor_temp_f` | num (ro) | — (firmware-internal) | — | — | `SensorInputs.outdoor_temp_f` | input to gate; Tempest → HA → ESPHome template sensor | `cfg_outdoor_temp_f` | n/a (live) | n/a | Tempest | readback only |
| `outdoor_dewpoint_f` | num (ro) | — (firmware-internal) | — | — | `SensorInputs.outdoor_dewpoint_f` | input to gate; computed from Tempest temp + RH | `cfg_outdoor_dewpoint_f` | n/a (live) | n/a | Tempest | readback only |

## Remaining tunables — TBD (stub rows to fill in during the week)

The remaining ~50 tunables are organized below by category. Each needs the full row treatment. **Default values, ranges, FW use sites, and cfg_* readback presence will be filled in week of 2026-04-20.**

### Mister pulse + timing (9 tunables, readback gap suspected)
- `mister_on_s`, `mister_off_s`, `mister_all_on_s`, `mister_all_off_s`, `mister_max_runtime_min`
- Readback-covered: `mister_engage_delay_s`, `mister_all_delay_s`, `mister_pulse_on_s`, `mister_pulse_gap_s`, `mister_water_budget_gal`, `mister_vpd_weight`

### Equipment timing — relay min on/off (8 tunables)
- `min_heat_on_s`, `min_heat_off_s`, `min_fan_on_s`, `min_fan_off_s`, `min_vent_on_s`, `min_vent_off_s`, `lead_rotate_s`, `fan_burst_min`, `vent_bypass_min`, `fog_burst_min`
- Readback-covered fog timing: `min_fog_on_s`, `min_fog_off_s`

### Controller v2 dwell gate
- Readback-covered: `sw_dwell_gate_enabled` (`cfg_dwell_gate_enabled`), `dwell_gate_ms` (`cfg_dwell_gate_ms`)
- Controller v2 cooling now enters at raw `temp_high` under normal outdoor conditions; `bias_cool` remains legacy-only for v2 normal cooling. If outdoor air is deeply cold relative to the crop band, v2 waits for the same band-scaled delta used by stage-2 fan escalation (`min(d_cool_stage_2, max(1°F, 25% of temp band width))`) before opening the vent, protecting temp-band compliance without cold-day vent thrash.

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

### Grow lights (5 tunables)
- `gl_dli_target`, `gl_lux_threshold`, `gl_lux_hysteresis`, `gl_sunrise_hour`, `gl_sunset_hour`

### Switches (7 tunables, 0.0/1.0)
- `sw_economiser_enabled`, `sw_fog_closes_vent`, `sw_gl_auto_mode`, `sw_irrigation_enabled`, `sw_irrigation_wall_enabled`, `sw_irrigation_center_enabled`, `sw_irrigation_weather_skip`, `sw_occupancy_inhibit`

### Known routing gaps
- `sw_mister_closes_vent` — exists as ESP32 switch + cfg readback, NOT in SETPOINT_MAP. Dispatcher cannot push. Sprint-21 follow-up unresolved.

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
- **bias_heat drift** — dispatcher pushed 5, firmware had 4. Would have surfaced via the spec's "valid range" + confirmation check.
- **MIDNIGHT label dispatch** — `TRANSITION:midnight_posture` had no entry in whatever dispatched send_to_iris calls. Architecturally similar: no up-front mapping.
