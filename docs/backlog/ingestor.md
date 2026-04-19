# Backlog: `ingestor`

Owned by the [`ingestor`](../agents/ingestor.md) agent.

Full delivery plan with reasoning, cross-agent branch survey, and risk register lives at `~/.claude-agents/verdify-ingestor/plans/yes-fill-this-out-unified-stearns.md`. This file is the operational queue.

## In flight

Sprint 24 (`a9d2147`) merged to `ingestor/main`; awaiting deploy + live-restart gate. `main` has diverged by one unrelated commit (`0a6af88` lint sweep) — coordinator will reconcile.

## Findings from 2026-04-18 scope review

Seven concrete gaps from the initial scope review; one additional (F9) surfaced when the topology commits landed on main mid-review.

- **F1 — CRITICAL:** `safety_invalid` alerts silently dropped since Sprint 23. `ingestor/tasks.py::alert_monitor` built `"category": "safety"` but `AlertCategory` only allows `sensor|equipment|climate|water|system`; post-Sprint-23 `AlertEnvelope.model_validate` rejected and logged+skipped. Blast radius: `safety_min/max/vpd_min/vpd_max` zero-or-invalid detection was offline. ✅ Sprint 24 (`a9d2147`) — changed to `"system"`.
- **F2 — HIGH:** Two parallel forecast writers; `scripts/forecast-sync.py` validated via `OpenMeteoForecastResponse` (Sprint 23) but `ingestor/tasks.py::forecast_sync` reimplemented the fetch unvalidated and was the live path (no systemd timer on the script). ✅ Sprint 24 — consolidated via Option A (script + systemd unit deleted, validated fetch inlined).
- **F3 — HIGH:** `_PHYSICS_INVARIANTS` drifted from canonical `ALL_TUNABLES` names (`fog_window_start` vs `fog_time_window_start`, etc.) — half the keys were dead defense. Pre-flight: 30-day `setpoint_clamps` audit = 0 rows on all renamed params (no planner bugs masked). ✅ Sprint 24 — renamed canonical, deleted non-tunable entries, added CI guard `test_physics_invariants_are_canonical`.
- **F4 — MEDIUM:** `write_esp32_logs` bypassed `ESP32LogRow` validation. ✅ Sprint 24 — validates before INSERT; drops empty-after-ANSI-strip rows.
- **F5 — MEDIUM:** `EquipmentStateEvent.equipment: str` should be `EquipmentId` Literal. ✅ **Already done upstream** by topology Sprint 22 (`a172576` on main) — `verdify_schemas/telemetry.py:201` is tight. Discovered mid-sprint when topology commits merged between session start and first edit.
- **F6 — MEDIUM:** `write_setpoint_changes` INSERT omitted the `source` column for ESP32-reported changes. ✅ Sprint 24 — tags `source='esp32'`.
- **F7 — LOW:** `daily_summary` two-writer pattern was implicit. ✅ Sprint 24 — both writer functions now carry authoritative-column docstrings.
- **F9 — LOW (new, surfaced by topology):** `alert_log.zone_id` column exists (topology migration 086) and `AlertEnvelope.zone_id: int | None` is wired, but `ingestor/tasks.py::alert_monitor` never populates it — every built alert has `"zone": None` and implicitly `zone_id=None`. No data-loss risk (column is nullable), but an opportunity for richer alert routing once the topology tables are populated. Sprint 27+ candidate.

F8 (staleness window in `write_climate`) investigated and dismissed as correct.

## Sprint 24 — Correctness Closure (shipped `a9d2147`)

**Branch:** `ingestor/sprint-24-correctness` → merged to `ingestor/main`. Awaiting deploy + live gate.

- [x] **S24.1** `safety_invalid` alert category → `"system"` (`ingestor/tasks.py`)
- [x] **S24.2** ESP32-reported setpoint changes tagged `source='esp32'` (`ingestor/ingestor.py`)
- [x] **S24.3** `ESP32LogRow` validation in `write_esp32_logs`
- [x] **S24.4** `_PHYSICS_INVARIANTS` renamed to canonical; dead entries removed; pre-flight clamp audit = 0 rows
- [x] **S24.5** `scripts/forecast-sync.py` + `systemd/verdify-forecast.service` deleted; `OpenMeteoForecastResponse` validation inlined into `tasks.py::forecast_sync`
- [x] **S24.6** Two-writer `daily_summary` authority docstrings
- [x] **S24.7** CI test `test_physics_invariants_are_canonical` (`verdify_schemas/tests/test_tunables.py`) — worktree-safe sys.path reorder

