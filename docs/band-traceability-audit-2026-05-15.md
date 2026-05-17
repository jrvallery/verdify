# Band traceability audit - 2026-05-15

Scope: trace the home page "target band" graphs for temperature and VPD back through Grafana, database band functions, dispatcher writes, ESP32 cfg readbacks, and firmware enforcement. Data below was queried from live TimescaleDB on 2026-05-15 17:22 MDT. Latest climate row at audit time: 2026-05-15 17:21 MDT.

## Executive summary

The temperature band is mostly traceable end-to-end. The home graph draws `fn_band_setpoints(ts)` and the dispatcher pushes rounded values from the same function to firmware. Last-72h differences are small on average (`0.04 deg F` average low-edge delta, `0.5 deg F` max), mostly from the dispatcher's 1% deadband between pushes.

The VPD band is not the same end-to-end. The home graph draws the crop-science band from `fn_band_setpoints(ts)`. The firmware is enforcing the dispatcher's *house VPD band*, which starts with `fn_band_setpoints(now())` but is then widened/shifted by `_house_vpd_control_band()` using zone VPD targets and a `0.55 kPa` minimum width. Last-72h VPD graph-vs-firmware mismatch was 100% of samples; firmware `vpd_high` averaged `0.179 kPa` above the graph high edge and was as much as `0.330 kPa` higher.

Compliance percentages on the home page are valid for the firmware-enforced setpoint timeline, not for the crop band drawn on the home VPD graph. Over the last 72h, raw firmware-band both-axis compliance was `50.5%`; the smoothed line against the graph's crop band would read `38.2%`. That explains why the graph looks worse than the compliance card: they are measuring different VPD windows.

The greenhouse really is riding above the enforced band during hot/dry periods. Last 72h, smoothed temperature was above the firmware high edge `42.6%` of samples and smoothed VPD was above the firmware high edge `39.6%`. `36.3%` of samples were both temp-high and VPD-high. This is not only a visualization bug; the dominant failure mode is hot/dry concurrent stress during `VENTILATE`.

## Trace path

| Layer | Temperature band | VPD band |
|---|---|---|
| Home page | `/mnt/iris/verdify-vault/website/index.md` embeds `site-home` panel `30` | `/mnt/iris/verdify-vault/website/index.md` embeds `site-home` panel `31` |
| Grafana panel | `grafana/dashboards/site-home.json`, panel `30`, target `C`: `fn_band_setpoints(t.ts).temp_low/temp_high` on a 30-minute timeline | `grafana/dashboards/site-home.json`, panel `31`, target `C`: `fn_band_setpoints(t.ts).vpd_low/vpd_high` on a 30-minute timeline |
| Actual graphed line | 15-sample rolling average of `climate.temp_avg` | 30-sample rolling average of `climate.vpd_avg` |
| Crop DB function | `fn_band_setpoints(target_ts)` interpolates hourly `crop_target_profiles` for season `spring` | Same function |
| Zone DB function | Not used for global temp band | `fn_zone_vpd_targets(target_ts)` derives per-zone VPD high targets from active crops |
| Dispatcher | `ingestor/tasks.py::setpoint_dispatcher()` pushes `temp_low/temp_high` from `fn_band_setpoints(now())` | Dispatcher calls `_house_vpd_control_band()`, then pushes `vpd_low/vpd_high` from that derived house band |
| Audit table | `setpoint_changes` records pushed values with `source='band'` | Same |
| Readback | `setpoint_snapshot` records ESP32 cfg readbacks; `setpoint_changes.confirmed_at` is set on match | Same |
| ESPHome map | `ingestor/entity_map.py` maps `temp_low/temp_high` to `set_temp_low__f` / `set_temp_high__f` | maps `vpd_low/vpd_high` to `set_vpd_low_kpa` / `set_vpd_high_kpa` |
| Firmware ingest | `firmware/greenhouse/tunables.yaml` writes globals `target_temp_low_f` / `target_temp_high_f` | writes globals `target_vpd_low_kpa` / `target_vpd_high_kpa` |
| Control model | `firmware/greenhouse/controls.yaml` builds `Setpoints`; `greenhouse_logic.h` uses band-first control | Same, plus VPD effective interior edges for fog/dehum relay behavior |

