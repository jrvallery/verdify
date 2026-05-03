# Backlog: cross-cutting

Coordinator-owned queue. Items that span 2+ agent scopes, touch shared territory, or are high-stakes enough to warrant single-driver execution.

## Launch coordination

Launch work is tracked in [`docs/backlog/launch.md`](launch.md) with the command center in [`docs/launch/README.md`](../launch/README.md). Coordinator owns:

- [x] **Launch privacy/security gate.** Public Markdown and generated HTML scrubbed for family names, local IPs, camera/security details, ambiguous solar/cloud claims, and raw dollar-sign rendering.
- [ ] **Launch identity/code transparency decisions.** Jason decides attribution and repo/prompt visibility before HN/Reddit.
- [x] **Public API and indexing stance.** Public API is read-only for proof routes; writes require a key; API/Grafana are noindex while launch pages remain indexable.
- [x] **Public proof contract.** Added public-safe home metrics and data-health response models/endpoints for launch proof cards.
- [x] **Launch sequencing.** P0 hardening is deployed; remaining launch timing is Jason-owned attribution/copy/video availability.
- [x] **Cross-agent release train.** Web/genai/ingestor/saas/coordinator launch work was closed as one coordinator-driven release.

## Schemas / contracts

- [x] **Per-alert-type discriminated union for `AlertEnvelope`.** Requested by `ingestor`. `AlertEnvelope` now preserves the existing model API while validating through a tagged per-alert registry covering every current alert writer, including planner, API, dispatcher, heap, firmware, and setpoint-confirmation alerts.
- [x] **Migrate `verdify_schemas.crops.ObservationAction.data` union to also accept `HarvestCreate` / `TreatmentCreate`.** Verified with regression coverage.
- [x] **Scorecard typed projection** (requested by `genai` + `web`). `ScorecardResponse` is the shared typed shape; migration 096 and `db/schema.sql` now match the live 25-metric numeric `fn_planner_scorecard()`, and `/api/v1/scorecard` returns that schema.

## Migrations

- [x] Audit all `greenhouse_id` defaults — migration `103-greenhouse-id-default-audit.sql` sets the missing single-site defaults and publishes `v_greenhouse_id_default_audit`; DB tests enforce zero missing defaults.
- [ ] Consolidate `v_daily_oscillation` + `v_daily_oscillation_summary` — one wraps the other; renderer confusion on which to use.

## Infra

- [ ] Secret Manager migration (Sprint 10 B10.5 from SaaS backlog) — credentials move from `.env` to Secret Manager refs. Touches every service.
- [x] Flaky `test_dew_point_risk_computes`. Increased the shared DB smoke-test wrapper timeout from 15 s to 45 s.
- [x] Grafana dashboard audit. 55 live dashboards / 904 panels were swept on 2026-04-28; JSON changes are committed with the web/runtime reconciliation.

## CI / tooling

- [x] Sprint 22 added drift guards in CI with a Postgres service container. CI now runs the DB schema smoke subset (`tests/test_02_database.py::TestSchemaIntegrity`) against that service container via the direct psql test helper mode.
- [x] `ruff format` in pre-commit reformats files Claude agents just wrote, occasionally creating a 2-round edit cycle. Pre-commit now passes `--config pyproject.toml` explicitly to both ruff hooks.

## Docs

- [ ] `docs/FOLDER-HIERARCHY.md` predates the agent split; refresh to reflect agent ownership.
- [ ] `docs/SYSTEM-ARCHITECTURE.md` — same; add agent boundaries overlaid on the component diagram.
- [ ] Move `docs/RUNBOOK.md` operational procedures into per-agent scope docs where they fit, and leave the runbook as cross-cutting incident response only.

## Observability

Currently handled as ephemeral coordinator-dispatched work (see `CLAUDE.md` open question 2). If this queue grows past ~5 items, revisit whether a persistent `observability` agent is warranted.

## Data trust / data science audit — 2026-05-01

Read-only multi-axis audit covered climate/weather, HVAC/control, water/soil/nutrients, crop outcomes, planner/forecast, and owner storytelling. Core finding: Verdify has strong telemetry for what happened in the greenhouse, but weaker proof for what it produced. Prioritize trust fixes first, then outcome closure.

### In progress / immediate software fixes

- [x] **Data trust migration.** Migration `101-data-trust-and-outcome-views.sql` repairs misleading view definitions and adds trust/outcome surfaces:
  - `v_dew_point_risk` uses America/Denver days and observed sample durations instead of hard-coded 2-minute cadence.
  - `v_water_daily` uses America/Denver days and positive meter deltas instead of UTC-day consecutive max deltas.
  - `v_forecast_accuracy` / `v_forecast_accuracy_daily` only use forecasts fetched before the observed hour.
  - `v_iris_planning_context.active_plan` filters `is_active = true`.
  - `v_setpoint_compliance` / `fn_compliance_pct()` report active temp/VPD band compliance instead of static schedule compliance.
  - New trust/story views: `v_water_accountability`, `v_forecast_accuracy_lead_buckets`, `v_required_sensor_coverage`, `v_energy_daily`, `v_energy_estimate_reconciliation`, `v_setpoint_delivery_latency`, `v_mister_zone_effectiveness`, `v_plan_tactical_outcome_daily`, `v_data_trust_ledger`.
