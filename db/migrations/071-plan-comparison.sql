-- 071-plan-comparison.sql
-- Compare consecutive scheduled plans: what changed per parameter

CREATE OR REPLACE VIEW v_plan_comparison AS
WITH plan_order AS (
    SELECT DISTINCT plan_id, MIN(created_at) AS created_at
    FROM setpoint_plan
    WHERE plan_id LIKE 'iris-2026%'
      AND plan_id NOT LIKE '%reactive%'
      AND plan_id NOT LIKE '%fix%'
      AND plan_id NOT LIKE '%dev%'
    GROUP BY plan_id
    ORDER BY MIN(created_at) DESC
    LIMIT 20
),
plan_pairs AS (
    SELECT plan_id,
        created_at,
        LAG(plan_id) OVER (ORDER BY created_at) AS prev_plan_id
    FROM plan_order
),
cur_stats AS (
    SELECT sp.plan_id, sp.parameter,
        COUNT(*) AS waypoints,
        ROUND(AVG(sp.value)::numeric, 2) AS avg_value,
        ROUND(MIN(sp.value)::numeric, 2) AS min_value,
        ROUND(MAX(sp.value)::numeric, 2) AS max_value
    FROM setpoint_plan sp
    JOIN plan_pairs pp ON sp.plan_id = pp.plan_id
    WHERE sp.parameter IN (
        'temp_high','temp_low','vpd_high','vpd_hysteresis','d_cool_stage_2',
        'mister_engage_kpa','mister_all_kpa','mister_pulse_on_s',
        'mister_pulse_gap_s','mister_vpd_weight'
    )
    GROUP BY sp.plan_id, sp.parameter
),
prev_stats AS (
    SELECT sp.plan_id AS prev_plan_id, sp.parameter,
        COUNT(*) AS waypoints,
        ROUND(AVG(sp.value)::numeric, 2) AS avg_value,
        ROUND(MIN(sp.value)::numeric, 2) AS min_value,
        ROUND(MAX(sp.value)::numeric, 2) AS max_value
    FROM setpoint_plan sp
    JOIN plan_pairs pp ON sp.plan_id = pp.prev_plan_id
    WHERE sp.parameter IN (
        'temp_high','temp_low','vpd_high','vpd_hysteresis','d_cool_stage_2',
        'mister_engage_kpa','mister_all_kpa','mister_pulse_on_s',
        'mister_pulse_gap_s','mister_vpd_weight'
    )
    GROUP BY sp.plan_id, sp.parameter
)
SELECT
    pp.plan_id,
    pp.prev_plan_id,
    pp.created_at AT TIME ZONE 'America/Denver' AS plan_created,
    COALESCE(c.parameter, p.parameter) AS parameter,
    COALESCE(c.waypoints, 0) AS cur_waypoints,
    COALESCE(p.waypoints, 0) AS prev_waypoints,
    c.avg_value AS cur_avg,
    p.avg_value AS prev_avg,
    ROUND((COALESCE(c.avg_value, 0) - COALESCE(p.avg_value, 0))::numeric, 2) AS delta_avg,
    c.min_value AS cur_min, c.max_value AS cur_max,
    p.min_value AS prev_min, p.max_value AS prev_max
FROM plan_pairs pp
LEFT JOIN cur_stats c ON pp.plan_id = c.plan_id
LEFT JOIN prev_stats p ON pp.prev_plan_id = p.prev_plan_id AND COALESCE(c.parameter, p.parameter) = p.parameter
WHERE pp.prev_plan_id IS NOT NULL
  AND (c.parameter IS NOT NULL OR p.parameter IS NOT NULL)
ORDER BY pp.created_at DESC, COALESCE(c.parameter, p.parameter);
