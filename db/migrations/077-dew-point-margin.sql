-- 077-dew-point-margin.sql
-- Dew point margin KPI: condensation risk tracking
-- Margin = indoor temp_avg - indoor dew_point (both from ESP32 sensors)
-- < 5°F = condensation risk, < 3°F = imminent

-- Add columns to daily_summary
ALTER TABLE daily_summary ADD COLUMN IF NOT EXISTS min_dp_margin_f double precision;
ALTER TABLE daily_summary ADD COLUMN IF NOT EXISTS dp_risk_hours double precision;

-- View: daily dew point risk from climate table
CREATE OR REPLACE VIEW v_dew_point_risk AS
SELECT
    date_trunc('day', ts)::date AS date,
    ROUND(MIN(temp_avg - dew_point)::numeric, 1) AS min_margin_f,
    ROUND(AVG(temp_avg - dew_point)::numeric, 1) AS avg_margin_f,
    -- Hours where margin < 5°F (condensation risk zone)
    ROUND((COUNT(*) FILTER (WHERE temp_avg - dew_point < 5) * 2.0 / 60)::numeric, 1) AS risk_hours,
    -- Hours where margin < 3°F (imminent condensation)
    ROUND((COUNT(*) FILTER (WHERE temp_avg - dew_point < 3) * 2.0 / 60)::numeric, 1) AS critical_hours
FROM climate
WHERE temp_avg IS NOT NULL AND dew_point IS NOT NULL
GROUP BY date_trunc('day', ts)::date
ORDER BY date;

-- Update scorecard function to include dew point metrics
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
    SELECT 'dp_margin_min_f',           COALESCE(min_margin_f::text, 'n/a') FROM v_dew_point_risk WHERE date = target_date
    UNION ALL
    SELECT 'dp_risk_hours',             COALESCE(risk_hours::text, '0') FROM v_dew_point_risk WHERE date = target_date
    UNION ALL
    SELECT '7d_avg_score',              ROUND(AVG(planner_score)::numeric, 1)::text
        FROM v_planner_performance WHERE date BETWEEN target_date - 6 AND target_date
    UNION ALL
    SELECT '7d_avg_stress',             ROUND(AVG(total_stress_h)::numeric, 1)::text
        FROM v_planner_performance WHERE date BETWEEN target_date - 6 AND target_date
    UNION ALL
    SELECT '7d_avg_cost',               ROUND(AVG(cost_total)::numeric, 2)::text
        FROM v_planner_performance WHERE date BETWEEN target_date - 6 AND target_date
    UNION ALL
    SELECT '7d_avg_dp_risk',            ROUND(COALESCE(AVG(risk_hours), 0)::numeric, 1)::text
        FROM v_dew_point_risk WHERE date BETWEEN target_date - 6 AND target_date;
$$;

COMMENT ON VIEW v_dew_point_risk IS
    'Indoor condensation risk: dew point margin (temp_avg - dew_point). <5°F = risk, <3°F = imminent. Computed from ESP32 indoor sensors.';