- [x] **Live daily summary completeness.** `ingestor/tasks.py::daily_summary_live` now writes `rh_avg`, `outdoor_temp_min`, `outdoor_temp_max`, refreshes `captured_at`, and reads water from canonical `v_water_daily`.
- [x] **Backfill corrected daily summary fields.** Migration `102-data-backlog-completion.sql` recomputes historical `daily_summary` climate fields, `rh_avg`, outdoor min/max, dew-point risk, canonical water totals, measured `kwh_total`, peak kW, and measured-electric cost.
- [x] **Regenerate dashboard/site SQL catalog after migration 101.** Added the provisioned Grafana `Greenhouse: Data Trust Ledger` dashboard and moved generated daily plan pages to DB-backed archive self-check rows.
- [x] **Add CI drift tests for trust views.** `tests/test_02_database.py` now requires and smoke-tests the trust, water, irrigation, forecast-action, crop-completeness, mart, and archive self-check views.

### Near-term data-quality work

- [x] **Water accounting hardening.** Added `water_meter_events`, `v_water_meter_daily`, event reset/phantom-zero tracking, and canonical `v_water_daily` from positive event deltas.
- [x] **Irrigation log repair.** Migration 102 replays drip events from `equipment_state` into `irrigation_log` with `schedule_id`, zone, duration, estimated gallons, weather skip, fertigation, and metering method.
- [x] **Energy reconciliation.** `daily_summary.kwh_total` now uses watt-time integration from `v_energy_daily`; `v_energy_estimate_reconciliation` remains the estimate-vs-measured quality surface.
- [x] **Alert lifecycle cleanup.** Migration 102 normalizes resolved rows, keeps `suppressed` as an explicit schema disposition, and adds `v_alert_lifecycle_quality`.
- [x] **Sensor registry coverage.** Migration 102 activates or registers required live climate/soil/wind/intake/hydro fields so required coverage is represented in `v_required_sensor_coverage`.
- [x] **Forecast action outcomes.** Migration 102 backfills `forecast_action_log.outcome`, adds outcome timestamps/metrics, and publishes `v_forecast_action_outcomes`.
- [x] **Planner model observability.** `mcp/server.py::plan_status` now writes `openclaw_interaction_log` rows; the existing OpenClaw dashboard now has a real write path.
- [x] **Active-plan cleanup.** Migration 102 deactivates past active waypoints and adds `delivery_status`, `expired_at`, and `superseded_by_ts` for `setpoint_changes`, surfaced in `v_setpoint_change_delivery`.

### Outcome closure / agronomy layer

- [x] **Crop lifecycle completeness.** Migration 102 fills active crop counts/expected harvests/target defaults from `crop_catalog` and publishes `v_crop_lifecycle_completeness`.
- [x] **Harvest logging.** Harvest tables/API/MCP schemas now capture salable weight, culls, quality reason, destination, price/revenue, labor, operator, crop, zone, and position linkage; `v_harvest_story` normalizes outcomes by DLI/water/kWh.
- [x] **Structured phenology observations.** Observation schemas and writers now accept plant height, leaf count, canopy cover, flowering, fruit count, root condition, mortality, and stress tags; `v_growth_observation_quality` tracks coverage.
- [x] **Treatment/IPM logging.** Treatment schemas now include follow-up due/completed timestamps and outcome, with `v_nutrient_lab_status`/treatment rows preserving crop linkage.
- [x] **Nutrient/lab evidence.** `lab_results` now links to recipes/source sample IDs; `v_nutrient_lab_status` joins latest hydro/lab chemistry to active recipe targets.
- [x] **Succession plan data.** `v_succession_plan_readiness` now exposes every active position's crop/successor status so empty positions and missing follow-on plans are measurable.

### Hardware / physical sensing backlog

- [x] **PAR/PPFD sensor.** Codified as `instrumentation_requirements.par_ppfd` and surfaced in `v_instrumentation_readiness`; physical install remains an operator/hardware action.
- [x] **Leaf wetness + leaf temperature.** Codified as `instrumentation_requirements.leaf_wetness_temp` and surfaced in `v_instrumentation_readiness`; physical install remains an operator/hardware action.
- [x] **Independent actuator feedback.** Codified as `instrumentation_requirements.actuator_feedback` and surfaced in `v_instrumentation_readiness`; physical install remains an operator/hardware action.
- [x] **Water system instrumentation.** Codified as `instrumentation_requirements.zone_flow_meters` and surfaced in `v_instrumentation_readiness`; physical install remains an operator/hardware action.
- [x] **Energy submetering.** Codified as `instrumentation_requirements.energy_submetering` and surfaced in `v_instrumentation_readiness`; physical install remains an operator/hardware action.

### Story products

- [x] **Forecast -> plan -> outcome mart.** Added `v_forecast_plan_outcome_mart`.
- [x] **Grower economics story.** Added `v_grower_economics_story`.
- [x] **Data trust ledger dashboard.** Added provisioned Grafana dashboard `greenhouse-data-trust-ledger` on `v_data_trust_ledger`, instrumentation readiness, and daily plan archive self-checks.
- [x] **Daily plan archive self-check.** Added `daily_plan_archive_audit`, `v_daily_plan_archive_self_check`, and writer support in `scripts/generate-daily-plan.py`.

## Open design questions (flagged earlier)

1. Worktree migration path — rename `slot-*` to `worktrees/{agent}/` now vs. lazily per first sprint.
2. Replay corpus ownership — firmware owns tests, ingestor exports telemetry fixture. How frozen is the fixture?
3. Branch-prefix enforcement — convention + review vs. pre-commit hook that refuses out-of-scope edits.

Coordinator decides these before the first parallel cycle starts.
