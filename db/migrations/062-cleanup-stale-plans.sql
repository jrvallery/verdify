-- 062-cleanup-stale-plans.sql
-- Deactivate all setpoint_plan rows except the newest plan_id per parameter.
-- After this, only the latest scheduled plan's waypoints are active.

WITH latest AS (
    SELECT DISTINCT ON (parameter) parameter, plan_id, created_at
    FROM setpoint_plan
    WHERE is_active = true
    ORDER BY parameter, created_at DESC
)
UPDATE setpoint_plan sp SET is_active = false
WHERE sp.is_active = true
AND NOT EXISTS (
    SELECT 1 FROM latest l
    WHERE l.parameter = sp.parameter AND l.plan_id = sp.plan_id
);
