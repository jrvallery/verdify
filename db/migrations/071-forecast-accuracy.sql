-- Migration 071: Forecast accuracy view
-- Compares weather_forecast temp/RH/cloud vs observed climate per day
-- Uses DISTINCT ON to pick the latest fetched_at per forecast hour,
-- then joins against hourly-averaged climate observations.

BEGIN;

DROP VIEW IF EXISTS v_forecast_accuracy_daily;

CREATE VIEW v_forecast_accuracy_daily AS
WITH forecast_deduped AS (
    -- Latest fetch per forecast hour (most complete data)
    SELECT DISTINCT ON (ts)
        ts,
        fetched_at,
        temp_f,
        rh_pct,
        cloud_cover_pct
    FROM weather_forecast
    WHERE ts >= now() - interval '14 days'
      AND ts <= now()
    ORDER BY ts, fetched_at DESC
),
forecast_daily AS (
    SELECT
        date_trunc('day', ts)::date AS date,
        avg(temp_f)                 AS fc_temp_avg,
        avg(rh_pct)                 AS fc_rh_avg,
        avg(cloud_cover_pct)        AS fc_cloud_avg,
        -- Average horizon: how far ahead the forecast was made
        avg(EXTRACT(EPOCH FROM (ts - fetched_at)) / 3600.0) AS horizon_hours
    FROM forecast_deduped
    GROUP BY 1
),
observed_daily AS (
    SELECT
        date_trunc('day', ts)::date AS date,
        avg(outdoor_temp_f)         AS obs_temp_avg,
        avg(outdoor_rh_pct)         AS obs_rh_avg
    FROM climate
    WHERE ts >= now() - interval '14 days'
      AND ts <= now()
    GROUP BY 1
)
SELECT
    f.date,
    p.param,
    CASE p.param
        WHEN 'temp_f'          THEN f.fc_temp_avg
        WHEN 'rh_pct'          THEN f.fc_rh_avg
        WHEN 'cloud_cover_pct' THEN f.fc_cloud_avg
    END AS forecast_avg,
    CASE p.param
        WHEN 'temp_f'          THEN o.obs_temp_avg
        WHEN 'rh_pct'          THEN o.obs_rh_avg
        WHEN 'cloud_cover_pct' THEN NULL  -- no observed cloud sensor
    END AS observed_avg,
    CASE p.param
        WHEN 'temp_f'          THEN f.fc_temp_avg  - o.obs_temp_avg
        WHEN 'rh_pct'          THEN f.fc_rh_avg    - o.obs_rh_avg
        WHEN 'cloud_cover_pct' THEN NULL
    END AS bias,
    CASE p.param
        WHEN 'temp_f'          THEN abs(f.fc_temp_avg  - o.obs_temp_avg)
        WHEN 'rh_pct'          THEN abs(f.fc_rh_avg    - o.obs_rh_avg)
        WHEN 'cloud_cover_pct' THEN NULL
    END AS abs_error,
    round(f.horizon_hours::numeric, 1) AS horizon_hours
FROM forecast_daily f
JOIN observed_daily o USING (date)
CROSS JOIN (VALUES ('temp_f'), ('rh_pct'), ('cloud_cover_pct')) AS p(param)
ORDER BY f.date DESC, p.param;

COMMIT;
