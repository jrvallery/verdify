# Greenhouse control-loop audit - 2026-05-16

Scope: qualitative and quantitative review of the live Verdify greenhouse
control loop: planner prompts and MCP writes, dispatcher setpoint pushes,
API/setpoint fallback surfaces, ingestor readbacks, firmware enforcement,
historical performance, tunables, equipment utilization, and the public graph
contract.

Data was queried from live TimescaleDB on 2026-05-16. Local audit snapshots are
in America/Denver.

## Executive summary

The current setpoint delivery path is healthy. At 2026-05-16 09:42 MDT, the
current active plan (`iris-20260516-0545`) had 37 planner-owned tactical params;
all 37 matched active plan -> latest pushed value -> ESP32 cfg readback, with
zero exceptions. The two elapsed transition blocks in that plan also landed
cleanly: 52 changed elapsed rows, 26 already at value, 26 first pushes matched,
0 mismatches, 0 missing pushes, p50/p95 push latency 59/59 seconds, and
p50/p95 readback confirmation latency 39/81 seconds.

The band ownership model is now correct: planner rows no longer own
`temp_low`, `temp_high`, `vpd_low`, or `vpd_high`; those edges come from crop
targets and dispatcher/house-band derivation. Current band provenance confirms
crop -> dispatcher -> pushed firmware setpoint -> cfg readback alignment. The
operator graphs should keep showing only actual/forecast plus the green
firmware-compliance bands; detailed trigger/padding/provenance belongs in audit
tables, not as many trend lines.

Recent history shows a necessary nuance: guardrails can intentionally prevent a
planned transition value from becoming the pushed value at the transition
timestamp. On 2026-05-15, VPD-high moisture guardrails held or clamped mist/fog
thresholds during dry stress, then restored plan values once safe. That is good
safety behavior, but the audit surface must label it explicitly as
`held_by_guardrail` or `first_push_guardrailed`; otherwise it looks like
transition drift.

Control performance is improving versus the baseline-off window, but the last
week degraded under hot/dry weather. The dominant greenhouse failure mode is
still hot/dry `VENTILATE`: high fan and vent runtime, high water use, frequent
VPD-high stress, and only partial fog/mister assistance. This is a real physics
and tuning problem, not just a visualization problem.

## End-to-end ownership

| Layer | Owns | Evidence |
|---|---|---|
| Crop target model | Temperature and crop VPD ideal bands | `fn_band_setpoints(ts)`, `crop_target_profiles` |
| House-band derivation | Firmware-enforced whole-house VPD band | `ingestor/tasks.py::_house_vpd_control_band()` and `fn_house_vpd_control_band()` |
| Planner/MCP | 37 tactical policy knobs, not the four band edges | `mcp/server.py` validates required planner params and drops band-owned params before `setpoint_plan` writes |
| Dispatcher | Converts active plan + band functions into ESPHome pushes; applies registry and physics guardrails | `ingestor/tasks.py::setpoint_dispatcher()` |
| API/setpoint fallback | Reports current effective setpoints; must use computed bands for band-owned params | `api/main.py::get_setpoints()`, `scripts/setpoint-server.py` |
| ESP32 firmware | Owns relay decisions, safety, dwell, mode transitions, and cfg readbacks | `firmware/lib/greenhouse_logic.h`, ESPHome `cfg_*` sensors |
| Ingestor confirmation | Converts ESP32 cfg readbacks into `setpoint_changes.confirmed_at` | `ingestor/ingestor.py::write_setpoint_snapshot()` confirmation path |
| Public graphs | Operator story: actual/forecast climate plus compliance band | `fn_band_timeline()`, Grafana site dashboards |

The desired sentence is now true for the current system:

`crop profiles -> band functions -> dispatcher/API fallback -> setpoint_changes -> ESP32 cfg_* readback -> firmware enforcement -> daily compliance`

For planner-owned tunables:

`planner prompt/context -> MCP set_plan -> setpoint_plan -> v_active_plan -> dispatcher guardrails -> setpoint_changes -> ESP32 cfg_* readback -> firmware enforcement`

## Current setpoint fidelity

Current active planner-owned params at 2026-05-16 09:42 MDT:

| Check | Result |
|---|---:|
| Active planner-owned params | 37 |
| Latest pushed value matches active plan | 37 / 37 |
| Latest ESP32 readback matches active plan | 37 / 37 |
| Latest pushed row confirmed | 37 / 37 |
| Exceptions | 0 |

