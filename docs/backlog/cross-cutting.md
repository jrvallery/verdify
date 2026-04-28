# Backlog: cross-cutting

Coordinator-owned queue. Items that span 2+ agent scopes, touch shared territory, or are high-stakes enough to warrant single-driver execution.

## Schemas / contracts

- [ ] **Per-alert-type discriminated union for `AlertEnvelope`.** Requested by `ingestor`. Split the single flat shape into a discriminated union keyed by `alert_type` so each alert's `details` gets a dedicated model.
- [ ] **Migrate `verdify_schemas.crops.ObservationAction.data` union to also accept `HarvestCreate` / `TreatmentCreate`.** (Already done in Sprint 23; verify after merge.)
- [x] **Scorecard typed projection** (requested by `genai` + `web`). `ScorecardResponse` is the shared typed shape; migration 096 and `db/schema.sql` now match the live 25-metric numeric `fn_planner_scorecard()`, and `/api/v1/scorecard` returns that schema.

## Migrations

- [ ] Audit all `greenhouse_id` defaults — some tables have the column, some don't; `harvests` + `treatments` notably missing. SaaS-track requires every table to have it.
- [ ] Consolidate `v_daily_oscillation` + `v_daily_oscillation_summary` — one wraps the other; renderer confusion on which to use.

## Infra

- [ ] Secret Manager migration (Sprint 10 B10.5 from SaaS backlog) — credentials move from `.env` to Secret Manager refs. Touches every service.
- [ ] Flaky `test_dew_point_risk_computes`. Pre-existing; times out after 15 s on the `docker exec` path. Either increase timeout in `conftest.py` or switch the test to asyncpg.
- [x] Grafana dashboard audit. 55 live dashboards / 904 panels were swept on 2026-04-28; JSON changes are committed with the web/runtime reconciliation.

## CI / tooling

- [ ] Sprint 22 added drift guards in CI with a Postgres service container. Extend to run smoke tests (`tests/`) in the same job — currently only schema tests run in CI.
- [ ] `ruff format` in pre-commit reformats files Claude agents just wrote, occasionally creating a 2-round edit cycle. Pre-commit should run ruff with the project config, not defaults.

## Docs

- [ ] `docs/FOLDER-HIERARCHY.md` predates the agent split; refresh to reflect agent ownership.
- [ ] `docs/SYSTEM-ARCHITECTURE.md` — same; add agent boundaries overlaid on the component diagram.
- [ ] Move `docs/RUNBOOK.md` operational procedures into per-agent scope docs where they fit, and leave the runbook as cross-cutting incident response only.

## Observability

Currently handled as ephemeral coordinator-dispatched work (see `CLAUDE.md` open question 2). If this queue grows past ~5 items, revisit whether a persistent `observability` agent is warranted.

## Open design questions (flagged earlier)

1. Worktree migration path — rename `slot-*` to `worktrees/{agent}/` now vs. lazily per first sprint.
2. Replay corpus ownership — firmware owns tests, ingestor exports telemetry fixture. How frozen is the fixture?
3. Branch-prefix enforcement — convention + review vs. pre-commit hook that refuses out-of-scope edits.

Coordinator decides these before the first parallel cycle starts.
