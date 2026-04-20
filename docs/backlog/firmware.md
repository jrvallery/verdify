# Backlog: `firmware`

Owned by the [`firmware`](../agents/firmware.md) agent. Sprint counter is agent-local (resets under the agent-org split — see `CLAUDE.md`).

## In flight

- **`firmware/sprint-10-phase0-completion`** — Phase 0 completion bundle per the agronomy review. **0.2** THERMAL_RELIEF now runs both fans (was lead-only). **0.4a** `dt_ms` clamped to 5 s at the caller (controls.yaml) — blocks RTOS-hang fast-forward through dwell timers. **0.4b** three hardcoded magic numbers (`1800000` ms vent-latch, `5.0` safety-max seal margin, `ECON_HEAT_MARGIN_F`) moved into `Setpoints` as `vent_latch_timeout_ms`, `safety_max_seal_margin_f`, `econ_heat_margin_f`; `validate_setpoints` clamps them. **0.4c** `vpd_min_safe` override extended to break SEALED_MIST (with state cleanup that mirrors the normal was_sealed exit). **0.3** Day/night setpoint pairs — 8 new `Setpoints` fields (`temp_{low,high}_{day,night}`, `vpd_{low,high}_{day,night}`), `is_photoperiod` on SensorInputs, `resolve_active_band()` helper with fallback to legacy generic fields. Hybrid `is_photoperiod` computation in controls.yaml (scheduled window OR tempest_lux > 5000). 8 new HA Number entities + photoperiod-window tunables. 11 new unit tests; 85/85 pass; replay clean.

## Recently landed

- **`firmware/sprint-9-quick-hardening`** — reviewer-recommended one-session bundle after sprint-8 validation: P1#7 Heat S2 latch via new `heat2_latched` bit in ControlState (prevents gas-valve rapid cycling); P2#8 relational asserts in `validate_setpoints()`; P1#4 R2-3 cycle-breaker bypass documented; P2#11 SAFETY_HEAT runs lead fan for canopy circulation. 10 new tests; 74/74 pass.
- **`firmware/sprint-8-r23-fog-helper`** — multi-reviewer synthesis P0 pass. P0#1 R2-3 FOG demotion, P0#2 sealed_timer reset, P0#3 midnight-wrap fog window, P1#5 safety reset symmetry, P1#6 fog_permitted helper, P3#14 "full battery" comment. **Bonus win confirmed by review:** resetting `vpd_watch_timer_ms` on safety entry also closed the stale-dwell-across-safety concern from the original P1#4.
- **`firmware/sprint-7-cycle-audit`** — per-zone cycle counters for misters + drips (5 new `cnt_*_today` globals + template sensors). Rising-edge counted in `turn_on_zone` and irrigation dispatch. Sensors live on ESP32; ingestor DAILY_ACCUM_MAP + coordinator migration queued as handoffs.
- **`firmware/sprint-6-midnight-audit`** — docs-only. 60-day telemetry found no midnight edge-case; midday crash clustering logged for a separate sprint.
- **`firmware/sprint-5-tooling`** — `make replay-corpus-refresh` + deploy-time `fw_version` bump. Corpus now covers through today; `diagnostics.firmware_version` is per-commit unique.
- **`firmware/sprint-4-leak-debounce`** — `bs_leak_detected` gained a 30 s bleed-down grace period + added `fog_rly` to the valve list. Post-deploy: 0 `leak_detected` transitions in first 5-min watch window (vs baseline 2.3/5min).
- **`firmware/sprint-3-cfg-readbacks`** — per-zone VPD target readback sensors. Ingestor routing in commit `4cc5df5`.
- **`firmware/sprint-2-zone-fairness`** — 10-min last-fire watchdog. Counter `mister_fairness_overrides_today`. Ingestor wire-up followed.
- **`firmware/sprint-1-housekeeping`** — drift fixes + dead-code cleanup + doc sync.

## Coordination queue (handoffs to other agents)

Findings from the 2026-04-18 audit that live outside firmware scope. Each is a focused handoff PR filed into the owning agent's scope, labeled `requested-by: firmware`:

