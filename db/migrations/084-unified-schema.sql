-- Migration 084: Unified Plan Schema + Feedback Loop (Sprint 20)
--
-- Two additive, nullable columns that unlock the feedback loop + structured
-- planning. Ship ahead of the code so the old ingestor/MCP tolerates the
-- new columns until they get populated.
--
-- setpoint_changes.confirmed_at (Phase 4 / FW-4):
--   Populated by the ingestor's setpoint_snapshot task when the ESP32
--   cfg_* readback matches the most recent unconfirmed write for that
--   parameter (within the dispatcher's 1% proportional dead-band, same
--   _should_skip tolerance). FB-1 monitor alerts on rows that stay NULL
--   past 5 min.
--
-- plan_journal.hypothesis_structured (Phase 5):
--   JSONB companion to the free-form hypothesis prose, validated by
--   PlanHypothesisStructured (verdify_schemas/plan.py). Lets the daily
--   plan renderer produce structured per-section breakdowns (conditions,
--   stress windows, rationale) instead of just dumping prose.

BEGIN;

ALTER TABLE setpoint_changes
    ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ;

COMMENT ON COLUMN setpoint_changes.confirmed_at IS
    'FW-4 (Sprint 20): set when ingestor setpoint_snapshot sees a matching cfg_* readback from ESP32 within 1% dead-band. NULL = unconfirmed; after 5 min the setpoint_confirmation_monitor task opens a setpoint_unconfirmed alert.';

CREATE INDEX IF NOT EXISTS idx_setpoint_changes_unconfirmed
    ON setpoint_changes (ts DESC)
    WHERE confirmed_at IS NULL;

ALTER TABLE plan_journal
    ADD COLUMN IF NOT EXISTS hypothesis_structured JSONB;

COMMENT ON COLUMN plan_journal.hypothesis_structured IS
    'Sprint 20 Phase 5: validated JSONB companion to the prose hypothesis. Shape: PlanHypothesisStructured — {conditions, stress_windows[], rationale[]}. Populated by the set_plan MCP tool when the planner emits a structured JSON block; NULL for legacy rows.';

CREATE INDEX IF NOT EXISTS idx_plan_journal_structured
    ON plan_journal USING gin (hypothesis_structured);

COMMIT;
