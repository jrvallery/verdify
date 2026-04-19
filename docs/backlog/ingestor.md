# Backlog: `ingestor`

Owned by the [`ingestor`](../agents/ingestor.md) agent.

## In flight

- [x] **Sprint 23 — Pydantic rollout gaps.** Ingestor write paths, HA state schemas, Open-Meteo validation, plus MCP harvest/treatment bug fix (bundled). Commit `47f8154` on `iris-dev/sprint-23-pydantic-gaps`. Awaiting fast-forward merge into main + live ingestor restart verification.

## Next up (candidates)

- [ ] **Alert monitor: per-alert-type schema discriminated union.** `AlertEnvelope` is currently a single flat shape with `extra="forbid"`. Different alert_type's have meaningfully different `details` shapes — would catch more drift if modeled as a discriminated union. Medium-sized refactor; needs coordinator sign-off on schema split.
- [ ] **Retire `_parse_float`.** Now that `_ha_state` + `HAEntityState.as_float()` handle all new paths, audit for remaining `_parse_float` callers and migrate.
- [ ] **Dispatcher observability.** Tier 1 audit (commit `76fe9b1`) added clamp audit + ESP32 push; next: structured trace for the full plan → dispatch → confirmation loop. Feed into `genai`'s plan evaluation.
- [ ] **Forecast deviation monitor → structured alerts.** Currently embedded in tasks.py, emits alert dicts. Move to the same `AlertEnvelope` pattern as alert_monitor.
- [ ] **Split `tasks.py`.** It's > 2200 lines. Break into `tasks/shelly.py`, `tasks/tempest.py`, `tasks/ha.py`, `tasks/alerts.py`, `tasks/dispatcher.py`. Pure refactor — coordinator approves first.

## Ideas (not yet committed)

- Replace `docker exec verdify-timescaledb` wrappers in the smoke tests with an asyncpg connection (would shave ~15 s off test suite).
- Ingestor self-health endpoint (exposes last write timestamps per table) for `web` agent's status API.

## Recent history

- Sprint 23: Pydantic rollout gaps (in flight).
- Sprint 22: `verdify_schemas.telemetry` + drift guards (schema foundation).
- Sprint 21: Full-stack Pydantic coverage.
- Sprint 20: Unified plan schema + feedback loop.
- Sprint 19: Signal quality + test coverage (A3 milestone).
- Sprint 18: Deterministic dispatch (A2).

## Gates / reminders

- Every new DB write path goes through a `verdify_schemas` model at the boundary.
- Restart-then-tail is the live gate: `sudo systemctl restart verdify-ingestor && sudo journalctl -u verdify-ingestor -f`. Watch 5 min for `ValidationError` / schema errors.
- Drift guards must pass: `pytest verdify_schemas/tests/test_drift_guards.py`.
