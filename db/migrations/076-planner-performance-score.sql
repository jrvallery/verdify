-- 076-planner-performance-score.sql
-- Automated planner performance scoring: stress-efficiency composite KPI
-- Replaces manual 1-10 outcome_score with computed metrics

-- View: stress-efficiency ratio for any date range
-- This is the top-level KPI: minimize stress while minimizing cost
CREATE OR REPLACE VIEW v_planner_performance AS
WITH daily AS (
    SELECT
        date,
        COALESCE(stress_hours_heat, 0)     AS heat_stress_h,
        COALESCE(stress_hours_cold, 0)     AS cold_stress_h,
        COALESCE(stress_hours_vpd_high, 0) AS vpd_high_stress_h,
        COALESCE(stress_hours_vpd_low, 0)  AS vpd_low_stress_h,
        COALESCE(stress_hours_heat, 0) + COALESCE(stress_hours_cold, 0)
            + COALESCE(stress_hours_vpd_high, 0) + COALESCE(stress_hours_vpd_low, 0)
            AS total_stress_h,
        COALESCE(cost_total, 0)            AS cost_total,
        COALESCE(cost_electric, 0)         AS cost_electric,
        COALESCE(cost_gas, 0)              AS cost_gas,
        COALESCE(cost_water, 0)            AS cost_water
    FROM daily_summary
    WHERE date IS NOT NULL
)
SELECT
    date,
    heat_stress_h,
    cold_stress_h,
    vpd_high_stress_h,
    vpd_low_stress_h,
    total_stress_h,
    -- Compliance: fraction of 24h NOT in stress
    ROUND(((1.0 - LEAST(total_stress_h / 24.0, 1.0)) * 100)::numeric, 1) AS compliance_pct,
    cost_total,
    cost_electric,
    cost_gas,
    cost_water,
    -- Stress-efficiency ratio: $/stress-hour (higher = spending more per stress hour)
    -- NULL if zero stress (perfect day)
    CASE WHEN total_stress_h > 0
         THEN ROUND((cost_total / total_stress_h)::numeric, 2)
         ELSE NULL END AS cost_per_stress_hour,
    -- Planner score (0-100): weighted composite
    -- Priority 1: stay in band (80%). Priority 2: minimize cost (20%).
    ROUND((
        -- Compliance component (0-80): % of day in-band
        -- 0h stress = 80, 24h stress = 0. Linear scale.
        (1.0 - LEAST(total_stress_h / 24.0, 1.0)) * 80
        -- Cost efficiency component (0-20): <$5/day = full marks, $15+ = 0
        + GREATEST(0, (1.0 - LEAST(cost_total / 15.0, 1.0))) * 20
    )::numeric, 1) AS planner_score
FROM daily;

-- Function: get planner score card for a date (used by gather-plan-context.sh)
CREATE OR REPLACE FUNCTION fn_planner_scorecard(target_date date DEFAULT CURRENT_DATE)
RETURNS TABLE(
    metric text,
    value text
) LANGUAGE sql STABLE AS $$
    SELECT 'planner_score'::text,       planner_score::text FROM v_planner_performance WHERE date = target_date
    UNION ALL
    SELECT 'compliance_pct',            compliance_pct::text FROM v_planner_performance WHERE date = target_date
    UNION ALL
    SELECT 'total_stress_h',            total_stress_h::text FROM v_planner_performance WHERE date = target_date
    UNION ALL
    SELECT 'heat_stress_h',             heat_stress_h::text FROM v_planner_performance WHERE date = target_date
    UNION ALL
    SELECT 'cold_stress_h',             cold_stress_h::text FROM v_planner_performance WHERE date = target_date
    UNION ALL
    SELECT 'vpd_high_stress_h',         vpd_high_stress_h::text FROM v_planner_performance WHERE date = target_date
    UNION ALL
    SELECT 'vpd_low_stress_h',          vpd_low_stress_h::text FROM v_planner_performance WHERE date = target_date
    UNION ALL
    SELECT 'cost_total',                cost_total::text FROM v_planner_performance WHERE date = target_date
    UNION ALL
    SELECT 'cost_per_stress_hour',      COALESCE(cost_per_stress_hour::text, 'perfect') FROM v_planner_performance WHERE date = target_date
    UNION ALL
    SELECT '7d_avg_score',              ROUND(AVG(planner_score)::numeric, 1)::text
        FROM v_planner_performance WHERE date BETWEEN target_date - 6 AND target_date
    UNION ALL
    SELECT '7d_avg_stress',             ROUND(AVG(total_stress_h)::numeric, 1)::text
        FROM v_planner_performance WHERE date BETWEEN target_date - 6 AND target_date
    UNION ALL
    SELECT '7d_avg_cost',               ROUND(AVG(cost_total)::numeric, 2)::text
        FROM v_planner_performance WHERE date BETWEEN target_date - 6 AND target_date;
$$;

-- Update v_stress_hours_today to use band-aware setpoints (not just latest setpoint_changes)
-- The current view uses DISTINCT ON setpoint_changes which misses time-of-day band variation.
-- This is correct for now since bands change slowly, but noted for future improvement.

COMMENT ON VIEW v_planner_performance IS
    'Top-level KPI: planner_score (0-100). Priority 1: compliance/in-band time (80%). Priority 2: cost efficiency (20%). Used by planner self-assessment.';
