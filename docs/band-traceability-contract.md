# Band Traceability Contract

Status: deployed to the live TimescaleDB on 2026-05-15.

Verdify has three band concepts. Do not collapse them in code, dashboards, copy, or planner prompts.

| Band | Source | Meaning |
| --- | --- | --- |
| Crop target band | `fn_band_setpoints(ts)` | Plant-policy envelope from crop target profiles. |
| Firmware-enforced band | `setpoint_changes` via dispatcher pushes | The temp/VPD band the ESP32 state machine enforces. This is what compliance and stress scorecards use. |
| Readback band | `setpoint_snapshot` cfg_* values | Firmware-side echo that proves the ESP32 accepted the pushed values. |

## Canonical SQL Surface

- `fn_house_vpd_control_band(ts)` derives the firmware house VPD band from the crop VPD envelope plus zone VPD targets. It mirrors dispatcher semantics: median zone target, low-side relaxation, and `0.55 kPa` minimum width.
- `fn_timeline_setpoint_value(greenhouse_id, parameter, ts, default)` resolves non-band tunables for timeline graphs: actual pushed values through `now()`, active/planned schedule after `now()`, latest push/default as fallback.
- `fn_band_timeline(start_ts, end_ts, step, greenhouse_id)` is the dashboard timeline. Samples at or before `now()` use actual pushed firmware setpoints from `setpoint_changes`; samples after `now()` use the dispatcher-projected crop/house band. It also derives firmware trigger and padding thresholds from the same tunables and sensor context the ESP32 uses: temperature heat/cool thresholds, outdoor-cold vent padding, solar cooling lead, VPD humidify/dehumidify hysteresis, effective VPD edges, and fog escalation thresholds. This keeps history and future bound into one continuous graph without flattening the forecast.
- `fn_band_setpoint_provenance(ts, greenhouse_id)` is the operator source trace for the four rendered compliance edges. It shows crop target value, dispatcher-derived value, latest pushed firmware setpoint, latest `cfg_*` readback, latest planner context, and the source chain. Use this table for "where did this setpoint come from?" instead of adding more lines to the trend graph.
- `fn_band_trace(start_ts, end_ts, greenhouse_id)` returns raw and smoothed climate, crop band, firmware band, cfg readback band, compliance flags for crop and firmware bands, readback match flags, and `trace_quality_flag`.
- `v_band_trace_recent` is the rolling 14-day production trace.
- `v_band_trace_latest` is the latest production sample.
- `fn_setpoint_at(greenhouse_id, parameter, ts)` is the greenhouse-aware pushed-setpoint lookup. The older `fn_setpoint_at(parameter, ts)` remains for legacy consumers.

## Runtime Contract

- `ingestor/tasks.py::setpoint_dispatcher()` must use `fn_house_vpd_control_band(now())` for `vpd_low` and `vpd_high`.
- `api/main.py::get_setpoints()` must use the same function so the legacy ESP32 polling fallback matches direct pushes.
- Temperature still uses the crop band directly for future projection today; VPD may differ because firmware controls one air mass while zone mister targets remain local.
- The VPD compliance fill may look smoother than temperature because it is the normalized whole-house VPD control band. Temperature uses the crop temperature envelope directly.
- Planner- and public-facing compliance language must say "firmware-enforced band" unless it explicitly uses the crop compliance flags from `fn_band_trace`.
- Operator trend graphs should stay sparse: actual climate and forecast pressure plus the green firmware-compliance low/high band. Do not render planner setpoint rows, derived actuator triggers, padding thresholds, or event rails on the public operator graph. Keep crop provenance, clear thresholds, hysteresis padding, heat-stage details, and readback proof in `fn_band_setpoint_provenance()` / `fn_band_timeline()` tables and tests rather than rendering every derived line.

## Deployment Notes

This contract touches `verdify_schemas/**`, `ingestor/tasks.py`, `api/main.py`, and DB functions. After merge, bounce:

- `verdify-api`
- `verdify-ingestor`

No firmware OTA is required for this traceability change.
