# Backlog: `firmware`

Owned by the [`firmware`](../agents/firmware.md) agent. Sprint counter is agent-local (resets under the agent-org split — see `CLAUDE.md`).

## In flight

- **`firmware/sprint-2-zone-fairness`** — mister zone-rotation fairness watchdog. 90-day audit showed west stressed 36% of time but firing only 13% of mister cycles (53% of its >5min stress episodes never served). Adds a 10-min last-fire watchdog that overrides the stress-scoring formula when any zone has been stressed without firing. Counter `mister_fairness_overrides_today` exposed for post-deploy validation. See the sprint-2 commit message for full data + mechanism analysis.

## Recently landed

- **`firmware/sprint-1-housekeeping`** — drift fixes + dead-code cleanup + doc sync. No shipped control-logic change.

## Coordination queue (handoffs to other agents)

Findings from the 2026-04-18 audit that live outside firmware scope. Each is a focused handoff PR filed into the owning agent's scope, labeled `requested-by: firmware`:

- [ ] **Coordinator — EquipmentId schema reconciliation.** `verdify_schemas/telemetry.py:160-187` declares 7 IDs firmware never emits (`dehum`, `safety_dehum`, `occupancy`, `door_open`, `gl1`, `gl2`, `grow_light`) and misses ~16 that `ingestor/entity_map.py:94-137` routes to `equipment_state`. Add a drift guard in `verdify_schemas/tests/test_drift_guards.py` that asserts `EquipmentId` ⊇ the set emitted by entity_map.
- [ ] **Coordinator — override flag enum guard.** Add a drift guard that compares `OverrideEvent.override_type` against the 7 flag names in `firmware/lib/greenhouse_types.h` (`OverrideFlags` struct). Today the schema accepts any string; a silent rename would corrupt `override_events`.
- [ ] **Coordinator + genai — `sw_mister_closes_vent` routing.** Firmware handles the key in `controls.yaml`, but it's not in `verdify_schemas/tunables.py` ALL_TUNABLES or `entity_map.py` SETPOINT_MAP. Decide: add to schema or drop the firmware handler.
- [ ] **Ingestor — alert monitor coverage for OBS-3.** `scripts/alert-monitor.py` does not watch `diagnostics.relief_cycle_count > 0` (breaker latched) or `diagnostics.vent_latch_timer_s > 1200` (vent stuck in latched VENTILATE). Add both, plus firmware version staleness vs. an expected pin.
- [ ] **Ingestor — override events smoke test.** Add `test_override_events_written` to `tests/test_05_ingestor.py` to verify `gh_overrides` diff → `override_events` write.
- [ ] **Genai — MCP `set_tunable()` validator.** Today MCP can push any key; if it's not in the firmware handler's accept list, it silently no-ops. Add a pre-push validation.
- [ ] **Saas — real-time setpoint push.** `controls.yaml` references an aioesphomeapi push path that doesn't exist. Either implement or drop the comment.

## Candidates (operational, co-owned with `saas`)

- [ ] **Cloud-fallback setpoints** (was Sprint 10 B10.6) — firmware OTA: add cloud URL as secondary setpoint source.
- [ ] **Direct MQTT to cloud** (was Sprint 10 B10.7) — firmware OTA: publish to `mqtt.verdify.ai` directly.
- [ ] **Cloud-only test window** (was Sprint 10 B10.8) — 24 h test: disable local ingestor, verify ESP32 runs from cloud.

## Ideas (not yet committed)

- Revisit the 7-mode state machine's midnight transition — historical data showed edge-case behavior near 00:00.
- Expand replay corpus to include the last 30 days automatically (complement to the fixed 8-month `replay_overrides.csv.gz`).
- Per-relay cycle-count audit in firmware (complement to ingestor-side counting).
- Mister zone rotation review: does `mister_vpd_weight` starve low-VPD zones under sustained stress?

## Gates / reminders

- Replay against 8 months of telemetry (`make test-firmware`) is a **permanent gate** for structural firmware changes.
- `make firmware-check` (ESPHome compile) must pass before commit; `make check` runs the full chain.
- Any new override flag must land in `verdify_schemas/telemetry.OverrideEvent` and `firmware/lib/greenhouse_types.h` (`OverrideFlags` struct) — coordinate with coordinator first.
- Any relay / switch rename touches `entity_map.py` — coordinate with ingestor.
