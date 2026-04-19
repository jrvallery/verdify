# Backlog: `ingestor`

Owned by the [`ingestor`](../agents/ingestor.md) agent.

Full delivery plan with reasoning, cross-agent branch survey, and risk register lives at `~/.claude-agents/verdify-ingestor/plans/yes-fill-this-out-unified-stearns.md`. This file is the operational queue.

## In flight

Nothing active. Sprint 23 (`47f8154`) shipped to main `2c2572d`. Sprint 24 is ready to start pending Jason's decisions on the open questions below.

## Findings from 2026-04-18 scope review

Seven concrete gaps found by reading every file in scope plus every `verdify_schemas/` model the ingestor touches. One is critical; the rest are addressable over three sprints.

- **F1 — CRITICAL:** `safety_invalid` alerts silently dropped since Sprint 23 shipped. `ingestor/tasks.py:706` uses `"category": "safety"` but `AlertCategory` (`verdify_schemas/alerts.py:17`) only allows `sensor|equipment|climate|water|system`. Post-Sprint-23 validation rejects and logs+skips. Fix in Sprint 24. Blast radius: `safety_min/max/vpd_min/vpd_max` zero-or-invalid detection offline.
- **F2 — HIGH:** Two parallel forecast writers. `scripts/forecast-sync.py` validates via `OpenMeteoForecastResponse` (Sprint 23); `ingestor/tasks.py::forecast_sync` (line 1231) reimplements unvalidated. The validated path has no systemd timer → the live path is the unvalidated one.
- **F3 — HIGH:** `_PHYSICS_INVARIANTS` (`tasks.py:902-933`) has ~half its keys wrong (`fog_window_start` vs canonical `fog_time_window_start`, `fog_min_temp` vs `fog_min_temp_f`, `fog_rh_ceiling` vs `fog_rh_ceiling_pct`, plus `max_relief_cycles`/`vpd_max_safe`/`vpd_min_safe` not in `ALL_TUNABLES`). Dead defense.
- **F4 — MEDIUM:** `ESP32LogRow` exists in `verdify_schemas/system_infra.py` but `ingestor/ingestor.py:472-509` writes `esp32_logs` from raw tuples, bypassing validation.
- **F5 — MEDIUM:** `EquipmentStateEvent.equipment: str` should be `EquipmentId` Literal. The Literal exists (`telemetry.py:160`, 26 values) but is unused. Coordinator handshake required.
- **F6 — MEDIUM:** `ingestor/ingestor.py:337-340` INSERTs ESP32-reported setpoint changes without `source` column. `SetpointSource` Literal includes `"esp32"` for exactly this.
- **F7 — LOW:** `daily_summary` two-writer pattern (midnight snapshot in `ingestor.py:375`, live refresh in `tasks.py:1679`) is implicit. Docstrings should name authoritative columns.

F8 (staleness window in `write_climate`) investigated and dismissed as correct.

## Sprint 24 — Correctness Closure (next up)

**Branch:** `ingestor/sprint-24-correctness`. Target: 1 week, one commit per `feedback_sprint_commit_shape` convention.

- [ ] **S24.1** Fix `safety_invalid` alert category → `"system"` at `ingestor/tasks.py:706` (recommend over widening the enum — cheaper, revisits in Sprint 25 discriminated union anyway)
- [ ] **S24.2** Tag ESP32-reported setpoint changes with `source='esp32'` in `write_setpoint_changes` (`ingestor/ingestor.py:326-340`)
- [ ] **S24.3** Validate `ESP32LogRow` before `esp32_logs` INSERT (`ingestor/ingestor.py:472-509`)
- [ ] **S24.4** Rename `_PHYSICS_INVARIANTS` keys to canonical `ALL_TUNABLES` names; delete dead entries (`ingestor/tasks.py:902-933`). Review `setpoint_clamps` for the last 30 days first — any clamps on the soon-to-be-deleted names may represent real planner bugs being silently masked
- [ ] **S24.5** Consolidate forecast-sync: delete `scripts/forecast-sync.py` + `systemd/verdify-forecast.service`, add `OpenMeteoForecastResponse.model_validate` to `ingestor/tasks.py::forecast_sync` (Option A, §6.4 of the plan)
- [ ] **S24.6** Docstring `daily_summary` authority at both writer sites (`ingestor/ingestor.py:375`, `ingestor/tasks.py:1679`)
- [ ] **S24.7** Add CI test `test_physics_invariants_are_canonical` — `_PHYSICS_INVARIANTS.keys() ⊆ ALL_TUNABLES` — in `verdify_schemas/tests/test_tunables.py`

