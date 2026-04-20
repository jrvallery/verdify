-- Migration 092: plan_delivery_log (Sprint 24.6 — F14 planner observability)
--
-- One row per `iris_planner.send_to_iris` call. Makes the delivery→plan
-- correlation query-able: today I had to scavenge journalctl + plan_journal
-- to discover "21 triggers delivered, 0 plans written since 06:25 UTC".
-- With this table, that becomes one SQL.
--
-- Write path: ingestor/tasks.py::planning_heartbeat inserts immediately
-- after send_to_iris returns. The existing 30-min verification pass
-- (tasks.py:2087) and a new <2h retry pass update `resulting_plan_id` +
-- `plan_written_at` by joining plan_journal on plan_id or time window.

BEGIN;

CREATE TABLE IF NOT EXISTS plan_delivery_log (
    id              SERIAL PRIMARY KEY,
    delivered_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type      TEXT NOT NULL,       -- SUNRISE | SUNSET | TRANSITION | FORECAST | DEVIATION
    event_label     TEXT,                -- human-readable label (e.g. "Tree Shade")
    session_key     TEXT,                -- OpenClaw session key used
    wake_mode       TEXT,                -- 'now' | 'next-heartbeat'
    gateway_status  INTEGER,             -- HTTP status code returned by OpenClaw
    gateway_body    TEXT,                -- response body (for non-2xx OR 200 with a non-ok structure)
    resulting_plan_id   TEXT,            -- set by verification pass if a plan landed post-delivery
    plan_written_at     TIMESTAMPTZ,     -- when the plan landed in plan_journal
    greenhouse_id   TEXT NOT NULL DEFAULT 'vallery' REFERENCES greenhouses(id)
);

CREATE INDEX IF NOT EXISTS plan_delivery_log_delivered_at_idx
    ON plan_delivery_log (delivered_at DESC);
CREATE INDEX IF NOT EXISTS plan_delivery_log_event_type_idx
    ON plan_delivery_log (event_type, delivered_at DESC);
CREATE INDEX IF NOT EXISTS plan_delivery_log_unresolved_idx
    ON plan_delivery_log (delivered_at)
    WHERE resulting_plan_id IS NULL;

COMMENT ON TABLE plan_delivery_log IS
    'Sprint 24.6 / F14: Iris planner delivery audit. One row per send_to_iris '
    'call; resulting_plan_id populated by the verification pass when a plan '
    'lands. Core diagnostic: "SELECT event_type, count(*) FILTER (WHERE '
    'resulting_plan_id IS NOT NULL) AS planned, count(*) AS delivered FROM '
    'plan_delivery_log WHERE delivered_at > now() - interval ''24 hours'' '
    'GROUP BY event_type" — a working Iris gives planned ~ delivered.';

COMMIT;
