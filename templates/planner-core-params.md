# Planner Core Parameters

## Canonical Contract

The canonical tunable list is `verdify_schemas/tunable_registry.py`.
`REGISTRY` covers every dispatcher route in `ingestor/entity_map.py::SETPOINT_MAP`.
MCP `set_tunable` accepts exactly `PLANNER_PUSHABLE_REG`, which means Tier 2
escape-hatch parameters are pushable when Iris names a specific reason.

`TIER1_REG` is only the daily prompt subset. A planner transition should include
the tactical Tier 1 parameters it is intentionally setting, not a mandatory
copy of every tunable.

## Ownership

- Crop band: `temp_low`, `temp_high`, `vpd_low`, `vpd_high` are dispatcher-owned
  from crop profiles in normal operation. Use direct `set_tunable` only for an
  explicit temporary override.
- Safety rails: `safety_min`, `safety_max`, `safety_vpd_min`, `safety_vpd_max`
  are operator/fallback rails and are not planner-pushable.
- Planner policy: all other `planner_pushable=True` registry rows may be pushed
  via `set_tunable` or `set_plan`; firmware clamps remain the final authority.

## Drift Guards

CI checks the registry against:

- `verdify_schemas/tunables.py` schema names
- `ingestor/entity_map.py` dispatcher and cfg readback maps
- `firmware/greenhouse/controls.yaml` `/setpoints` clamp keys
- `mcp/server.py` Tier 1 prompt allowlist and planner-pushable gate

New firmware tunables must add the ESPHome Number, `/setpoints` parser entry,
cfg readback, entity map route, schema name, and registry row in the same PR.