Current active plan transition audit:

| Plan | Created MDT | Changed elapsed rows | Already at value | First push matched | Guardrailed | Mismatch | No push within 10m | Max push | Max confirm |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `iris-20260516-0545` | 2026-05-16 05:47 | 52 | 26 | 26 | 0 | 0 | 0 | 59s | 81s |

Transition block detail:

| Transition MDT | Changed params | Already | Matched | Guardrailed | Bad | Max push | Max confirm |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-05-16 05:50 | 37 | 26 | 11 | 0 | 0 | 53s | 81s |
| 2026-05-16 08:30 | 15 | 0 | 15 | 0 | 0 | 59s | 39s |

Current band provenance at 2026-05-16 09:45 MDT:

| Param | Crop target | Dispatcher | Latest pushed | ESP32 readback | Source |
|---|---:|---:|---:|---:|---|
| `temp_high` | 78.0 | 78.0 | 78.0 | 78.0 | `fn_band_setpoints` |
| `temp_low` | 71.5 | 71.5 | 71.4 | 71.4 | `fn_band_setpoints` |
| `vpd_high` | 1.125 | 1.256 | 1.25 | 1.25 | `fn_house_vpd_control_band` |
| `vpd_low` | 0.7375 | 0.706 | 0.70 | 0.70 | `fn_house_vpd_control_band` |

The VPD crop target and firmware value differ by design. The firmware controls
one air mass, so the dispatcher derives a widened/shifted house VPD band from
crop and zone targets.

## Recent transition fidelity

Last 36h plan audit, using only active rows and elapsed transitions:

| Plan | Changed elapsed rows | Already | Matched | Guardrailed | Mismatch | No plan push within 10m | Interpretation |
|---|---:|---:|---:|---:|---:|---:|---|
| `iris-20260516-0545` | 52 | 26 | 26 | 0 | 0 | 0 | Clean |
| `iris-20260515-2010` | 78 | 27 | 39 | 1 | 0 | 11 | Moisture params were held by VPD-high guardrails and restored later |
| `iris-20260515-0546` | 93 | 26 | 60 | 7 | 0 | 0 | Clean after accounting for guardrails |

Examples from `iris-20260515-2010`:

| Transition | Param | Planned | First matching push | Notes |
|---|---|---:|---|---|
| 2026-05-15 20:15 | `fog_escalation_kpa` | 0.5 | 20:43 | Held near 0.2 by VPD-high guardrail, then restored |
| 2026-05-15 20:15 | `mister_all_kpa` | 1.2 | 20:43 | Held near 1.06 by VPD-high guardrail, then restored |
| 2026-05-15 20:15 | `mister_engage_kpa` | 1.0 | 20:43 | First push at 20:23 was guardrailed to 0.86, then restored |
| 2026-05-15 22:30 | `fog_escalation_kpa` | 0.9 | 23:03 | Held by guardrail, restored later |
| 2026-05-15 22:30 | `mister_all_kpa` | 1.85 | 23:03 | Held by guardrail, restored later |
| 2026-05-15 22:30 | `mister_engage_kpa` | 1.45 | 23:03 | Held by guardrail, restored later |

Conclusion: pushed setpoints accurately follow transitions when guardrails allow
the transition. The current missing audit affordance is a first-class
`held_by_guardrail` status when the requested value is evaluated but the
applied value remains unchanged, so no new `setpoint_changes` row is emitted.

## Historical performance

Daily KPI windows:

| Window | Compliance | Temp compliance | VPD compliance | Stress h/day | Heat stress | Cold stress | VPD high stress | VPD low stress | Cost/day | Water/day | Planner score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Last 30 complete days | 42.2% | 57.0% | 61.7% | 19.30 | 5.61 | 4.60 | 7.58 | 1.50 | $5.50 | 441 gal | 46.5 |
| Last 14 complete days | 53.2% | 68.1% | 64.8% | 15.91 | 5.59 | 1.99 | 6.56 | 1.77 | $5.64 | 590 gal | 55.1 |
| Last 7 complete days | 45.8% | 61.6% | 55.9% | 19.76 | 8.54 | 0.66 | 8.34 | 2.23 | $5.02 | 750 gal | 49.9 |
| 2026-05-16 partial | 98.2% | 98.9% | 99.3% | 0.17 | n/a | n/a | n/a | n/a | n/a | n/a | 98.3 |