- [x] **Coordinator — EquipmentId schema reconciliation.** ✅ Landed as ingestor sprint-24 hotfix (commit `4a89844`).
- [x] **Ingestor — route `mister_fairness_overrides_today`.** ✅ Landed as ingestor sprint-24-alignment; `daily_summary.mister_fairness_overrides_today` column exists.
- [x] **Ingestor — F10: `mister_state` / `mister_zone` STATE_MAP mismatch.** ✅ Landed as ingestor sprint-24-alignment; sensor_health is now 100% (0 stale).
- [ ] **Coordinator — override flag enum guard.** Add a drift guard that compares `OverrideEvent.override_type` against the 7 flag names in `firmware/lib/greenhouse_types.h` (`OverrideFlags` struct). Today the schema accepts any string; a silent rename would corrupt `override_events`.
- [ ] **Coordinator + genai — `sw_mister_closes_vent` routing.** Firmware handles the key in `controls.yaml`, but it's not in `verdify_schemas/tunables.py` ALL_TUNABLES or `entity_map.py` SETPOINT_MAP. Decide: add to schema or drop the firmware handler.
- [ ] **Ingestor — alert monitor coverage for OBS-3.** `scripts/alert-monitor.py` does not watch `diagnostics.relief_cycle_count > 0` (breaker latched) or `diagnostics.vent_latch_timer_s > 1200` (vent stuck in latched VENTILATE). Add both, plus firmware version staleness vs. an expected pin.
- [ ] **Ingestor — override events smoke test.** Add `test_override_events_written` to `tests/test_05_ingestor.py` to verify `gh_overrides` diff → `override_events` write.
- [ ] **Ingestor — `setpoint_unconfirmed` lifecycle fix.** alert_monitor tracks specific (param, value, push_ts) tuples; stale alerts persist indefinitely when a later push supersedes an older one before readback can confirm the older value. Net effect: 20+ critical alerts per 5 hours of active dispatch. Should resolve by latest-readback-for-parameter rather than require exact-push-match.
- [ ] **Coordinator — `daily_summary.cycles_{mister_south,mister_west,mister_center,drip_wall,drip_center}` columns (sprint-7 follow-up).** Firmware now emits these via `daily_mister_*_cycles` + `daily_drip_*_cycles` template sensors. Needs a migration to add the columns to `daily_summary`.
- [ ] **Ingestor — DAILY_ACCUM_MAP entries for the sprint-7 cycle sensors.** Slug keys: `cycles___mister_south__today_`, `cycles___mister_west__today_`, `cycles___mister_center__today_`, `cycles___drip_wall__today_`, `cycles___drip_center__today_`. Depends on the coordinator migration above.
- [ ] **Coordinator — `v_cycle_count_audit` view (sprint-7 follow-up).** Join `daily_summary.cycles_*` with per-day aggregates from `equipment_state` (count of state-true transitions). Flag divergence >5% as a warning. Depends on the column migration.
- [ ] **Ingestor — F12 triage: `v_stress_hours_today` semantics.** "32 h cold_stress/day" suggests zone-summing not clock-summing. Doc fix or view fix.
- [ ] **Genai — MCP `set_tunable()` validator.** Today MCP can push any key; if it's not in the firmware handler's accept list, it silently no-ops. Add a pre-push validation.
- [ ] **Saas — real-time setpoint push.** `controls.yaml` references an aioesphomeapi push path that doesn't exist. Either implement or drop the comment.

## Candidates (operational, co-owned with `saas`)

- [ ] **Cloud-fallback setpoints** (was Sprint 10 B10.6) — firmware OTA: add cloud URL as secondary setpoint source.
- [ ] **Direct MQTT to cloud** (was Sprint 10 B10.7) — firmware OTA: publish to `mqtt.verdify.ai` directly.
- [ ] **Cloud-only test window** (was Sprint 10 B10.8) — 24 h test: disable local ingestor, verify ESP32 runs from cloud.

## Ideas (not yet committed)

### Stability & safety

- **Midday crash-loop investigation** _(queued for sprint-10)_. 91 unexpected reboots in 60 days (Guru/Panic 51 + Task WDT 38 + 2 unknown), clustered at local hours 11-13 (33 crashes, peak 14 at hour 12). Rate ~1.5/day. Strong correlation with peak VPD + peak mister-state-machine activity. Phase 10a: read-only forensics (heap trajectory, state+equipment snapshot at crash − 1 tick, env envelope, modbus bus, RSSI, setpoint-pull coincidence). Phase 10b: fix or docs-only close. Real operational disruption — highest-severity remaining item.

### Phase 1 sensor wire-up _(queued for sprint-11)_

Extend `SensorInputs` to expose data already flowing through the ESP32 so the control logic can reason over it. No hardware orders — Tempest covers outdoor temp/RH/lux; `greenhouse_co2_ppm` is on the onboard ADC; `tempest_solar_w_m2` is live via UDP.

- `outdoor_temp_f` (from `tempest_temp_f` / `pulled_outdoor_temp_f`). Enables `vent_can_cool = outdoor_temp_f < temp_f - 2.0f` gate in VENTILATE/DEHUM_VENT decisions.
- `outdoor_dewpoint_f` (computed inside controls.yaml from outdoor temp + RH). Enables `vent_can_dehum = outdoor_dewpoint_f < inside_dewpoint_f - 2.0f` gate for DEHUM_VENT (prevents vent-exchanging saturated air for saturated air).
- `co2_ppm` (from `greenhouse_co2_ppm`). Enables a CO2 exchange cap on long sealed cycles during photoperiod (hard cap at `sealed_max_ms` regardless of timer is already the blunt proxy; this adds a proper `co2_ppm < 350` trigger).
- `solar_w_m2` (from `tempest_solar_w_m2`). Solar-driven enthalpy gain is a dominant term for sealed-daytime thermal runaway; this lets `sealed_max_ms` shrink under strong sun.
- `lux` (from `tempest_lux`, also used for `is_photoperiod`). Exposed so downstream decisions can read it directly.

