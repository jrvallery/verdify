# Backlog: `firmware`

Owned by the [`firmware`](../agents/firmware.md) agent.

## In flight

None.

## Next up (candidates)

- [ ] **Cloud-fallback setpoints** (Sprint 10 B10.6 from legacy SaaS backlog) — firmware OTA: add cloud URL as secondary setpoint source. Coordinate with `saas` agent.
- [ ] **Direct MQTT to cloud** (Sprint 10 B10.7) — firmware OTA: publish to `mqtt.verdify.ai` directly. Coordinate with `saas` agent.
- [ ] **Cloud-only test window** (Sprint 10 B10.8) — 24 h test: disable local ingestor, verify ESP32 runs from cloud. Requires coordinator + `saas` + `ingestor` coordination.

## Ideas (not yet committed)

- Revisit the 7-mode state machine's midnight transition — historical data showed edge-case behavior near 00:00 (see `docs/VPD-PRIMARY-ARCHITECTURE.md`).
- Expand replay corpus to include the last 30 days automatically.
- Add per-relay cycle-count audit in firmware (complement to ingestor-side counting).

## Recent history

- Sprint 17: Sensor fault resilience, per-probe staleness exclusion, OTA auto-rollback, tracked systemd units.
- Sprint 16: OBS-1e — silent override event emission (override_events table).
- Sprint 15: ESP32 reboot resilience, firmware hardening.

## Gates / reminders

- Replay against 8 months of telemetry is a **permanent gate** for structural firmware changes.
- `make firmware-check` must pass before commit.
- Any new override flag must also land in `verdify_schemas.telemetry.OverrideEvent` and firmware `greenhouse_types.h` — coordinate with coordinator.
