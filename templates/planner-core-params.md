# Planner Core Parameters

## Canonical Contract

The canonical tunable list is `verdify_schemas/tunable_registry.py`.
`REGISTRY` covers every dispatcher route in `ingestor/entity_map.py::SETPOINT_MAP`.
MCP `set_tunable` accepts exactly `PLANNER_PUSHABLE_REG`, which is now the
canonical planner-policy class. Non-policy rows remain documented and
searchable but are rejected for planner writes.

`TIER1_REG` is the routine planner-policy surface. A full planner transition
must include every tactical Tier 1 parameter, even when the value is unchanged,
so old active rows cannot carry stale semantics across the plan horizon.

## Ownership

- Crop band: `temp_low`, `temp_high`, `vpd_low`, `vpd_high` are dispatcher-owned
  from crop profiles in normal operation. The planner must not write them.
- Safety rails: `safety_min`, `safety_max`, `safety_vpd_min`, `safety_vpd_max`
  are operator/fallback rails and are not planner-pushable.
- Planner policy: only `control_class="planner_policy"` registry rows may be
  pushed via `set_tunable` or `set_plan`; firmware clamps remain the final
  authority.
- Controller/operator/readback/retired rows are context only. Promote them to
  planner policy only after replay evidence proves they add value.

## Key Semantics

- `mister_engage_kpa` gates physical S1 mister pulses once `SEALED_MIST` or
  explicit `VENTILATE` assist creates humidity demand. SEALED_MIST entry itself comes from `vpd_high` plus
  `vpd_watch_dwell_s`. During live VPD-high or near-edge `VENTILATE` stress,
  keep moisture thresholds near the active band: engage around
  `vpd_high + 0.05`, all-zone around `max(1.0, vpd_high + 0.25)`, and fog
  escalation around `0.20`, or `0.15` in hot/dry venting, unless dew-point
  margin is tight.
- The dispatcher enforces that band-coupled posture during live VPD-high or
  near-edge `VENTILATE` stress with healthy dew margin by clamping overly conservative planner values for
  `mister_engage_kpa`, `mister_all_kpa`, `mister_*_delay_s`,
  `mister_pulse_gap_s`, `min_fog_off_s`, and `fog_escalation_kpa`. The clamp
  stays sticky across recent unrecovered stress; do not unwind moisture
  aggression until observed VPD has stayed below the high band.
- `DEHUM_VENT` exits immediately if it overshoots dry-side VPD above
  `vpd_high`; do not use dwell gates to hold dehumidification through dry
  stress.
- Heat2 is invalid without heat1, and non-safety heat is suppressed during
  physical vent/fan air exchange.
- The dispatcher keeps the house VPD control band at least 0.55 kPa wide to
  prevent mixed-zone crop targets from creating chatter.
- `sw_fog_closes_vent` and `sw_mister_closes_vent` are planner-policy
  interlocks for normal moisture cycles; explicit VENTILATE vent-mist assist
  bypasses them because temperature remains the primary control objective.

## Drift Guards

CI checks the registry against:

- `verdify_schemas/tunables.py` schema names
- `ingestor/entity_map.py` dispatcher and cfg readback maps
- `firmware/greenhouse/controls.yaml` `/setpoints` clamp keys
- `mcp/server.py` Tier 1 prompt allowlist and planner-pushable gate

New firmware tunables must add the ESPHome Number, `/setpoints` parser entry,
cfg readback, entity map route, schema name, and registry row in the same PR.