Leaf MLX90614 (`leaf_temp_f` + computed `leaf_air_vpd_kpa`) is separately a hardware order and the only Phase 1 item that actually needs new hardware.

### P3 semantic polish _(queued for sprint-12)_

- **P3#12 — Include THERMAL_RELIEF in `was_ventilating`.** `was_ventilating = (prev in {VENTILATE, THERMAL_RELIEF})`. Prevents chatter at the post-relief boundary when temp is marginal.
- **P3#15 — Clarify `econ_block` vs `vpd_min_safe` policy.** Current behavior documented in sprint-10 `s10_vpd_min_safe_override_respects_econ_block` test: with `econ_block=true`, greenhouse stays in IDLE even at dangerous humidity. Either add an unconditional safety override (economy can't block safety) or document the intentional precedence.

### P4 code health _(queued for sprint-13)_

- **P4#17 — Remove dead occupancy branch in mist_stage progression.** `if (moisture_blocked) { state.mist_stage = MIST_WATCH; }` inside `if (mode == SEALED_MIST)` is unreachable (outer planner exits SEALED_MIST on occupancy first). Delete + add comment explaining absence.
- **P4#19 — Consolidate R2-X / FW-X history into `DESIGN.md`.** Sprint-tag inline comments are great mid-sprint, obscure intent for cold readers. One-page DESIGN.md capturing priority tiers, override layers, observability contract; strip sprint tags in favor of `// See DESIGN.md §3.2` references.

### P4 larger refactor _(discretionary, sprint-14)_

- **P4#18 — Split `determine_mode()`.** ~150 lines of dense temporal logic. Extract `evaluate_safety()`, `evaluate_planner()`, `apply_emergency_seal()`, `progress_mist()`. Preserves observable behavior; bolts test hooks onto each sub-function.
- **P4#20 — Sharpen `evaluate_overrides()` counterfactuals.** Upgrade each flag from "condition present" to true counterfactual ("would the final mode differ if this gate wasn't here?"). Reviewer calls current behavior "good diagnostics, not a mathematically exact explanation engine" — fine as-is, optional to sharpen.

## Closed / resolved

- **Phase 0 agronomy-review items** — _sprint-10, 2026-04-19_ — closed: 0.2 THERMAL_RELIEF both fans; 0.4a `dt_ms` clamp; 0.4b three magic numbers into Setpoints; 0.4c vpd_min_safe override for SEALED_MIST (P3#13 absorbed); 0.3 day/night setpoint pairs with hybrid is_photoperiod. P2#9, P2#10, P3#13 all closed. Open from the original Phase 0: 0.1 always-on HAF (hardware question — spare relay vs multi-tap).
- **Multi-reviewer synthesis P0/P1/P3 items** — _sprint-8 + sprint-9, 2026-04-19_ — closed: P0#1/P0#2/P0#3 R2-3 bug trio + midnight wrap; P1#4 R2-3 cycle-breaker bypass documented; P1#5 safety-mode reset symmetry; P1#6 fog_permitted extraction; P1#7 heat-S2 latch; P2#8 validate_setpoints relational asserts; P2#11 SAFETY_HEAT fan; P3#14 "full battery" comment. Bonus fix: vpd_watch_timer_ms reset on safety entry closed the stale-dwell half of P1#4.
- **Midnight-transition investigation** — _sprint-6, 2026-04-19_ — 60-day telemetry analysis found no evidence of edge-case behavior near 00:00 local. State-transition density, null rate, equipment activity, and crash distribution are all normal at midnight; midday (11-14 local) is where anomalies cluster. Counter-reset code paths reviewed and found correct. Full writeup in sprint-6 commit.

## Trigger-dated

- **2026-05-19 — 30-day sprint-2 fairness follow-up audit.** Re-run the 90-day fairness audit query from the sprint-2 commit message (`4471743`). Expect west's on-cycle share to climb from 15% toward 30% of total mister cycles. Prerequisite: `make replay-corpus-refresh` has been run routinely so the corpus extends to that date.

## Gates / reminders

- Replay against 8 months of telemetry (`make test-firmware`) is a **permanent gate** for structural firmware changes.
- `make firmware-check` (ESPHome compile) must pass before commit; `make check` runs the full chain.
- Any new override flag must land in `verdify_schemas/telemetry.OverrideEvent` and `firmware/lib/greenhouse_types.h` (`OverrideFlags` struct) — coordinate with coordinator first.
- Any relay / switch rename touches `entity_map.py` — coordinate with ingestor.