Baseline comparison:

| Period | Dates | Compliance | Temp compliance | VPD compliance | Stress h/day | VPD-high stress | Cost/day | Water/day | Score |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline-off | 2026-04-22 to 2026-04-25 | 20.1% | 45.3% | 30.1% | 29.80 | 15.90 | $6.05 | 428 gal | 28.0 |
| Post-Iris | 2026-04-26 to 2026-04-29 | 47.9% | 61.0% | 74.8% | 15.41 | 3.82 | $4.37 | 130 gal | 52.5 |
| Recent 14d | 2026-05-02 to 2026-05-15 | 53.2% | 68.1% | 64.8% | 15.91 | 6.56 | $5.64 | 590 gal | 55.1 |
| Recent 7d | 2026-05-09 to 2026-05-15 | 45.8% | 61.6% | 55.9% | 19.76 | 8.34 | $5.02 | 750 gal | 49.9 |

The planner/control loop improved substantially over baseline-off, especially
VPD stress and operating cost. The last seven days regressed under warmer,
drier weather; water use rose sharply while compliance fell.

Worst recent days:

| Date | Compliance | Temp | VPD | Stress h | Heat stress | VPD-high stress | Temp max | VPD max | Water |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026-05-11 | 24.5% | 49.8% | 33.2% | 28.08 | 10.92 | 11.45 | 89.0F | 2.35 | 257 gal |
| 2026-05-14 | 43.7% | 52.5% | 54.5% | 22.27 | 11.37 | 10.90 | n/a | n/a | 821 gal |
| 2026-05-10 | 40.2% | 65.7% | 44.8% | 21.49 | n/a | n/a | n/a | n/a | 1169 gal |
| 2026-05-15 | 64.7% | 74.8% | 73.8% | 12.33 | 5.83 | 6.28 | n/a | n/a | 1513 gal |

## Equipment utilization

Fourteen-day equipment totals:

| Equipment | Runtime | Cycles | Avg min/day | Max min/day |
|---|---:|---:|---:|---:|
| `heat1` | 10288 min | 355 | 735 | 1389 |
| `vent` | 6183 min | 219 | 442 | 823 |
| `fan2` | 4483 min | 431 | 320 | 730 |
| `fan1` | 4407 min | 415 | 315 | 704 |
| `heat2` | 3305 min | 275 | 254 | 1016 |
| `fog` | 2083 min | 715 | 160 | 399 |
| `mister_center` | 1440 min | 1402 | 103 | 196 |
| `mister_west` | 608 min | 541 | 43 | 151 |
| `mister_south` | 393 min | 433 | 28 | 53 |

State durations over 14 days:

| Mode | Runtime | Transitions | Avg h/day |
|---|---:|---:|---:|
| `IDLE` | 214.23h | 345 | 15.30 |
| `VENTILATE` | 99.58h | 173 | 7.66 |
| `SEALED_MIST_S1` | 17.98h | 292 | 1.38 |
| `DEHUM_VENT` | 4.47h | 48 | 0.32 |
| `SEALED_MIST_S2` | 1.62h | 69 | 0.12 |
| `SEALED_MIST_FOG` | 0.04h | 2 | 0.00 |

Mister effectiveness, 14 days:

| Zone | Cycles | Avg duration | Avg VPD drop | p50 drop | p90 drop |
|---|---:|---:|---:|---:|---:|
| center | 1387 | 61.9s | 0.080 kPa | 0.070 | 0.220 |
| west | 540 | 67.4s | 0.082 kPa | 0.070 | 0.260 |
| south | 398 | 54.9s | 0.118 kPa | 0.100 | 0.270 |

Interpretation:

- The greenhouse is spending many hours in `VENTILATE`, and hot/dry stress is
  still common in that mode.
- Fog runtime is high, but `SEALED_MIST_FOG` mode runtime is nearly zero. Fog
  is likely firing mostly as vent assist or under other equipment paths; the
  mode/equipment taxonomy should be reconciled.
- Center mister is used heavily but has lower VPD drop per cycle than south.
  Zone weighting and nozzle/equipment placement deserve review.

## Forecast quality

Last 14 days, forecast accuracy by lead bucket:

| Variable | Lead | Bias | MAE |
|---|---:|---:|---:|
| Temp | 0-6h | +0.03F | 2.40F |
| Temp | 6-24h | +0.21F | 2.58F |
| Temp | 24-48h | -0.49F | 2.84F |
| Temp | 48h+ | -0.76F | 7.82F |
| VPD | 0-6h | +0.63 kPa | 0.87 kPa |
| VPD | 6-24h | +0.68 kPa | 0.91 kPa |
| VPD | 24-48h | +0.63 kPa | 0.87 kPa |
| VPD | 48h+ | +0.36 kPa | 0.61 kPa |
| Solar | 0-6h | +36.8 W/m2 | 83.9 W/m2 |
| Solar | 6-24h | +33.8 W/m2 | 83.7 W/m2 |

The VPD forecast is materially high-biased. The planner should receive and use
bias-corrected VPD/confidence, or its dry-stress tactics will overfit noisy
forecast pressure. That does not remove the observed live VPD-high stress; it
means forecast-driven anticipation needs calibration.

## Tunable surface

Registry summary:

| Metric | Count |
|---|---:|
| Total registry tunables | 106 |
| Planner-pushable Tier 1 | 37 |
| Tier 2/operator/other | 69 |
| Push owner `planner` | 58 |
| Push owner `band` | 12 |
| Push owner `operator` | 29 |
| Control class `planner_policy` | 37 |
| Control class `crop_band` | 8 |
| Control class `controller_safety` | 47 |
| Retired | 11 |
| Planner-pushable without readback | 0 |

Current active planner-owned values:

| Param | Current | Impact |
|---|---:|---|
| `d_heat_stage_2` | 5.0 | Heat2 staging threshold; band-first firmware now latches heat2 at raw `temp_low` when needed |
| `d_cool_stage_2` | 2.0 | Fan2/cooling escalation; effective value is capped by band width |
| `temp_hysteresis` | 1.5 | Temperature transition hysteresis |
| `heat_hysteresis` | 1.2 | Heat recovery/deadband |
| `vpd_hysteresis` | 0.4 | VPD transition hysteresis; firmware caps effective hysteresis to band width |
| `mister_engage_kpa` | 1.05 | S1 moisture threshold |
| `mister_all_kpa` | 1.20 | All-zone moisture threshold |
| `mister_engage_delay_s` | 45 | S1 delay |
| `mister_all_delay_s` | 90 | S2/all delay |
| `mister_water_budget_gal` | 600 | Water budget ceiling |
| `mister_pulse_on_s` | 60 | Mister pulse duration |
| `mister_pulse_gap_s` | 30 | Gap between mist pulses |
| `mister_vpd_weight` | 2.6 | Zone selection/scoring weight |
| `min_fog_on_s` | 45 | Fog min on |
| `min_fog_off_s` | 60 | Fog min off |
| `min_heat_on_s` | 120 | Heat min on |
| `min_heat_off_s` | 180 | Heat min off |
| `min_vent_on_s` | 60 | Vent min on |
| `min_vent_off_s` | 60 | Vent min off |
| `vpd_watch_dwell_s` | 45 | Time above VPD edge before humidity action is ready |
| `mist_max_closed_vent_s` | 180 | Closed-vent mist limit |
| `mist_thermal_relief_s` | 90 | Mist thermal relief timing |
| `enthalpy_open` | -2 | Economizer open threshold |
| `enthalpy_close` | 1 | Economizer close threshold |
| `sw_summer_vent_enabled` | 1 | Summer vent preference enabled |
| `vent_prefer_temp_delta_f` | 5 | Outdoor cooler-by threshold |
| `vent_prefer_dp_delta_f` | 5 | Outdoor drier-by threshold |
| `outdoor_staleness_max_s` | 600 | Outdoor data freshness gate |
| `sw_fog_closes_vent` | 1 | Fog/vent interlock policy |
| `sw_mister_closes_vent` | 1 | Mister/vent interlock policy |
| `bias_heat` | 0.1 | Low/no effect in band-first main heat threshold |
| `bias_cool` | 0.0 | Low/no effect in band-first main cool threshold |
| `sw_dwell_gate_enabled` | 1 | Dwell gate enabled |
| `dwell_gate_ms` | 300000 | Five-minute dwell gate |
| `sw_fsm_controller_enabled` | 1 | Production band-first controller path |
| `mist_backoff_s` | 700 | Mist backoff |
| `fog_escalation_kpa` | 0.3 | Fog escalation margin above VPD high |

