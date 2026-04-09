-- Migration 031: Replace setpoint_schedule with setpoint_plan
-- The static hour-of-day schedule is replaced by a dynamic AI-driven planning table.
-- Iris generates rolling 24-48h setpoint plans, the dispatcher pushes them to ESP32.

-- Drop the static table (just created, no dependencies)
DROP TABLE IF EXISTS setpoint_schedule;

-- Create the dynamic planning table
CREATE TABLE IF NOT EXISTS setpoint_plan (
    ts          TIMESTAMPTZ NOT NULL,
    parameter   TEXT NOT NULL,
    value       DOUBLE PRECISION NOT NULL,
    plan_id     TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'iris',
    reason      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (ts, parameter, plan_id)
);

SELECT create_hypertable('setpoint_plan', 'ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_setplan_param ON setpoint_plan (parameter, ts);
CREATE INDEX IF NOT EXISTS idx_setplan_active ON setpoint_plan (ts DESC)
    WHERE ts >= now() - interval '1 hour';
CREATE INDEX IF NOT EXISTS idx_setplan_planid ON setpoint_plan (plan_id, ts);

COMMENT ON TABLE setpoint_plan IS 'AI-generated setpoint schedule. Iris writes future waypoints, dispatcher pushes to ESP32 via aioesphomeapi. Each row = "at time T, set parameter P to value V."';
COMMENT ON COLUMN setpoint_plan.ts IS 'When this setpoint should take effect (UTC)';
COMMENT ON COLUMN setpoint_plan.parameter IS 'Matches setpoint_changes.parameter and ESP32 number entity names';
COMMENT ON COLUMN setpoint_plan.plan_id IS 'Identifies which planning cycle generated this (e.g. 2026-03-24T07:00)';
COMMENT ON COLUMN setpoint_plan.reason IS 'AI reasoning for this value (e.g. pre-cool for 95°F forecast)';
