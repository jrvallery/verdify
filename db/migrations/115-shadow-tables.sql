-- 115-shadow-tables.sql
-- =============================================================================
-- Phase 6 of the Iris loop overhaul — shadow MCP tables.
--
-- The shadow week (Phase 6) fans planner cycles out to a second Hermes
-- container (hermes-iris-shadow on :8643) that points at mcp/server_shadow.py.
-- Shadow writes go to these tables instead of plan_journal / setpoint_plan,
-- so we can score shadow-Hermes plans against actual sensor data without
-- touching production setpoints.
--
-- Daily diff (scripts/compare-shadow-plans.py) joins shadow + prod rows by
-- trigger_id to produce a side-by-side report: structured-hypothesis rate,
-- tool-discipline violations, parameter-validity, plan-evaluate compliance,
-- anchor_score deltas, per-event elapsed time + cost.
--
-- After the canary cutover completes (Phase 7) and OpenClaw is retired
-- (Phase 8), these shadow tables stay around as the replay/regression
-- harness for any future model swap.
-- =============================================================================

BEGIN;

-- ── plan_journal_shadow: same shape as plan_journal, side-channel writes ──
CREATE TABLE IF NOT EXISTS plan_journal_shadow (
    plan_id               TEXT NOT NULL,
    created_at            TIMESTAMPTZ DEFAULT now(),
    conditions_summary    TEXT,
    hypothesis            TEXT,
    experiment            TEXT,
    expected_outcome      TEXT,
    params_changed        TEXT[],
    actual_outcome        TEXT,
    outcome_score         SMALLINT
                          CHECK (outcome_score IS NULL OR (outcome_score BETWEEN 1 AND 10)),
    anchor_score          SMALLINT,
    lesson_extracted      TEXT,
    validated_at          TIMESTAMPTZ,
    greenhouse_id         TEXT DEFAULT 'vallery',
    hypothesis_structured JSONB,
    planner_instance      TEXT,
    trigger_id            UUID,
    -- Shadow-specific: which prod plan_id (if any) this shadow row corresponds
    -- to. NULL for shadow plans that have no matched prod equivalent (e.g. if
    -- the prod side rejected the plan).
    matched_prod_plan_id  TEXT,
    PRIMARY KEY (plan_id)
);

CREATE INDEX IF NOT EXISTS idx_plan_journal_shadow_created ON plan_journal_shadow (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_plan_journal_shadow_trigger ON plan_journal_shadow (trigger_id);
CREATE INDEX IF NOT EXISTS idx_plan_journal_shadow_matched ON plan_journal_shadow (matched_prod_plan_id);

COMMENT ON TABLE plan_journal_shadow IS
  'Shadow plan_journal — shadow-Hermes (Phase 6) writes plan rows here '
  'instead of the production plan_journal so we can score shadow plans '
  'against the same telemetry without touching prod setpoints.';

-- ── setpoint_plan_shadow: same shape as setpoint_plan ──
-- Note: NOT a hypertable. The shadow corpus is bounded to the shadow week
-- volume (~50-100 cycles); we don't need TimescaleDB partitioning here.
CREATE TABLE IF NOT EXISTS setpoint_plan_shadow (
    ts        TIMESTAMPTZ NOT NULL,
    parameter TEXT NOT NULL,
    value     DOUBLE PRECISION,
    plan_id   TEXT NOT NULL,
    reason    TEXT,
    inserted_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ts, parameter, plan_id)
);

CREATE INDEX IF NOT EXISTS idx_setpoint_plan_shadow_plan ON setpoint_plan_shadow (plan_id);
CREATE INDEX IF NOT EXISTS idx_setpoint_plan_shadow_ts ON setpoint_plan_shadow (ts);

COMMENT ON TABLE setpoint_plan_shadow IS
  'Shadow setpoint_plan — shadow-Hermes waypoints, never dispatched to '
  'ESP32. Compared to prod setpoint_plan by scripts/compare-shadow-plans.py '
  'for parameter-validity + plan-shape regression checks.';

-- ── plan_delivery_log_shadow: minimal record of shadow gateway calls ──
CREATE TABLE IF NOT EXISTS plan_delivery_log_shadow (
    id              BIGSERIAL PRIMARY KEY,
    delivered_at    TIMESTAMPTZ DEFAULT now(),
    event_type      TEXT NOT NULL,
    event_label     TEXT,
    session_key     TEXT,
    gateway_status  INTEGER,
    gateway_body    TEXT,
    trigger_id      UUID,
    instance        TEXT,
    hermes_run_id   TEXT,
    matched_prod_delivery_log_id INTEGER
);

CREATE INDEX IF NOT EXISTS idx_plan_delivery_log_shadow_trigger ON plan_delivery_log_shadow (trigger_id);
CREATE INDEX IF NOT EXISTS idx_plan_delivery_log_shadow_event ON plan_delivery_log_shadow (event_type, delivered_at DESC);

COMMENT ON TABLE plan_delivery_log_shadow IS
  'Shadow plan_delivery_log — every shadow-Hermes /v1/runs call records '
  'here with the same trigger_id as the prod delivery, so diff scripts '
  'can pair them up.';

COMMIT;
