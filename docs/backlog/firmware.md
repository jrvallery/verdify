# Backlog: `firmware`

Owned by the [`firmware`](../agents/firmware.md) agent. Sprint counter is agent-local (resets under the agent-org split — see `CLAUDE.md`).

## In flight

- **`firmware/sprint-7-cycle-audit`** — per-zone cycle counters for misters (south/west/center) + drips (wall/center). 5 new template sensors mirror the existing `cycles_fan1_today` pattern; firmware counts rising edges in `turn_on_zone()` (misters) and irrigation dispatch (drips, including the flush rising edge). Closes the audit-visibility gap where fan/heat/fog/vent had counters but irrigation relays only had runtime.

## Recently landed

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

- Per-relay cycle-count audit in firmware (complement to ingestor-side counting). **Queued for sprint-7**.
- **Midday crash-loop investigation.** 91 unexpected reboots in 60 days (Guru/Panic 51 + Task WDT 38), heavily clustered at local hours 11-13 (33 crashes, peaking at hour 12 with 14). Likely heap/stack pressure during peak mister-state-machine activity when VPD is highest. Separate from the sprint-6 midnight investigation, which ruled out midnight-specific issues.

## Closed / resolved

- **Midnight-transition investigation** — _sprint-6, 2026-04-19_ — 60-day telemetry analysis found no evidence of edge-case behavior near 00:00 local. State-transition density, null rate, equipment activity, and crash distribution are all normal at midnight; midday (11-14 local) is where anomalies cluster. Counter-reset code paths reviewed and found correct. Full writeup in sprint-6 commit.

## Trigger-dated

- **2026-05-19 — 30-day sprint-2 fairness follow-up audit.** Re-run the 90-day fairness audit query from the sprint-2 commit message (`4471743`). Expect west's on-cycle share to climb from 15% toward 30% of total mister cycles. Prerequisite: `make replay-corpus-refresh` has been run routinely so the corpus extends to that date.

## Gates / reminders

- Replay against 8 months of telemetry (`make test-firmware`) is a **permanent gate** for structural firmware changes.
- `make firmware-check` (ESPHome compile) must pass before commit; `make check` runs the full chain.
- Any new override flag must land in `verdify_schemas/telemetry.OverrideEvent` and `firmware/lib/greenhouse_types.h` (`OverrideFlags` struct) — coordinate with coordinator first.
- Any relay / switch rename touches `entity_map.py` — coordinate with ingestor.
