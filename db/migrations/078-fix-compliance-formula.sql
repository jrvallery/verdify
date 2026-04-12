-- 078: Fix compliance formula — use time-union, not sum of independent stress hours
--
-- Problem: v_planner_performance computed compliance as (1 - total_stress/24)*100
-- but total_stress is the SUM of 4 independent categories that can overlap.
-- 61h total → 0% compliance even though the system was mostly in band.
--
-- Fix: Compute compliance as % of climate rows where BOTH temp and VPD are in band,
-- using the setpoints that were active at each reading's timestamp.

-- Helper: get the band setpoint active at a given time for a given parameter
CREATE OR REPLACE FUNCTION fn_setpoint_at(p_param TEXT, p_ts TIMESTAMPTZ)
RETURNS FLOAT AS $$
    SELECT value FROM setpoint_changes
    WHERE parameter = p_param AND ts <= p_ts
    ORDER BY ts DESC LIMIT 1;
$$ LANGUAGE SQL STABLE;

-- Replace v_stress_hours_today with a version that uses time-appropriate bands
CREATE OR REPLACE VIEW v_stress_hours_today AS
WITH readings AS (
    SELECT ts, temp_avg, vpd_avg
    FROM climate
    WHERE ts >= date_trunc('day', now() AT TIME ZONE 'America/Denver') AT TIME ZONE 'America/Denver'
      AND temp_avg IS NOT NULL
)
SELECT
    date_trunc('day', r.ts AT TIME ZONE 'America/Denver') AS date,
    round(sum(CASE WHEN r.temp_avg < fn_setpoint_at('temp_low', r.ts)
                   THEN 1.0/60 ELSE 0 END)::numeric, 2) AS cold_stress_hours,
    round(sum(CASE WHEN r.temp_avg > fn_setpoint_at('temp_high', r.ts)
                   THEN 1.0/60 ELSE 0 END)::numeric, 2) AS heat_stress_hours,
    round(sum(CASE WHEN r.vpd_avg > fn_setpoint_at('vpd_high', r.ts)
                   THEN 1.0/60 ELSE 0 END)::numeric, 2) AS vpd_stress_hours,
    round(sum(CASE WHEN r.vpd_avg < fn_setpoint_at('vpd_low', r.ts)
                   THEN 1.0/60 ELSE 0 END)::numeric, 2) AS vpd_low_hours
FROM readings r
GROUP BY 1;

-- Replace v_planner_performance with proper time-union compliance
CREATE OR REPLACE VIEW v_planner_performance AS
WITH daily_compliance AS (
    -- For each day, compute % of minutes where BOTH temp AND VPD are in band
    -- using the setpoints active at each reading's timestamp
    SELECT
        (c.ts AT TIME ZONE 'America/Denver')::date AS date,
        count(*) AS total_readings,
        count(*) FILTER (WHERE
            c.temp_avg >= fn_setpoint_at('temp_low', c.ts)
            AND c.temp_avg <= fn_setpoint_at('temp_high', c.ts)
            AND c.vpd_avg >= fn_setpoint_at('vpd_low', c.ts)
            AND c.vpd_avg <= fn_setpoint_at('vpd_high', c.ts)
        ) AS in_band_readings
    FROM climate c
    WHERE c.temp_avg IS NOT NULL
      AND c.ts >= now() - interval '14 days'
    GROUP BY 1
),
daily AS (
    SELECT
        d.date,
        COALESCE(d.stress_hours_heat, 0) AS heat_stress_h,
        COALESCE(d.stress_hours_cold, 0) AS cold_stress_h,
        COALESCE(d.stress_hours_vpd_high, 0) AS vpd_high_stress_h,
        COALESCE(d.stress_hours_vpd_low, 0) AS vpd_low_stress_h,
        COALESCE(d.stress_hours_heat, 0) + COALESCE(d.stress_hours_cold, 0)
            + COALESCE(d.stress_hours_vpd_high, 0) + COALESCE(d.stress_hours_vpd_low, 0) AS total_stress_h,
        COALESCE(d.cost_total, 0) AS cost_total,
        COALESCE(d.cost_electric, 0) AS cost_electric,
        COALESCE(d.cost_gas, 0) AS cost_gas,
        COALESCE(d.cost_water, 0) AS cost_water
    FROM daily_summary d
    WHERE d.date IS NOT NULL
)
SELECT
    d.date,
    d.heat_stress_h,
    d.cold_stress_h,
    d.vpd_high_stress_h,
    d.vpd_low_stress_h,
    d.total_stress_h,
    -- Compliance: % of readings where both temp AND VPD in band
    COALESCE(
        round((dc.in_band_readings::numeric / NULLIF(dc.total_readings, 0)) * 100, 1),
        0
    ) AS compliance_pct,
    d.cost_total,
    d.cost_electric,
    d.cost_gas,
    d.cost_water,
    CASE WHEN d.total_stress_h > 0
        THEN round((d.cost_total / d.total_stress_h)::numeric, 2)
        ELSE NULL
    END AS cost_per_stress_hour,
    -- Planner score: 80% compliance + 20% cost efficiency
    round((
        COALESCE((dc.in_band_readings::numeric / NULLIF(dc.total_readings, 0)), 0)
            * 0.8 * 100
        + GREATEST(0, 1.0 - LEAST(d.cost_total / 15.0, 1.0)) * 20
    )::numeric, 1) AS planner_score