**Milestone M1 — achieved at commit time:** every ingestor write validates through a schema; zero dead physics invariants; `safety_invalid` alerts build valid envelopes.

**CI gates passed:** `verdify_schemas/tests/` 299/299; `tests/` smoke 137/137; `ruff check` + `ruff format` clean on touched files.

**Remaining gate — live deploy:** `sudo systemctl restart verdify-ingestor && sudo journalctl -u verdify-ingestor -f` for 5 min, then §10 verification queries from the plan file.

## Sprint 25 — Discriminated `AlertEnvelope`

**Branch:** `ingestor/sprint-25-alert-union`. Target: 2 weeks. Blocked by coordinator schema PR.

Scope reduced from the original plan: `EquipmentStateEvent.equipment: EquipmentId` was delivered by topology Sprint 22 upstream. Sprint 25 now covers the alert union only.

- [ ] **Schema PR (coordinator, blocking)** Split `AlertEnvelope` into discriminated union keyed by `alert_type`. 13 types today: `sensor_offline`, `relay_stuck`, `vpd_stress`, `temp_safety`, `vpd_extreme`, `leak_detected`, `esp32_reboot`, `planner_stale`, `safety_invalid`, `heat_manual_override`, `soil_sensor_offline`, `heat_staging_inversion`, `setpoint_unconfirmed`. Each gets a typed `*Details` subtype with `extra="forbid"`.
- [ ] **S25.1** Migrate `alert_monitor` (`tasks.py::alert_monitor`) to per-type typed builders
- [ ] **S25.2** Migrate `setpoint_confirmation_monitor` alert build
- [ ] **S25.3** Migrate `forecast_deviation_check` trigger write into unified `AlertEnvelope` path (supersedes the cross-cutting "deviation → structured alerts" item)

**Milestone M2:** alerts are type-checked at build time. Deviation monitor uses the unified alert path.

**Success criteria:** every `*Details` subtype has `extra="forbid"`; new `test_alert_envelope_dispatches_by_type` covers every branch; `alert_log` new-row rate within ±10% of 30-day baseline; post-deploy Slack chatter unchanged.

**Handshakes:**
- Coordinator: schema PR first
- Genai: MCP `alerts` tool `AlertAction` envelope (`verdify_schemas/alerts.py:83`) unchanged

## Sprint 26 — `tasks.py` Split

**Branch:** `ingestor/sprint-26-tasks-split`. Target: 1 week, pure refactor.

- [ ] **S26.1** Create `ingestor/tasks/` package: `ha.py`, `alerts.py`, `dispatcher.py`, `forecast.py`, `daily.py`, `heartbeat.py`, `confirmation.py`, `water.py`
- [ ] **S26.2** `tasks/__init__.py` re-exports existing names — import surface unchanged
- [ ] **S26.3** Delete `ingestor/tasks.py`
- [ ] **S26.4** Verify `from tasks import X` still works for every caller
- [ ] **S26.5** Update test coverage to import the new modules

**Milestone M3:** every module <500 lines; zero behavior change.

**Success criteria:** `wc -l ingestor/tasks/*.py` max <500; `make lint` + `make test` clean; 10 min live-tail shows every one of 16 tasks fires ≥1×; journalctl output identical modulo module-name prefix.

**Handshakes:** coordinator approves the import-surface change.

## Sprint 27 — Observability Tier 2 + SaaS prep

**Branch:** `ingestor/sprint-27-observability`. Target: 2 weeks.

- [ ] **S27.1** Structured JSON trace for `plan → dispatch → push → snapshot → confirmation` loop. Correlation ID from plan emission through every step. New `dispatcher_trace` hypertable (coordinator migration)
- [ ] **S27.2** Retire `_parse_float` — audit callers, migrate to `HAEntityState.as_float()`
- [ ] **S27.3** `greenhouse_id` write-path audit — every INSERT/UPDATE in ingestor scope includes it; coordinator-side backfill migration for existing NULLs
- [ ] **S27.4** Ingestor self-health endpoint — last-write-ts per hypertable + task loop last-run matrix — for `web` agent's status API (previously an "Ideas" bullet)

**Milestone M4:** every plan waypoint traceable end-to-end by `trace_id`. `greenhouse_id` consistent on every write. Web can render ingestor health without log scraping.

**Success criteria:** `SELECT * FROM dispatcher_trace WHERE trace_id=$1` returns full loop for a single tunable change; `grep _parse_float ingestor/` empty; drift guard covers `dispatcher_trace`; `/health/writes` endpoint returns 200 with per-table timestamps.