Important stale path: `api/main.py::get_setpoints()` still computes VPD band directly from `fn_band_setpoints(now())`, not `_house_vpd_control_band()`. Current firmware contract says the HTTP poller is intentionally absent and direct ESPHome push is the live path. If HTTP fallback is re-enabled, it will disagree with current dispatcher VPD semantics.

## Current snapshot

Latest sampled row during audit:

| Metric | Value |
|---|---:|
| Local sample time | 2026-05-15 17:09 MDT |
| Indoor temp / VPD | `72.3 deg F` / `0.94 kPa` |
| Graph crop temp band | `67.7-73.7 deg F` |
| Firmware/readback temp band | `67.8-73.8 deg F` |
| Graph crop VPD band | `0.57-0.86 kPa` |
| Firmware/readback VPD band | `0.54-1.09 kPa` |
| Zone VPD targets | south `1.58`, west `1.20`, east `0.98`, center `0.86` kPa |

Current firmware readbacks matched the last pushed value exactly for all checked band/tactical parameters: `temp_low`, `temp_high`, `vpd_low`, `vpd_high`, `vpd_target_*`, `mister_engage_kpa`, `mister_all_kpa`, `vpd_hysteresis`, `vpd_watch_dwell_s`, `d_cool_stage_2`, `bias_cool`, and `sw_fsm_controller_enabled`.

## Graph band vs firmware band

Last 72h, climate samples compared at each sample timestamp:

| Edge | Average delta | Max delta | Mismatch rate |
|---|---:|---:|---:|
| Temp low | `0.040 deg F` | `0.500 deg F` | `17.3%` temp edge mismatch > `0.11 deg F` |
| VPD low | `0.056 kPa` | `0.140 kPa` | `100.0%` VPD edge mismatch > `0.011 kPa` |
| VPD high | `0.179 kPa` | `0.330 kPa` | included in same `100.0%` VPD mismatch |

Interpretation:

- Temperature is aligned enough for operational use. The visible green band is the same policy the firmware receives, with small dispatcher deadband lag.
- VPD is intentionally not aligned: graph = crop target envelope; firmware = widened house-control envelope. That needs to be visible on the graph or the graph should use the firmware envelope when it is presented as "what the ESP32 is enforcing."

## Compliance validation

The home compliance trend panels use `v_planner_performance`, whose live definition reads `daily_summary.compliance_pct`, `temp_compliance_pct`, and `vpd_compliance_pct`. Those daily columns are computed by `ingestor/tasks.py::_refresh_daily_summary_for_date()` from `climate` rows and the active `setpoint_changes` band timeline.

Recent recomputation from raw climate rows and setpoint intervals:

| Day | Samples | Daily both | Recomputed both | Daily temp | Recomputed temp | Daily VPD | Recomputed VPD |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-05-15 | 1032 | `69.4%` | `69.2%` | `74.4%` | `74.7%` | `77.3%` | `77.1%` |
| 2026-05-14 | 1437 | `43.7%` | `43.7%` | `52.5%` | `52.5%` | `54.5%` | `54.5%` |
| 2026-05-13 | 1436 | `45.3%` | `45.3%` | `47.4%` | `47.4%` | `66.5%` | `66.5%` |
| 2026-05-12 | 1439 | `48.3%` | `48.3%` | `63.5%` | `63.5%` | `58.1%` | `58.1%` |
| 2026-05-11 | 1441 | `24.5%` | `24.5%` | `49.8%` | `49.8%` | `33.2%` | `33.2%` |
| 2026-05-10 | 1440 | `40.2%` | `40.2%` | `65.7%` | `65.7%` | `44.8%` | `44.8%` |
| 2026-05-09 | 1438 | `53.6%` | `53.6%` | `77.8%` | `77.8%` | `60.6%` | `60.6%` |
| 2026-05-08 | 1437 | `56.8%` | `53.9%` | `68.7%` | `65.2%` | `62.8%` | `62.8%` |

Validation result:

