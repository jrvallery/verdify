-- 114-plan-delivery-hermes-run-id.sql
-- =============================================================================
-- Phase 5 of the Iris loop overhaul — record the Hermes /v1/runs `run_id` on
-- plan_delivery_log alongside the existing OpenClaw gateway_status / gateway_body.
--
-- When AI_GATEWAY_PROVIDER=hermes the dispatcher writes hermes_run_id so the
-- post-cycle SLA verifier can correlate plan_journal.trigger_id ↔
-- plan_delivery_log.trigger_id ↔ Hermes run.id. Without this column we'd lose
-- the bridge between Hermes-side run telemetry and Verdify's plan history.
--
-- OpenClaw rows keep hermes_run_id NULL. After the Phase 7 canary cutover
-- completes and Phase 8 retires OpenClaw, gateway_status + gateway_body
-- remain meaningful as the HTTP-layer return from Hermes /v1/runs.
-- =============================================================================

BEGIN;

ALTER TABLE plan_delivery_log
  ADD COLUMN IF NOT EXISTS hermes_run_id text;

COMMENT ON COLUMN plan_delivery_log.hermes_run_id IS
  'Hermes /v1/runs run.id when AI_GATEWAY_PROVIDER=hermes (or per-event '
  'override). NULL for OpenClaw deliveries.';

CREATE INDEX IF NOT EXISTS idx_plan_delivery_log_hermes_run
  ON plan_delivery_log (hermes_run_id)
  WHERE hermes_run_id IS NOT NULL;

COMMIT;
