-- Migration 096: resync planner scorecard SQL with the live DB contract.
--
-- GenAI's typed ScorecardResponse and the public API both expect the 25-metric
-- numeric scorecard currently deployed in production. Migrations 076-078 and
-- db/schema.sql still carried the older text-returning function, so fresh DBs
-- and CI could drift from live.

CREATE OR REPLACE VIEW v_daily_kpi AS
SELECT
    date,
    round(COALESCE(compliance_pct, 0)::numeric, 1) AS compliance_pct,
    round(COALESCE(temp_compliance_pct, 0)::numeric, 1) AS temp_compliance_pct,
    round(COALESCE(vpd_compliance_pct, 0)::numeric, 1) AS vpd_compliance_pct,
    round(COALESCE(stress_hours_heat, 0)::numeric, 2) AS heat_stress_h,
    round(COALESCE(stress_hours_cold, 0)::numeric, 2) AS cold_stress_h,
    round(COALESCE(stress_hours_vpd_high, 0)::numeric, 2) AS vpd_high_stress_h,
    round(COALESCE(stress_hours_vpd_low, 0)::numeric, 2) AS vpd_low_stress_h,
    round(
        (
            COALESCE(stress_hours_heat, 0)
            + COALESCE(stress_hours_cold, 0)
            + COALESCE(stress_hours_vpd_high, 0)
            + COALESCE(stress_hours_vpd_low, 0)
        )::numeric,
        2
    ) AS total_stress_h,
    round(COALESCE(kwh_estimated, kwh_total, 0)::numeric, 2) AS kwh,
    round(COALESCE(therms_estimated, gas_used_therms, 0)::numeric, 3) AS therms,
    round(COALESCE(water_used_gal, 0)::numeric, 0) AS water_gal,
    round(COALESCE(mister_water_gal, 0)::numeric, 0) AS mister_water_gal,
    round(COALESCE(cost_electric, 0)::numeric, 2) AS cost_electric,
    round(COALESCE(cost_gas, 0)::numeric, 2) AS cost_gas,
    round(COALESCE(cost_water, 0)::numeric, 2) AS cost_water,
    round(COALESCE(cost_total, 0)::numeric, 2) AS cost_total,
    round(temp_min::numeric, 1) AS temp_min,
    round(temp_max::numeric, 1) AS temp_max,
    round(temp_avg::numeric, 1) AS temp_avg,
    round(vpd_min::numeric, 2) AS vpd_min,
    round(vpd_max::numeric, 2) AS vpd_max,
    round(vpd_avg::numeric, 2) AS vpd_avg,
    round(dli_final::numeric, 1) AS dli,
    round(min_dp_margin_f::numeric, 1) AS dp_margin_min_f,
    round(COALESCE(dp_risk_hours, 0)::numeric, 1) AS dp_risk_hours,
    round(
        (
            COALESCE(compliance_pct, 0) / 100.0 * 80
            + GREATEST(0, 1.0 - LEAST(COALESCE(cost_total, 0) / 15.0, 1.0)) * 20
        )::numeric,
        1
    ) AS planner_score
FROM daily_summary
WHERE date IS NOT NULL
ORDER BY date;

DROP FUNCTION IF EXISTS fn_planner_scorecard(date);
DROP VIEW IF EXISTS v_planner_performance;

CREATE VIEW v_planner_performance AS
WITH daily AS (
    SELECT
        d.date,
        COALESCE(d.stress_hours_heat, 0) AS heat_stress_h,
        COALESCE(d.stress_hours_cold, 0) AS cold_stress_h,
        COALESCE(d.stress_hours_vpd_high, 0) AS vpd_high_stress_h,
        COALESCE(d.stress_hours_vpd_low, 0) AS vpd_low_stress_h,
        COALESCE(d.stress_hours_heat, 0)
            + COALESCE(d.stress_hours_cold, 0)
            + COALESCE(d.stress_hours_vpd_high, 0)
            + COALESCE(d.stress_hours_vpd_low, 0) AS total_stress_h,
        COALESCE(d.compliance_pct, 0) AS compliance_pct,
        COALESCE(d.temp_compliance_pct, 0) AS temp_compliance_pct,
        COALESCE(d.vpd_compliance_pct, 0) AS vpd_compliance_pct,
        COALESCE(d.cost_total, 0) AS cost_total,
        COALESCE(d.cost_electric, 0) AS cost_electric,
        COALESCE(d.cost_gas, 0) AS cost_gas,
        COALESCE(d.cost_water, 0) AS cost_water
    FROM daily_summary d
    WHERE d.date IS NOT NULL
)
SELECT
    date,
    heat_stress_h,
    cold_stress_h,
    vpd_high_stress_h,
    vpd_low_stress_h,
    total_stress_h,
    round(compliance_pct::numeric, 1) AS compliance_pct,
    round(temp_compliance_pct::numeric, 1) AS temp_compliance_pct,
    round(vpd_compliance_pct::numeric, 1) AS vpd_compliance_pct,
    cost_total,
    cost_electric,
    cost_gas,
    cost_water,
    CASE
        WHEN total_stress_h > 0 THEN round((cost_total / total_stress_h)::numeric, 2)
        ELSE NULL::numeric
    END AS cost_per_stress_hour,
    round(
        (
            compliance_pct / 100.0 * 80
            + GREATEST(0, 1.0 - LEAST(cost_total / 15.0, 1.0)) * 20
        )::numeric,
        1
    ) AS planner_score