- 2026-05-09 through 2026-05-14 match exactly.
- 2026-05-15 differs by at most `0.3 points`, expected because the daily summary was captured before the latest samples.
- 2026-05-08 differs on temp/both by `2.9-3.5 points`. That older mismatch should be investigated before claiming historical 30-day exactness. It does not affect the main finding: the current compliance cards are using firmware bands, not graph crop VPD bands.

Last-72h compliance comparison using the home graph smoothing:

| Measurement | Both-axis compliance |
|---|---:|
| Raw climate vs firmware band | `50.5%` |
| Smoothed graph line vs firmware band | `53.6%` |
| Raw climate vs graph crop band | `36.9%` |
| Smoothed graph line vs graph crop band | `38.2%` |

This is the key operator-facing mismatch: the visual VPD window is stricter than the compliance window.

## "Right outside the window" check

Last 72h, using smoothed values like the home graph:

| Axis/window | Outside rate | Average outside margin | Median outside margin | Max outside margin | Near-miss share |
|---|---:|---:|---:|---:|---:|
| Temp vs firmware band | `43.2%` | `2.09 deg F` | `1.74 deg F` | `6.95 deg F` | `12.4%` within `0.5 deg F` |
| Temp vs graph crop band | `44.0%` | `2.11 deg F` | `1.74 deg F` | `6.95 deg F` | `13.4%` within `0.5 deg F` |
| VPD vs firmware band | `39.6%` | `0.086 kPa` | `0.057 kPa` | `0.478 kPa` | `46.3%` within `0.05 kPa` |
| VPD vs graph crop band | `60.9%` | `0.230 kPa` | `0.212 kPa` | `0.676 kPa` | `7.7%` within `0.05 kPa` |

So the observation is half true in two different ways:

- Against the firmware VPD band, many misses are small: almost half of VPD misses are within `0.05 kPa`.
- Against the graph crop VPD band, the system is not merely "just outside"; it is often materially above the stricter crop high edge because the firmware's house band has been relaxed upward.

High-side breakdown over the same 72h:

| Band shown/evaluated | Temp low | Temp high | VPD low | VPD high |
|---|---:|---:|---:|---:|
| Firmware/enforced band | `0.6%` | `42.6%` | `0.0%` | `39.6%` |
| Graph crop band | `1.1%` | `42.9%` | `0.7%` | `60.2%` |

## Operational behavior during misses

Last 72h, smoothed firmware-band conditions:

| Condition | Samples | Share | Avg temp excess | Avg VPD excess | Fan on | Both fans | Fog on | Mister on |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| In band or low-side | 2342 | `54.3%` | | | `22.8%` | `0.2%` | `1.9%` | `3.6%` |
| Both temp and VPD high | 1566 | `36.3%` | `2.33 deg F` | `0.092 kPa` | `99.2%` | `69.6%` | `47.9%` | `33.0%` |
| Temp high only | 266 | `6.2%` | `0.82 deg F` | | `100.0%` | `23.3%` | `12.4%` | `16.9%` |
| VPD high only | 138 | `3.2%` | | `0.013 kPa` | `97.1%` | `0.0%` | `30.4%` | `6.5%` |

Mode distribution:

| Mode | Share | Temp high in mode | VPD high in mode | Fan on | Fog on | Mister on |
|---|---:|---:|---:|---:|---:|---:|
| `VENTILATE` | `57.4%` | `74.0%` | `68.7%` | `99.5%` | `35.0%` | `25.5%` |
| `IDLE` | `41.7%` | `0.0%` | `0.2%` | `0.6%` | `0.0%` | `1.2%` |
| `SEALED_MIST_*` combined | `<1%` | `0.0%` | `0.0%` | low | limited | limited |

Outdoor context for the same window:

| Day | Outdoor max | Outdoor min RH | Max solar | Afternoon outdoor RH avg |
|---|---:|---:|---:|---:|
| 2026-05-15 | `84.8 deg F` | `13.6%` | `1027 W/m2` | `15.4%` |
| 2026-05-14 | `88.6 deg F` | `13.8%` | `1099 W/m2` | `16.6%` |
| 2026-05-13 | `89.7 deg F` | `18.5%` | `1053 W/m2` | `26.8%` |
| 2026-05-12 | `77.8 deg F` | `26.4%` | `505 W/m2` | `28.3%` |

