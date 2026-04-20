# Backlog: `ingestor`

Owned by the [`ingestor`](../agents/ingestor.md) agent.

Full delivery plan with reasoning, cross-agent branch survey, and risk register lives at `~/.claude-agents/verdify-ingestor/plans/yes-fill-this-out-unified-stearns.md`. This file is the operational queue.

## In flight

Nothing. Sprint 24 + hotfix + alignment all shipped and live-gate-green as of 2026-04-19 12:54. Deploy path: `main → /mnt/iris/verdify → systemd restart`. See "Recent history" for commit chain.

## Findings from 2026-04-18 scope review

Seven concrete gaps from the initial scope review; one (F9) surfaced when topology commits landed mid-review; four more (F10–F13) surfaced during or after the live gates.

- **F1 — CRITICAL:** `safety_invalid` alerts silently dropped since Sprint 23. `ingestor/tasks.py::alert_monitor` built `"category": "safety"` but `AlertCategory` only allows `sensor|equipment|climate|water|system`; post-Sprint-23 `AlertEnvelope.model_validate` rejected and logged+skipped. Blast radius: `safety_min/max/vpd_min/vpd_max` zero-or-invalid detection was offline. ✅ Sprint 24 (`a9d2147`) — changed to `"system"`.
- **F2 — HIGH:** Two parallel forecast writers; `scripts/forecast-sync.py` validated via `OpenMeteoForecastResponse` (Sprint 23) but `ingestor/tasks.py::forecast_sync` reimplemented the fetch unvalidated and was the live path (no systemd timer on the script). ✅ Sprint 24 — consolidated via Option A (script + systemd unit deleted, validated fetch inlined).
- **F3 — HIGH:** `_PHYSICS_INVARIANTS` drifted from canonical `ALL_TUNABLES` names (`fog_window_start` vs `fog_time_window_start`, etc.) — half the keys were dead defense. Pre-flight: 30-day `setpoint_clamps` audit = 0 rows on all renamed params (no planner bugs masked). ✅ Sprint 24 — renamed canonical, deleted non-tunable entries, added CI guard `test_physics_invariants_are_canonical`.
- **F4 — MEDIUM:** `write_esp32_logs` bypassed `ESP32LogRow` validation. ✅ Sprint 24 — validates before INSERT; drops empty-after-ANSI-strip rows.
- **F5 — MEDIUM:** `EquipmentStateEvent.equipment: str` should be `EquipmentId` Literal. ✅ **Already done upstream** by topology Sprint 22 (`a172576` on main) — `verdify_schemas/telemetry.py:201` is tight. Discovered mid-sprint when topology commits merged between session start and first edit.
- **F6 — MEDIUM:** `write_setpoint_changes` INSERT omitted the `source` column for ESP32-reported changes. ✅ Sprint 24 — tags `source='esp32'`.
- **F7 — LOW:** `daily_summary` two-writer pattern was implicit. ✅ Sprint 24 — both writer functions now carry authoritative-column docstrings.
- **F9 — LOW (new, surfaced by topology):** `alert_log.zone_id` column exists (topology migration 086) and `AlertEnvelope.zone_id: int | None` is wired, but `ingestor/tasks.py::alert_monitor` never populates it — every built alert has `"zone": None` and implicitly `zone_id=None`. No data-loss risk (column is nullable), but an opportunity for richer alert routing once the topology tables are populated. Sprint 27+ candidate.
- **F10 — MEDIUM (surfaced by firmware's live-controller report):** `mister_state` + `mister_selected_zone` emitted as numeric template sensors (state_class=measurement), not text — `on_state_change` sensor branch had no STATE_MAP check so both routes went stale 27+ days. ✅ Sprint 24-alignment (`3b1d93a`) — added `_MISTER_STATE_NAMES` + `_MISTER_ZONE_NAMES` decoder tables, new branch in sensor path decodes codes (0=WATCH, 1=S1, 2=S2, 3=FOG; 0=none, 1=south, 2=west, 3=center) → routes to `system_state`. Live gate exercised WATCH/S1/S2 + none/south/west/center.
- **F11 — MEDIUM (firmware sprint-2 gap):** `mister_fairness_overrides_today` firmware sensor had no DB home → 7-day watchdog validation would require journalctl scraping. ✅ Sprint 24-alignment — migration `091-fairness-counter.sql` adds `daily_summary.mister_fairness_overrides_today`, schema + entity_map + `write_daily_summary` INSERT all wired. First midnight snapshot ~00:05 Apr 20 will land today's count.
- **F12 — LOW (documented, not fixed):** `v_stress_hours_today` uses `2.0/60.0` per-row coefficient assuming 30s climate cadence; actual cadence is 60s → 2x over-reporting. Fix is one-character view update but planner scorecard is calibrated to current values; coordinated flip required. Logged for cross-cutting backlog (needs coordinator + genai handshake).
- **F13 — LOW (surfaced by Sprint 24-alignment live gate):** `setpoint_confirmation_monitor` has no mechanism to age out "pre-readback-era" unconfirmed rows — old `setpoint_changes` pushed before firmware's cfg sensors existed never confirm and periodically re-fire alerts (observed: 1 stale critical for `vpd_target_south=1.530` from 18:04:33 UTC, before firmware sprint-3). Fix: age out unconfirmed rows >N hours old OR supersede: when newer same-param row confirms, backdate older. Sprint 27 candidate.

F8 (staleness window in `write_climate`) investigated and dismissed as correct.

## Sprint 24 — Correctness Closure (shipped `a9d2147`, live-gate PASSED 2026-04-19)

Closed F1/F2/F3/F4/F6/F7. Hotfix `4a89844` closed surface bugs in topology's `EquipmentId` literal + `fallback_window_s` + a test regression I missed; alignment `3b1d93a` closed F10 + F11 + firmware-drift allowlist.

- [x] **S24.1** `safety_invalid` alert category → `"system"`
- [x] **S24.2** ESP32-reported setpoint changes tagged `source='esp32'`
- [x] **S24.3** `ESP32LogRow` validation in `write_esp32_logs`
- [x] **S24.4** `_PHYSICS_INVARIANTS` renamed to canonical; dead entries removed
- [x] **S24.5** `scripts/forecast-sync.py` + `systemd/verdify-forecast.service` deleted; `OpenMeteoForecastResponse` validation inlined
- [x] **S24.6** Two-writer `daily_summary` authority docstrings
- [x] **S24.7** CI test `test_physics_invariants_are_canonical`
- [x] **Hotfix (F5-reopen):** `EquipmentId` widened from 26 → 42 names (topology's tightening was under-complete)
- [x] **Hotfix (readback):** `fallback_window_s` added to `NUMERIC_TUNABLES`; `test_tunable_set_matches_entity_map` relaxed to accept CFG_READBACK_MAP-only tunables
- [x] **Alignment F10:** numeric `mister_state` + `mister_selected_zone` → decoded `system_state` rows (live-verified WATCH/S1/S2 + none/south/west/center)
- [x] **Alignment F11:** migration 091 + schema + entity_map + INSERT for `mister_fairness_overrides_today`
- [x] **Alignment maintenance:** applied coordinator's unapplied migration 090; added dehum entries to DAILY_ACCUM_MAP drift allowlist

**Milestones achieved:** M1 (every write validates; zero dead invariants; safety_invalid fires). Live gate: zero errors for 5 min × 2 runs (hotfix + alignment).

**Deploy verified:** `main @ b25c09e` live on `verdify-ingestor.service` since 2026-04-19 12:48:41; 154+ log lines in watch window, 0 ERROR/WARNING.

## Sprint 25 — Discriminated `AlertEnvelope`

**Branch:** `ingestor/sprint-25-alert-union`. Target: 2 weeks. Blocked by coordinator schema PR.

**Schema PR spec:** [`docs/proposals/sprint-25-alert-envelope-union.md`](../proposals/sprint-25-alert-envelope-union.md) — full technical spec covering all 15 alert types with typed `*Details` models, drift guards, rollout sequence. Ready for coordinator execution.

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

## Candidate / Sprint 27+ (not yet committed)

- **F9 follow-up — alert `zone_id` population.** `alert_log.zone_id` (topology migration 086) is NULL on every ingestor-emitted alert today. Once topology tables are populated downstream, `alert_monitor` can resolve sensor/equipment → zone and tag alerts. Touches `tasks.py::alert_monitor` + lightweight `zone_of(sensor_id)` helper. Low priority until web/genai consume `zone_id`.
- **F12 — `v_stress_hours_today` coefficient fix.** One-char view change (`2.0/60.0` → `1.0/60.0`). Needs coordinator + genai handshake because planner scorecard is calibrated to the current 2x-reporting values.
- **F13 — age out or supersede stale `setpoint_unconfirmed` alerts.** When a newer same-param `setpoint_changes` row confirms, either backdate older rows' `confirmed_at` or filter them from `setpoint_confirmation_monitor`'s candidate set so pre-readback-era rows stop re-firing alerts.
- Replace `docker exec verdify-timescaledb` wrappers in smoke tests with asyncpg (cross-cutting item; ~15s off test suite).
- Dispatcher self-health heartbeat — emit one row every 5 min proving loop is alive.
- Migrate hardcoded mister/safety dispatcher defaults (`tasks.py:1054-1083`) into a DB-backed `ingestor_defaults` table — tunable without redeploy.

## Recent history

- **Sprint 24-alignment** (merged `3b1d93a`, 2026-04-19 12:54 live-gate PASSED): firmware sprint-2 fairness counter wire-up (migration 091 + schema + entity_map), F10 decoded-state routing, DAILY_ACCUM_MAP drift allowlist. Also applied coordinator's unapplied migration 090 as part of the deploy.
- **Sprint 24-hotfix** (merged `4a89844`, 2026-04-19 12:30 live-gate PASSED): post-deploy findings — `EquipmentId` literal widened 26→42 to cover all ingestor-emitted names (topology's tightening was under-complete), `fallback_window_s` added to NUMERIC_TUNABLES + test_tunables relaxed to accept readback-only tunables, `test_fw3_invariants_table_defined` updated for Sprint 24 rename.
- **Sprint 24** (merged `a9d2147`, 2026-04-19): Correctness closure — F1/F2/F3/F4/F6/F7 fixes + CI guard.
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
