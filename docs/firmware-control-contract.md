# Firmware Control Contract

Status: active audit, 2026-04-27.

This document defines how a firmware value is allowed to enter the ESP32
control loop. The goal is that greenhouse policy comes from the database,
planner, crop profile, or operator configuration. Firmware literals are allowed
only for fallback safety rails, physics/calibration constants, unit conversions,
or invariant clamps.

## End-to-End Tunable Path

Every planner/operator tunable must have this chain:

| Layer | Contract |
|---|---|
| Schema | Name appears in `verdify_schemas/tunables.py::ALL_TUNABLES` |
| Registry | Row in `verdify_schemas/tunable_registry.py::REGISTRY` with owner, range, default, ESP object id, cfg readback |
| Database | Written to `setpoint_plan` and/or `setpoint_changes`; latest value visible through MCP `get_setpoints` |
| Dispatcher | `ingestor/entity_map.py::SETPOINT_MAP` maps canonical name to ESPHome Number/Switch object id |
| ESPHome config | `firmware/greenhouse/tunables.yaml` exposes the Number/Switch and stores into a global |
| Firmware ingest | `firmware/greenhouse/controls.yaml` `/setpoints` handler parses the canonical key and clamps it |
| Control model | `Setpoints` in `firmware/lib/greenhouse_types.h` receives the global value, not a literal |
| Readback | `firmware/greenhouse/sensors.yaml` cfg sensor and `CFG_READBACK_MAP` let alerting confirm the value landed |

MCP `set_tunable` now gates on `PLANNER_PUSHABLE_REG`, not just Tier 1. Tier 1
is the daily prompt subset; Tier 2 is still pushable when Iris gives a specific
reason. Safety rails with `planner_pushable=False` remain operator/fallback only.

## Ownership Classes

| Class | Examples | Planner access |
|---|---|---|
| Crop band | `temp_low`, `temp_high`, `vpd_low`, `vpd_high` | Read-only in routine plans; explicit temporary override only |
| Planner policy | mist/fog timing, vent dwell, heat hysteresis, relief/latch knobs, grow-light thresholds | Pushable through `set_tunable` / `set_plan` |
| Operator/site constants | `site_pressure_hpa`, safety rail values | Not planner-pushable unless registry says so |
| Firmware fallback rails | `validate_setpoints()` clamps, sensor plausibility limits | Firmware-owned; used when upstream data is corrupt or absent |
| Physics/calibration | Magnus dewpoint constants, lux ADC conversion, VPD formula constants | Documented constants; not planner policy |

## 2026-04-27 Audit Fixes

The audit found live `Setpoints` fields that were already modeled in C++ but
still assigned as literals in `controls.yaml`. They are now fully routed:

| Canonical param | Previous literal | Current source |
|---|---:|---|
| `heat_hysteresis` | `1.0f` | `heat_hysteresis_f` global + Number + `/setpoints` + cfg readback |
| `max_relief_cycles` | `3` | `max_relief_cycles` global + Number + `/setpoints` + cfg readback |
| `dehum_aggressive_kpa` | `0.6f` | `dehum_aggressive_kpa` global + Number + `/setpoints` + cfg readback |
| `vent_latch_timeout_ms` | `1800000u` | `vent_latch_timeout_ms` global + Number + `/setpoints` + cfg readback |
| `safety_max_seal_margin_f` | `5.0f` | `safety_max_seal_margin_f` global + Number + `/setpoints` + cfg readback |
| `econ_heat_margin_f` | `5.0f` | `econ_heat_margin_f` global + Number + `/setpoints` + cfg readback |
| `gl_lux_hysteresis` | global-only | Number + `/setpoints` + cfg readback + registry |

Drift guards now fail if `Setpoints setpts = {...}` contains numeric policy
literals, if a dispatcher route lacks a registry row, or if MCP stops using
`PLANNER_PUSHABLE_REG` for `set_tunable`.

## Remaining Firmware Literals

These are still intentional constants or future tuning candidates:

| Category | Examples | Recommendation |
|---|---|---|
| Sensor plausibility and stale sentinels | temp/RH/VPD plausible ranges, stale outdoor age sentinel | Keep firmware-owned unless field data shows false trips |
| Physics and unit conversions | Magnus constants, F/C conversion, ADC/lux scaling, PPFD/DLI conversion | Keep as documented calibration constants |
| Controller shape constants | v2 band interior fraction `0.25`, VPD hysteresis cap fraction `0.33`, cold outdoor margin `10°F`, minimum band widths | Promote to planner tunables only after replay shows the current defaults are the limiting factor |
| Irrigation weather skip constants | `0.6 kPa` VPD, `35°F` outdoor temp | Candidate for a future irrigation tuning PR |
| Mister local timing heuristics | idle holdoff/fairness windows | Candidate if post-deploy telemetry shows zone starvation or cycling |

The next hardening step is a generated registry-derived ESPHome map so
`SETPOINT_MAP`, `CFG_READBACK_MAP`, and MCP allowlists stop being hand-maintained.