Interpretation: hot/dry VENTILATE is the main stress shape. The firmware is usually responding with fans, but not always with both fans, and moisture assist is active only part of the concurrent-stress time. Some of that is intentional gating; some is likely capacity or tuning headroom.

## Tunable impact trace

Current active tactical values at audit time:

| Tunable | Current | Firmware/control impact |
|---|---:|---|
| `temp_low/temp_high` | `67.8/73.8 deg F` readback | Firmware band edges. Band-first heat target is midpoint; cooling enters at high edge. Graph temp band is aligned except small dispatcher deadband lag. |
| `vpd_low/vpd_high` | `0.54/1.09 kPa` readback | Firmware house VPD band. Not the same as graph crop band `0.57/0.86 kPa`. |
| `vpd_target_south/west/east/center` | `1.58/1.20/0.99/0.87 kPa` readback | Zone mister selection and stress scoring. These do not define the home graph green VPD band. |
| `vpd_hysteresis` | `0.35 kPa` requested/readback | Firmware caps effective hysteresis to `33%` of band width. With current house width near `0.55 kPa`, effective VPD hysteresis is about `0.18 kPa`, not `0.35`. |
| `vpd_watch_dwell_s` | `30 s` | VPD must stay above firmware `vpd_high` for this dwell before humidification readiness. This deliberately ignores brief near-edge excursions. |
| `mister_engage_kpa` | `0.90 kPa` | Once humidity demand exists, S1 mister pulses can engage when average VPD exceeds this or a zone exceeds its zone target. |
| `mister_all_kpa` | `1.10 kPa` | Escalates to all-zone rotation after delay. Current average VPD at snapshot was `0.94`, above S1 engage but below all-zone threshold. |
| `mister_engage_delay_s/mister_all_delay_s` | `30 s / 60 s` | Adds latency before S1/S2 moisture action. Guardrail clamps recently forced more conservative planner requests back down to `45/90 s` when VPD was high. |
| `fog_escalation_kpa` | `0.18 kPa` | Fog in VENTILATE/SEALED_MIST requires VPD above effective high edge plus this margin, subject to RH/temp/time/occupancy gates. Guardrail recently clamped high requested values down to `0.15-0.30`. |
| `d_cool_stage_2` | `2.0 deg F` | Band-first code uses `min(d_cool_stage_2, 25% of temp band width)`. Current effective stage-2 fan delta is about `1.5 deg F` on a `6 deg F` band. Both fans were on only `69.6%` of concurrent temp+VPD high samples. |
| `bias_cool/bias_heat` | `-1.0/0.0 deg F` active | Under `sw_fsm_controller_enabled=1`, band-first heat/cool targets ignore these biases for the main heat/cool thresholds. `bias_cool=-1` is therefore probably low or no effect in the current controller path. |
| `sw_fsm_controller_enabled` | `1` | Confirms production is on the band-first path. |
| `sw_dwell_gate_enabled/dwell_gate_ms` | `1 / 300000 ms` | Holds non-safety mode transitions for up to 5 minutes unless preempted. Mode reasons showed `dwell_hold` events in the last 72h, so this can keep the controller intentionally just outside a threshold to prevent whipsaw. |

Recent guardrails:

| Clamp reason | Params affected | Count last 72h | Meaning |
|---|---|---:|---|
| `vpd_high_moisture_guardrail` | `mister_engage_kpa`, `mister_all_kpa`, delays, `mister_pulse_gap_s`, `min_fog_off_s`, `fog_escalation_kpa` | 272 total clamp rows | Dispatcher saw live VPD-high/near-edge stress and pulled planner moisture thresholds back near the active VPD band. This is working as intended and prevents the planner from delaying moisture correction too far above band. |

## What is working

- Band delivery to firmware is healthy. Last 72h, all checked band and tactical setpoint changes were `100%` confirmed by ESP32 readback. Average confirmation for band pushes was roughly `29-37 s`.
- Compliance math is now samples-in-band, not old stress-hour subtraction. Recent daily recomputation matches `daily_summary` for nearly all days checked.
- The dispatcher/fleet has a clear audit trail: `setpoint_changes`, `setpoint_snapshot`, `confirmed_at`, and `setpoint_clamps` make it possible to prove what the firmware was told.
- VPD moisture guardrails are active and useful. They detected high-VPD conditions and clamped overly conservative moisture thresholds.
- The controller is responding to hot conditions: fans were on `99.2%` of concurrent temp+VPD-high samples.

