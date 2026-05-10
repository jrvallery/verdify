-- 113-event-taxonomy-update.sql
-- =============================================================================
-- Phase 4 of the Iris loop overhaul — codify the new trigger vocabulary in
-- planner_trigger_ledger.event_type.
--
-- New closed set (emitted by ingestor/tasks.py:_compute_milestones):
--   SUNRISE / SUNSET / SOLAR_MAX / TRANSITION / FORECAST_DEVIATION / MANUAL
--
-- Retired (no longer emitted; constraint allows them in historical rows only):
--   MIDNIGHT (pre-contract-v1.5, mapped to TRANSITION:fixed_midnight which is
--   also retired)
--   FORECAST (the new-fetch poll trigger, replaced by FORECAST_DEVIATION
--   σ-gated triggers + the new FORECAST CALIBRATION context section)
--   DEVIATION (renamed to FORECAST_DEVIATION on the wire; in-flight rows are
--   coerced below)
--
-- Coercion: any historical 'DEVIATION' rows in planner_trigger_ledger are
-- renamed to 'FORECAST_DEVIATION' so the constraint can be tightened. The
-- plan_delivery_log table is left untouched — historical event_types there
-- (DEVIATION, FORECAST) remain readable for back-compat queries.
-- =============================================================================

BEGIN;

-- Coerce any in-flight DEVIATION ledger rows to FORECAST_DEVIATION.
UPDATE planner_trigger_ledger
   SET event_type = 'FORECAST_DEVIATION'
 WHERE event_type = 'DEVIATION';

-- Constrain the allowed event_type vocabulary.
ALTER TABLE planner_trigger_ledger
  DROP CONSTRAINT IF EXISTS planner_trigger_ledger_event_type_check;
ALTER TABLE planner_trigger_ledger
  ADD CONSTRAINT planner_trigger_ledger_event_type_check
  CHECK (event_type = ANY (ARRAY[
    'SUNRISE',
    'SUNSET',
    'SOLAR_MAX',
    'TRANSITION',
    'FORECAST_DEVIATION',
    'MANUAL',
    -- legacy event types kept in the set so old rows remain queryable
    -- without violating the constraint. New writes use the closed set
    -- above; ingestor/tasks.py no longer emits these.
    'MIDNIGHT',
    'FORECAST',
    'DEVIATION',
    'HEARTBEAT'
  ]));

COMMIT;