**Handshakes:**
- Coordinator: `dispatcher_trace` migration, `greenhouse_id` backfill migration
- Web: consumes `/health/writes`
- Genai: correlation ID propagates through `set_plan`/`set_tunable` MCP tools

## Decisions resolved 2026-04-18

All Sprint 24 blockers cleared and applied.

1. **F1 fix shape:** ✅ Shipped `"category": "system"` in Sprint 24. Semantic tightening deferred to Sprint 25's discriminated union where `safety_invalid` gets its own subtype.
2. ~~**Branch B1 (`iris-dev/sprint-22-pydantic-rollout`):** archive~~. **Superseded:** the two "unmerged" commits landed on `main` with slightly different SHAs (`a172576`, `6766ff9`) between session start and the first edit of this plan. Topology is shipped. The tracking branch can be pruned if it still exists locally; no archival tag needed.
3. **Branch B2 (`backend-dev`):** archive as `archive/backend-dev-experiment`. Still separate; coordinator-owned action.
4. **F2 consolidation:** ✅ Option A shipped — `scripts/forecast-sync.py` and `systemd/verdify-forecast.service` deleted, validation inlined into `tasks.py::forecast_sync`.
5. **Sprint 26 ordering:** AFTER Sprint 25. Alert migration lands on the existing monolith; split is a separate pure-refactor sprint.

## Candidate / Sprint 28+ (not yet committed)

- **F9 follow-up — alert `zone_id` population.** `alert_log.zone_id` (topology migration 086) is NULL on every ingestor-emitted alert today. Once the topology tables are populated, `alert_monitor` can resolve sensor/equipment → zone and tag alerts for topology-aware routing. Touches `tasks.py::alert_monitor` + possibly a lightweight `zone_of(sensor_id)` helper. Low priority until the web/genai agents actually consume `zone_id`.
- Replace `docker exec verdify-timescaledb` wrappers in smoke tests with asyncpg (cross-cutting item; ~15s off test suite)
- Dispatcher self-health heartbeat — emit one row every 5 min proving loop is alive
- Migrate hardcoded mister/safety dispatcher defaults (`tasks.py:1054-1083`) into a DB-backed `ingestor_defaults` table — tunable without redeploy

## Recent history

- **Sprint 24** (merged `a9d2147`, 2026-04-19): Correctness closure — F1/F2/F3/F4/F6/F7 fixes + CI guard. Awaiting live gate.
- **Topology merge** (`a172576` Sprint 22 + `6766ff9` Sprint 23, merged 2026-04-18): not an ingestor sprint, but closed F5 (`EquipmentStateEvent.equipment: EquipmentId`) and added `alert_log.zone_id` upstream (see F9).
- **Sprint 23** (shipped `47f8154`, 2026-04-17): Pydantic rollout — every ingestor write path validates through `verdify_schemas`, HA integrations route through `HAEntityState`, Open-Meteo script validates via `OpenMeteoForecastResponse`, MCP harvest/treatment fix
- **Sprint 22** (`e96f9ba`): `verdify_schemas.telemetry` + drift guards foundation (~15 new schemas, 146 tests, 18 drift guards, vault migration, API `response_model`)
- **Sprint 21**: Full-stack Pydantic coverage (DB ↔ API ↔ MCP ↔ vault ↔ external)
- **Sprint 20**: Unified plan schema + feedback loop + manifestation
- **Sprint 19**: Signal quality + test coverage (Milestone A3) — leak hysteresis, deviation σ-gate, plan-context error routing
- **Sprint 18**: Deterministic dispatch (Milestone A2) — physics invariants, proportional dead-band, clamp audit

## Gates / reminders

- Every new DB write path goes through a `verdify_schemas` model at the boundary.
- Restart-then-tail is the live gate: `sudo systemctl restart verdify-ingestor && sudo journalctl -u verdify-ingestor -f`. Watch 5 min for `ValidationError` / schema errors.
- Drift guards must pass: `pytest verdify_schemas/tests/test_drift_guards.py`.
- Tunable invariant must pass: `pytest verdify_schemas/tests/test_tunables.py` — any new ESP32 entity goes into both `entity_map.py::SETPOINT_MAP` and `verdify_schemas/tunables.py::ALL_TUNABLES` in the same commit.
- Coordinator handshake for anything touching `verdify_schemas/`, `db/migrations/`, `systemd/` (cross-agent units), or `.github/workflows/`.