## What is broken or misleading

- Home VPD graph and compliance cards do not use the same VPD band. The graph shows crop band; compliance uses firmware house band. This is the top traceability break.
- The home copy says the green bands are the target envelope and the event markers show firmware actions. It does not say the VPD green band is stricter than the band the firmware actually enforces.
- The legacy HTTP `/setpoints` endpoint would disagree with the current direct dispatcher path for VPD if it were re-enabled.
- `bias_cool` is active in the plan but probably not effectful under the current band-first firmware path. The planner should not spend reasoning budget on it unless firmware uses it again.
- Historical validation is not fully closed: 2026-05-08 daily temp/both compliance differed from recomputation by `2.9-3.5 points`.
- The system is still materially hot/dry outside the enforced band in real conditions. The visualization mismatch does not explain away the stress.

## Improvements

P0 traceability fixes:

1. Change the home VPD panel to show both bands:
   - "Crop target band" from `fn_band_setpoints()`.
   - "Firmware enforced house band" from `setpoint_changes` / `fn_setpoint_at()` or a new `v_band_trace` view.
2. Rename compliance panels to "Firmware band compliance" or add a second "Crop target compliance" metric. Do not let one graph imply the other.
3. Add a small home/evidence trace table: crop band, firmware pushed band, latest cfg readback, delta, confirmation age.
4. Update or retire `/setpoints` so its VPD semantics match `_house_vpd_control_band()` if it remains a real fallback.
5. Add a CI or scheduled audit query that recomputes daily compliance from climate + setpoint intervals and flags any day where `daily_summary` differs by more than `0.5 points`.

P1 control improvements:

1. Investigate both-fan duty during concurrent temp+VPD-high stress. Both fans were on `69.6%` of samples where both axes were high. Since average temp excess was `2.33 deg F`, there may be room to stage fan 2 earlier or force both fans during concurrent hot/dry stress.
2. Review VENTILATE moisture assist thresholds against the enforced house band, not the graph crop band. In concurrent stress, fog was on `47.9%` and misters `33.0%`; VPD excess was small on average (`0.092 kPa`) but frequent.
3. Keep the moisture guardrail. Its clamp rows show it is preventing high planner thresholds from delaying correction.
4. Remove or demote `bias_cool/bias_heat` from planner Tier 1 while `sw_fsm_controller_enabled=1`, unless firmware is changed to consume them in the band-first path.
5. Consider physical/capacity mitigations in parallel with tunables: shade, evaporative capacity, vent/fan airflow, and dry outdoor air management. The last 72h were `85-90 deg F`, `14-18% RH`, and high solar; fans alone cannot guarantee band compliance.

P2 data model cleanup:

1. Make `fn_band_setpoints()` explicit about active-crop scope. It currently reads all spring `crop_target_profiles`; at audit time that matched active-crop output, but the function does not encode that intent.
2. Create a reusable `v_band_trace` view with:
   - `ts`
   - crop temp/VPD band from `fn_band_setpoints(ts)`
   - firmware temp/VPD band from `setpoint_changes`
   - latest cfg readback values
   - graph-smoothed temp/VPD
   - raw temp/VPD
   - per-axis compliance flags for both crop and firmware bands
3. Move Grafana panels and daily compliance validation to that view so graph provenance and metric provenance are inspectable in one place.

## Bottom line

Temperature traceability is mostly sound. VPD traceability is not: the graph's VPD target band is the crop-science target, while the firmware is enforcing a widened house-control band. The compliance percentages are defensible for the firmware band, but they should not be visually paired with the stricter crop VPD band without labeling both.

Operationally, the greenhouse is still spending a lot of time high on temp and VPD during hot/dry ventilation. The next work should separate UI truth from control truth, then focus control changes on concurrent hot/dry `VENTILATE`: earlier fan-2, clearer vent-mist/fog thresholds, and physical capacity checks.