FROM daily d
LEFT JOIN daily_compliance dc ON d.date = dc.date;

-- Also update fn_planner_scorecard to use the new view
CREATE OR REPLACE FUNCTION fn_planner_scorecard(p_date DATE DEFAULT CURRENT_DATE)
RETURNS TABLE(metric TEXT, value NUMERIC) AS $$
BEGIN
    RETURN QUERY
    SELECT 'planner_score'::text, p.planner_score FROM v_planner_performance p WHERE p.date = p_date
    UNION ALL
    SELECT 'compliance_pct', p.compliance_pct FROM v_planner_performance p WHERE p.date = p_date
    UNION ALL
    SELECT 'total_stress_h', round(p.total_stress_h::numeric, 1) FROM v_planner_performance p WHERE p.date = p_date
    UNION ALL
    SELECT 'heat_stress_h', round(p.heat_stress_h::numeric, 1) FROM v_planner_performance p WHERE p.date = p_date
    UNION ALL
    SELECT 'cold_stress_h', round(p.cold_stress_h::numeric, 1) FROM v_planner_performance p WHERE p.date = p_date
    UNION ALL
    SELECT 'vpd_high_stress_h', round(p.vpd_high_stress_h::numeric, 1) FROM v_planner_performance p WHERE p.date = p_date
    UNION ALL
    SELECT 'vpd_low_stress_h', round(p.vpd_low_stress_h::numeric, 1) FROM v_planner_performance p WHERE p.date = p_date
    UNION ALL
    SELECT 'cost_total', round(p.cost_total::numeric, 2) FROM v_planner_performance p WHERE p.date = p_date
    UNION ALL
    -- 7-day averages
    SELECT '7d_avg_score', round(avg(p.planner_score), 1) FROM v_planner_performance p WHERE p.date BETWEEN p_date - 7 AND p_date - 1
    UNION ALL
    SELECT '7d_avg_stress', round(avg(p.total_stress_h)::numeric, 1) FROM v_planner_performance p WHERE p.date BETWEEN p_date - 7 AND p_date - 1
    UNION ALL
    SELECT '7d_avg_cost', round(avg(p.cost_total)::numeric, 2) FROM v_planner_performance p WHERE p.date BETWEEN p_date - 7 AND p_date - 1
    UNION ALL
    -- Dew point risk
    SELECT 'dp_margin_min_f', round(min(d.min_margin_f)::numeric, 1) FROM v_dew_point_risk d WHERE d.date = p_date
    UNION ALL
    SELECT '7d_avg_dp_risk', round(avg(d.risk_hours)::numeric, 1) FROM v_dew_point_risk d WHERE d.date BETWEEN p_date - 7 AND p_date - 1;
END;
$$ LANGUAGE plpgsql STABLE;
