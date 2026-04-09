-- 070-plan-accuracy-by-day.sql
-- Extended plan accuracy: per-day breakdown within 72h plans + forecast accuracy

CREATE OR REPLACE VIEW v_plan_accuracy_by_day AS
SELECT plan_id,
    (planned_ts AT TIME ZONE 'America/Denver')::date AS day,
    COUNT(*) AS waypoints,
    COUNT(*) FILTER (WHERE plan_achieved) AS achieved,
    ROUND(100.0 * COUNT(*) FILTER (WHERE plan_achieved)::numeric / NULLIF(COUNT(*), 0)::numeric, 1) AS accuracy_pct,
    ROUND(AVG(ABS(overshoot))::numeric, 2) AS mean_abs_error
FROM v_plan_compliance
GROUP BY plan_id, (planned_ts AT TIME ZONE 'America/Denver')::date;

-- Forecast accuracy: compare forecast vs observed per day per horizon
CREATE OR REPLACE VIEW v_forecast_accuracy_daily AS
WITH forecast_deduped AS (
    SELECT DISTINCT ON (ts) ts, fetched_at, temp_f, rh_pct, cloud_cover_pct,
        EXTRACT(EPOCH FROM ts - fetched_at) / 3600 AS horizon_hours
    FROM weather_forecast
    WHERE ts < now()
    ORDER BY ts, fetched_at DESC
),
observed AS (
    SELECT date_trunc('hour', ts) AS hour,
        AVG(temp_avg) AS obs_temp,
        AVG(rh_avg) AS obs_rh
    FROM climate
    WHERE temp_avg IS NOT NULL AND ts > now() - interval '30 days'
    GROUP BY 1
)
SELECT
    (f.ts AT TIME ZONE 'America/Denver')::date AS day,
    CASE
        WHEN f.horizon_hours <= 24 THEN '0-24h'
        WHEN f.horizon_hours <= 48 THEN '24-48h'
        ELSE '48-72h'
    END AS horizon,
    COUNT(*) AS hours,
    ROUND(AVG(ABS(f.temp_f - o.obs_temp))::numeric, 1) AS temp_mae,
    ROUND(AVG(f.temp_f - o.obs_temp)::numeric, 1) AS temp_bias,
    ROUND(AVG(ABS(f.rh_pct - o.obs_rh))::numeric, 1) AS rh_mae,
    ROUND(AVG(f.rh_pct - o.obs_rh)::numeric, 1) AS rh_bias
FROM forecast_deduped f
JOIN observed o ON date_trunc('hour', f.ts) = o.hour
WHERE f.ts > now() - interval '30 days'
GROUP BY 1, 2;