**Milestone M1:** every ingestor write validates through a schema; zero dead physics invariants; `safety_invalid` alerts fire again.

**Success criteria:** `make lint` + `make test` clean; drift guards + new physics-invariants test pass; 5 min live-tail shows no ValidationError and one successful cycle of every interval class. Post-restart queries confirm `safety_invalid` and `source='esp32'` land in DB.

**Handshakes:** none. All in scope.

## Sprint 25 — Discriminated `AlertEnvelope` + `EquipmentId` tightening

**Branch:** `ingestor/sprint-25-alert-union`. Target: 2 weeks. Blocked by coordinator schema PR.

- [ ] **Schema PR (coordinator, blocking)** Split `AlertEnvelope` into discriminated union keyed by `alert_type`. 13 types today: `sensor_offline`, `relay_stuck`, `vpd_stress`, `temp_safety`, `vpd_extreme`, `leak_detected`, `esp32_reboot`, `planner_stale`, `safety_invalid`, `heat_manual_override`, `soil_sensor_offline`, `heat_staging_inversion`, `setpoint_unconfirmed`. Plus tighten `EquipmentStateEvent.equipment: EquipmentId`.
- [ ] **S25.1** Migrate `alert_monitor` (`tasks.py:495-880`) to per-type typed builders
- [ ] **S25.2** Migrate `setpoint_confirmation_monitor` alert build (`tasks.py:2175-2265`)
- [ ] **S25.3** Migrate `forecast_deviation_check` trigger write (`tasks.py:1524-1662`) into unified `AlertEnvelope` path (supersedes the cross-cutting "deviation → structured alerts" item)
- [ ] **S25.4** Verify `EquipmentStateEvent` callers still pass after `EquipmentId` tightening (`ingestor/ingestor.py:242-263`, `tasks.py:437-470`)

**Milestone M2:** alerts are type-checked at build time. Deviation monitor uses the unified alert path. Equipment typo rejection.

**Success criteria:** every `*Details` subtype has `extra="forbid"`; new `test_alert_envelope_dispatches_by_type` covers every branch; new `test_equipment_state_rejects_unknown` confirms typo rejection; `alert_log` new-row rate within ±10% of 30-day baseline.

**Handshakes:**
- Coordinator: schema PR first
- Genai: MCP `alerts` tool `AlertAction` envelope (`verdify_schemas/alerts.py:83`) unchanged
- Firmware: `EquipmentId` literal covers every firmware-emitted equipment name in `firmware/greenhouse.yaml`

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

## Open decisions (block Sprint 24 kickoff)

1. **F1 fix shape:** recommend `"system"` (cheap, in-scope). Widening `AlertCategory` to include `"safety"` waits for Sprint 25 discriminated union.
2. **Branch B1 (`iris-dev/sprint-22-pydantic-rollout`):** 2 unmerged commits on "topology as first-class entities" — appears abandoned alternate Sprint 23. Recommend archiving as `archive/topology-sprint-23-draft`. Blocks nothing in Sprint 24 but avoids confusion.
3. **Branch B2 (`backend-dev`):** 491-file experimental FastAPI/SQLModel rewrite with Copilot scaffolding. Recommend archiving as `archive/backend-dev-experiment`.
4. **F2 consolidation direction:** Option A (delete script, validate inline) recommended over Option B (script-as-library).
5. **Sprint 26 ordering:** recommend AFTER Sprint 25. Bundling split with alert migration would be a 1000+ line diff; doing 25 on the monolith keeps each sprint reviewable.

## Candidate / Sprint 28+ (not yet committed)

- Replace `docker exec verdify-timescaledb` wrappers in smoke tests with asyncpg (cross-cutting item; ~15s off test suite)
- Dispatcher self-health heartbeat — emit one row every 5 min proving loop is alive
- Migrate hardcoded mister/safety dispatcher defaults (`tasks.py:1054-1083`) into a DB-backed `ingestor_defaults` table — tunable without redeploy

## Recent history

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