FROM daily;

CREATE OR REPLACE FUNCTION fn_planner_scorecard(p_date date DEFAULT CURRENT_DATE)
RETURNS TABLE(metric text, value numeric) AS $$
BEGIN
    RETURN QUERY
    SELECT 'planner_score'::text, k.planner_score FROM v_daily_kpi k WHERE k.date = p_date
    UNION ALL SELECT 'compliance_pct', k.compliance_pct FROM v_daily_kpi k WHERE k.date = p_date
    UNION ALL SELECT 'temp_compliance_pct', k.temp_compliance_pct FROM v_daily_kpi k WHERE k.date = p_date
    UNION ALL SELECT 'vpd_compliance_pct', k.vpd_compliance_pct FROM v_daily_kpi k WHERE k.date = p_date
    UNION ALL SELECT 'total_stress_h', k.total_stress_h FROM v_daily_kpi k WHERE k.date = p_date
    UNION ALL SELECT 'heat_stress_h', k.heat_stress_h FROM v_daily_kpi k WHERE k.date = p_date
    UNION ALL SELECT 'cold_stress_h', k.cold_stress_h FROM v_daily_kpi k WHERE k.date = p_date
    UNION ALL SELECT 'vpd_high_stress_h', k.vpd_high_stress_h FROM v_daily_kpi k WHERE k.date = p_date
    UNION ALL SELECT 'vpd_low_stress_h', k.vpd_low_stress_h FROM v_daily_kpi k WHERE k.date = p_date
    UNION ALL SELECT 'kwh', k.kwh FROM v_daily_kpi k WHERE k.date = p_date
    UNION ALL SELECT 'therms', k.therms FROM v_daily_kpi k WHERE k.date = p_date
    UNION ALL SELECT 'water_gal', k.water_gal FROM v_daily_kpi k WHERE k.date = p_date
    UNION ALL SELECT 'mister_water_gal', k.mister_water_gal FROM v_daily_kpi k WHERE k.date = p_date
    UNION ALL SELECT 'cost_electric', k.cost_electric FROM v_daily_kpi k WHERE k.date = p_date
    UNION ALL SELECT 'cost_gas', k.cost_gas FROM v_daily_kpi k WHERE k.date = p_date
    UNION ALL SELECT 'cost_water', k.cost_water FROM v_daily_kpi k WHERE k.date = p_date
    UNION ALL SELECT 'cost_total', k.cost_total FROM v_daily_kpi k WHERE k.date = p_date
    UNION ALL SELECT 'dp_margin_min_f', k.dp_margin_min_f FROM v_daily_kpi k WHERE k.date = p_date
    UNION ALL SELECT 'dp_risk_hours', k.dp_risk_hours FROM v_daily_kpi k WHERE k.date = p_date
    UNION ALL SELECT '7d_avg_score', round(avg(k.planner_score), 1) FROM v_daily_kpi k WHERE k.date BETWEEN p_date - 7 AND p_date - 1
    UNION ALL SELECT '7d_avg_compliance', round(avg(k.compliance_pct), 1) FROM v_daily_kpi k WHERE k.date BETWEEN p_date - 7 AND p_date - 1
    UNION ALL SELECT '7d_avg_cost', round(avg(k.cost_total), 2) FROM v_daily_kpi k WHERE k.date BETWEEN p_date - 7 AND p_date - 1
    UNION ALL SELECT '7d_avg_kwh', round(avg(k.kwh), 1) FROM v_daily_kpi k WHERE k.date BETWEEN p_date - 7 AND p_date - 1
    UNION ALL SELECT '7d_avg_therms', round(avg(k.therms), 3) FROM v_daily_kpi k WHERE k.date BETWEEN p_date - 7 AND p_date - 1
    UNION ALL SELECT '7d_avg_water_gal', round(avg(k.water_gal), 0) FROM v_daily_kpi k WHERE k.date BETWEEN p_date - 7 AND p_date - 1;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON VIEW v_daily_kpi IS
    'Daily KPI projection consumed by fn_planner_scorecard and planner/API scorecard contracts.';

COMMENT ON VIEW v_planner_performance IS
    'Top-level KPI: planner_score (0-100). Priority 1: compliance/in-band time (80%). Priority 2: cost efficiency (20%). Used by planner self-assessment.';
