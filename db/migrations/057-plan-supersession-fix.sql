-- 057-plan-supersession-fix.sql
-- Fix plan supersession: when a new plan is created, deactivate ALL future waypoints
-- from older plans. This prevents oscillation between old and new plan waypoints.

-- Add a superseded flag to setpoint_plan
ALTER TABLE setpoint_plan ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;

-- Mark old plan waypoints as inactive when they've been superseded by newer plans.
-- A waypoint is superseded if a newer plan (created_at > this plan's created_at)
-- has a waypoint for the same parameter.
UPDATE setpoint_plan sp SET is_active = false
WHERE EXISTS (
    SELECT 1 FROM setpoint_plan newer
    WHERE newer.parameter = sp.parameter
      AND newer.plan_id != sp.plan_id
      AND newer.created_at > sp.created_at
      AND newer.plan_id NOT LIKE 'iris-reactive%'
)
AND sp.plan_id NOT LIKE 'iris-reactive%';

-- Rebuild v_active_plan to only consider active waypoints
CREATE OR REPLACE VIEW v_active_plan AS
SELECT DISTINCT ON (parameter) parameter, value, ts, plan_id, reason, created_at
FROM setpoint_plan
WHERE ts <= now() AND is_active = true
ORDER BY parameter, created_at DESC;

-- Trigger: when a new plan is inserted, deactivate older plans' matching params
CREATE OR REPLACE FUNCTION deactivate_superseded_plans() RETURNS trigger AS $$
BEGIN
    UPDATE setpoint_plan SET is_active = false
    WHERE parameter = NEW.parameter
      AND plan_id != NEW.plan_id
      AND created_at < NEW.created_at
      AND is_active = true;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_plan_supersede ON setpoint_plan;
CREATE TRIGGER trg_plan_supersede
    AFTER INSERT ON setpoint_plan
    FOR EACH ROW EXECUTE FUNCTION deactivate_superseded_plans();