Guardrails are active:

| Last 14d clamp | Count | Meaning |
|---|---:|---|
| `mister_engage_kpa` | 74 | Planner requested moisture threshold too conservative during VPD stress |
| `vpd_low` | 63 | Registry/band limit clamps around 1.01-1.05 -> 1.0 |
| `mister_all_kpa` | 63 | Registry and VPD-high guardrail clamps |
| `fog_escalation_kpa` | 60 | Fog threshold pulled down during VPD-high stress |
| `mister_pulse_gap_s` | 38 | Mist cadence pulled tighter |
| `mister_all_delay_s` | 35 | All-zone delay pulled shorter |
| `mister_engage_delay_s` | 35 | S1 delay pulled shorter |
| `min_fog_off_s` | 25 | Fog off-time pulled shorter |
| `temp_high` | 7 | Band high-edge clamps |

This is not silent drift. It is traceable protection. But frequent guardrails
mean the planner is still not fully internalizing live dry-stress policy.

## Alerts and data health

At audit time, active severe alerts were clear and system health was good:

| Surface | Status |
|---|---|
| Sensor health score | 100.0 |
| Alert load score | 100.0 |
| Equipment health score | 100.0 |
| Controller score | 98.7 |
| Controller details | uptime 49023s, heap 45.8KB, WiFi RSSI -43 |

Thirty-day alert history still matters:

| Alert | Count | Notes |
|---|---:|---|
| `setpoint_unconfirmed` critical | 1046 | Latest May 9; confirmation path now clean |
| `sensor_offline` warning | 191 | Historical sensor reliability risk |
| `heap_pressure_critical` | 147 | Firmware stability risk |
| `esp32_reboot` | 97 | Firmware/device stability risk |
| `leak_detected` | 95 | Physical ops risk |
| `vpd_stress` | 92 | Climate stress remains real |
| `vpd_extreme` | 84 | Climate stress remains real |
| `firmware_relief_ceiling` | 73 | Prior relief/vent behavior risk |
| `firmware_vent_latched` | 65 | Prior vent latch risk |
| `planner_required_plan_missed` | 12 | Planner lifecycle risk |
| `planner_stale` critical | 8 | Planner freshness risk |
| `planner_band_ownership_drift` critical | 1 | Fixed by dropping band-owned planner params |

Data pipeline health was generally fresh. `equipment_state` showed old age by
heartbeat-style freshness checks, but equipment is event-driven; that view
should distinguish state-change tables from true heartbeat tables.

## What is working

- Current transition fidelity is clean for planner-owned tunables.
- Band provenance is traceable from crop target through dispatcher and ESP32
  readback.
- Planner writes are constrained: band-owned params are dropped before
  `setpoint_plan`, and required tactical params are validated.
- Dispatcher guardrails are catching unsafe or counterproductive planner
  requests.
- ESP32 remains the deterministic relay authority; the AI does not directly
  own relays.
- Post-Iris performance materially beat the baseline-off window.
- The public graph contract is now simpler and more truthful: compliance bands,
  not a pile of derived actuator thresholds.

## What is broken or weak

- Guardrail-held transitions are not represented cleanly enough. Some cases
  look like "no plan push within 10m" even though the dispatcher intentionally
  held the applied value and restored the plan later.
- The planner still requests moisture thresholds that guardrails must override
  during VPD-high stress.
- Recent climate performance degraded under hot/dry conditions despite high
  fan, vent, water, fog, and mister utilization.
- VPD forecast bias is large enough to distort planning unless corrected.
- `SEALED_MIST_FOG` mode time and physical fog runtime do not tell the same
  story; mode/equipment taxonomy needs a reconciliation view.
- Planner validation lifecycle is incomplete for some recent plans; scorecards
  should close the loop more consistently.
- The tunable surface is still broad. Thirty-seven Tier 1 knobs is workable
  only with strict grouping, scoring, and guardrail feedback.
- Some Tier 1 knobs, especially `bias_heat` and `bias_cool`, have low or
  ambiguous effect under the current band-first firmware path.

## Automation approach

Do not move to agent-direct relay control. The right architecture remains:

