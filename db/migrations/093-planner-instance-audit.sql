-- Migration 093: dual-Iris schema extension (iris-planner-contract v1.4)
--
-- Extends plan_delivery_log (migration 092 / sprint 24.6) with contract-
-- required audit columns so:
--   (a) every trigger can be correlated end-to-end via trigger_id
--   (b) opus/local plan attribution can be queried
--   (c) SLA-based alert_monitor rule 7 over `status` becomes possible
-- Also adds planner_instance + trigger_id to plan_journal + setpoint_changes
-- so every MCP write (set_plan / set_tunable) stamps its originating peer.
--
-- Online-safe: all ALTERs are nullable-text or UUID; no row rewrite.
-- Backfill UPDATEs are set-based and indexed.
--
-- Contract: docs/iris-planner-contract.md §2.D (landed 2026-04-19 @ c88490a).
-- Prereq:   migration 092 (plan_delivery_log from sprint 24.6) already applied.
-- Consumers:
--   * genai sprint-3 Sub-scope B — MCP server reads X-Planner-Instance /
--     X-Trigger-Id headers; new acknowledge_trigger tool writes acked_at +
--     status='acked'; set_plan / set_tunable stamp instance + trigger_id.
--   * ingestor sprint-25 — planning_heartbeat populates new columns on the
--     existing INSERT path; alert_monitor rule 7 joins plan_journal ↔
--     plan_delivery_log on trigger_id; SLA breaches flip status='timed_out'.

BEGIN;

-- ───────────────────────────────────────────────────────────────
-- plan_delivery_log — extended audit shape (§2.D)
-- ───────────────────────────────────────────────────────────────
ALTER TABLE plan_delivery_log ADD COLUMN IF NOT EXISTS trigger_id UUID UNIQUE;
ALTER TABLE plan_delivery_log ADD COLUMN IF NOT EXISTS instance   TEXT;
ALTER TABLE plan_delivery_log ADD COLUMN IF NOT EXISTS acked_at   TIMESTAMPTZ;
ALTER TABLE plan_delivery_log ADD COLUMN IF NOT EXISTS status     TEXT DEFAULT 'pending';

-- Status domain constraint (drop-and-recreate is idempotent-safe)
ALTER TABLE plan_delivery_log DROP CONSTRAINT IF EXISTS plan_delivery_log_status_check;
ALTER TABLE plan_delivery_log ADD CONSTRAINT plan_delivery_log_status_check
    CHECK (status IN ('pending','acked','plan_written','timed_out','delivery_failed'));

CREATE INDEX IF NOT EXISTS plan_delivery_log_trigger_id_idx
    ON plan_delivery_log (trigger_id);
CREATE INDEX IF NOT EXISTS plan_delivery_log_status_idx
    ON plan_delivery_log (status, delivered_at);

-- Backfill existing rows with derived status + 'iris-planner' instance label
UPDATE plan_delivery_log SET
    instance = 'iris-planner',
    status = CASE
        WHEN resulting_plan_id IS NOT NULL                          THEN 'plan_written'
        WHEN gateway_status IS NOT NULL
             AND gateway_status NOT BETWEEN 200 AND 299             THEN 'delivery_failed'
        WHEN delivered_at < now() - interval '2 hours'              THEN 'timed_out'
        ELSE 'pending'
    END
WHERE instance IS NULL;

-- ───────────────────────────────────────────────────────────────
-- plan_journal + setpoint_changes — instance/trigger stamping (§2.D)
-- ───────────────────────────────────────────────────────────────
ALTER TABLE plan_journal       ADD COLUMN IF NOT EXISTS planner_instance TEXT;
ALTER TABLE plan_journal       ADD COLUMN IF NOT EXISTS trigger_id       UUID;
ALTER TABLE setpoint_changes   ADD COLUMN IF NOT EXISTS planner_instance TEXT;
ALTER TABLE setpoint_changes   ADD COLUMN IF NOT EXISTS trigger_id       UUID;

CREATE INDEX IF NOT EXISTS idx_plan_journal_trigger_id ON plan_journal (trigger_id);
CREATE INDEX IF NOT EXISTS idx_plan_journal_instance   ON plan_journal (planner_instance);

UPDATE plan_journal     SET planner_instance = 'iris-planner' WHERE planner_instance IS NULL;
UPDATE setpoint_changes SET planner_instance = 'iris-planner' WHERE planner_instance IS NULL AND source = 'iris';

COMMIT;

-- ───────────────────────────────────────────────────────────────
-- Column documentation (post-COMMIT so CREATE-VIEW dependencies see them)
-- ───────────────────────────────────────────────────────────────
COMMENT ON COLUMN plan_delivery_log.trigger_id IS
    'UUID correlation key (contract v1.4 §2.D). Populated by ingestor on send_to_iris; '
    'stamped by MCP server onto plan_journal.trigger_id + setpoint_changes.trigger_id '
    'when headers flow through from OpenClaw /hooks/agent. NULL for pre-v1.4 rows.';
COMMENT ON COLUMN plan_delivery_log.instance IS
    'Planner instance handling the trigger: opus | local. Backfilled to iris-planner '
    'for pre-v1.4 rows. Disambiguates cloud Opus vs local vLLM gemma peers.';
COMMENT ON COLUMN plan_delivery_log.status IS
    'Lifecycle: pending (trigger in flight) -> plan_written (resulting_plan_id set), '
    'acked (via MCP acknowledge_trigger), timed_out (SLA breached), delivery_failed '
    '(gateway non-2xx). Drives alert_monitor rule 7 over per-pair SLA tables.';
COMMENT ON COLUMN plan_delivery_log.acked_at IS
    'Set by MCP acknowledge_trigger(trigger_id, reason) when Iris correctly defers a '
    'cycle without writing a plan. Distinguishes "read + no-change-needed" from '
    '"silently dropped"; the exact ambiguity that caused the 2026-04-19 false-stale.';
COMMENT ON COLUMN plan_journal.planner_instance IS
    'Which Iris peer authored this plan. Stamped by MCP set_plan from X-Planner-Instance '
    'header forwarded through OpenClaw. NULL rows are pre-v1.4.';
COMMENT ON COLUMN plan_journal.trigger_id IS
    'Correlation key back to plan_delivery_log.trigger_id. Enables "which trigger '
    'produced this plan?" lookups in one join.';