1. Planner proposes bounded tactical policy for the next horizon.
2. MCP validates schema, trigger correlation, and parameter ownership.
3. Dispatcher derives crop/house bands, applies safety/physics guardrails, and
   writes traceable setpoint pushes.
4. ESP32 owns deterministic relay control every control tick.
5. Telemetry, readbacks, clamps, and scorecards feed back into the next plan.

Compared with alternatives:

| Approach | Fit |
|---|---|
| Agent-direct control | Too risky for live physical operations; poor auditability |
| Pure static thermostat bands | Safe but leaves forecast, solar, and equipment learning unused |
| PID-only | Useful for one actuator/one variable, weak for vent/fog/mister coupling and hard safety constraints |
| Full MPC | Attractive later, but needs better calibrated plant model and actuator cost model |
| Current bounded-agent + deterministic firmware | Best current fit; needs stronger guardrail feedback and equipment utilization scoring |
| Future zone-voting firmware | Good longer-term direction for heterogeneous zones and multi-actuator decisions |

## Recommended backlog

P0 Track A:

1. Add a guardrail-aware transition audit view:
   `plan_id`, `transition_ts`, `parameter`, `planned`, `applied`, `readback`,
   `status`, `guardrail_reason`, `push_latency`, `confirm_latency`.
   Required statuses: `already_at_value`, `matched`, `guardrailed`,
   `held_by_guardrail`, `missed`, `mismatch`.
2. Emit a guardrail/hold audit row even when the applied value is unchanged and
   no `setpoint_changes` row is inserted. This closes the false "no push" gap.
3. Feed clamp and hold counts back into planner scoring. A plan that repeatedly
   needs VPD-high guardrails should lose score even if the greenhouse survives.
4. Update the planner context to explicitly show recent guardrail holds by
   transition block, not just current values.
5. Keep the public graphs sparse: actual/forecast plus green compliance band.
   Put provenance and trigger padding in audit tables and evidence pages.

P1 control performance:

1. Review hot/dry `VENTILATE` policy: fan2 staging, fog assist, mister assist,
   and vent interlocks during concurrent temp-high and VPD-high.
2. Add equipment-utilization penalties to plan evaluation: fan+vent hours,
   water per VPD-stress hour, fog cycles, and repeated short mister cycles.
3. Bias-correct VPD forecasts before planner use and include confidence by
   lead bucket.
4. Demote low-effect knobs from Tier 1 or group them behind higher-level regime
   controls.
5. Reconcile fog runtime with mode duration so operator graphs and scorecards
   explain what physical equipment actually did.

P2 physical and product:

1. Continue physical-capacity work in parallel: shade, airflow, evaporative
   capacity, nozzle placement, and dry outdoor air strategy.
2. Publish the guardrail-aware trace as part of the Verdify evidence story.
3. Turn the audit into a repeatable daily job and public evidence artifact.

## Verification run

- `make lint` passed after band/API/dispatcher/test changes.
- `make test` passed: 365 passed, 2 skipped, 1 xfailed.
- `make site-doctor` passed with 0 findings.
- Grafana render checks for home/climate/planning panels returned nonblank
  images with green compliance-band pixels.
- Live `/setpoints` and FastAPI `/setpoints` agreed with pushed band values
  within the normal dispatcher cadence.
- Current transition audit at 2026-05-16 09:42 MDT showed 0 exceptions for
  active planner-owned params and 0 failed elapsed transition rows.

## Completion audit

| Requirement | Covered |
|---|---|
| Planner code path | MCP validation, band ownership, 37 tactical params, prompt/provenance context |
| Dispatcher code path | Band derivation, active plan overlay, guardrails, push attribution |
| Firmware code path | Band-first deterministic relay ownership and cfg readbacks |
| Ingestor code path | Telemetry, snapshots, `confirmed_at`, alerts, daily summaries |
| API/fallback path | `/setpoints` and setpoint-server band-owned semantics |
| Historical performance | 30d/14d/7d, baseline-off vs Post-Iris, worst recent days |
| Tunables/params/values | Registry summary, current 37 active values, band values, guardrails |
| Equipment utilization | Runtime, cycles, modes, mister effectiveness |
| Forecast quality | Temp/VPD/solar bias and MAE |
| Setpoint transition fidelity | Current and recent plan transition audits |
| Working/broken/improve | Explicit sections and prioritized backlog |
