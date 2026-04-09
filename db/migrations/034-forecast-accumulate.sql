-- Migration 034: Switch weather_forecast to accumulation mode + planning views
-- Each hourly fetch now INSERTs (no overwrite). Views provide latest + accuracy.

-- Step 1: Drop unique constraint so multiple fetches per forecast hour can coexist
DROP INDEX IF EXISTS weather_forecast_ts_unique;

-- Step 2: Add composite index for efficient "latest per hour" queries
CREATE INDEX IF NOT EXISTS idx_forecast_ts_fetched ON weather_forecast (ts, fetched_at DESC);

-- Step 3: View — latest forecast per hour (what dashboards and Iris should query)
CREATE OR REPLACE VIEW v_forecast_latest AS
SELECT DISTINCT ON (ts) *
FROM weather_forecast
WHERE ts > now() - interval '24 hours'
ORDER BY ts, fetched_at DESC;

COMMENT ON VIEW v_forecast_latest IS 'Most recent forecast for each hour. Use instead of weather_forecast directly.';

-- Step 4: View — forecast accuracy (compare past forecasts vs actual conditions)
CREATE OR REPLACE VIEW v_forecast_accuracy AS
SELECT
  f.ts AS forecast_hour,
  f.fetched_at,
  ROUND(EXTRACT(EPOCH FROM f.ts - f.fetched_at)::numeric / 3600, 1) AS lead_hours,
  f.temp_f AS forecast_temp,
  m.outdoor_temp_f AS actual_temp,
  ROUND((f.temp_f - m.outdoor_temp_f)::numeric, 1) AS temp_error_f,
  f.vpd_kpa AS forecast_vpd,
  m.vpd_avg AS actual_vpd,
  ROUND((f.vpd_kpa - m.vpd_avg)::numeric, 2) AS vpd_error_kpa,
  f.solar_w_m2 AS forecast_solar,
  m.solar_w_m2 AS actual_solar,
  ROUND((f.solar_w_m2 - m.solar_w_m2)::numeric, 1) AS solar_error_w
FROM weather_forecast f
JOIN v_climate_merged m ON time_bucket('1 hour', m.bucket) = f.ts
WHERE f.ts < now();

COMMENT ON VIEW v_forecast_accuracy IS 'Forecast vs actual comparison. Uses outdoor_temp_f (not indoor). lead_hours = how far ahead the forecast was made.';

-- Step 5: Iris planning context — single query for all planning inputs
CREATE OR REPLACE VIEW v_iris_planning_context AS
SELECT
  now() AS query_ts,

  -- Current conditions (last hour)
  (SELECT json_build_object(
    'temp_avg', ROUND(AVG(temp_avg)::numeric, 1),
    'vpd_avg', ROUND(AVG(vpd_avg)::numeric, 2),
    'rh_avg', ROUND(AVG(rh_avg)::numeric, 1),
    'outdoor_temp_f', ROUND(AVG(outdoor_temp_f)::numeric, 1),
    'dli_today', ROUND(MAX(dli_today)::numeric, 2),
    'indoor_lux', ROUND(AVG(lux)::numeric, 0),
    'co2_ppm', ROUND(AVG(co2_ppm)::numeric, 0)
  ) FROM climate WHERE ts >= now() - interval '1 hour' AND temp_avg IS NOT NULL
  ) AS current_conditions,

  -- Yesterday's summary
  (SELECT json_build_object(
    'date', date,
    'cost_total', cost_total, 'cost_electric', cost_electric,
    'cost_gas', cost_gas, 'cost_water', cost_water,
    'kwh', kwh_estimated, 'water_gal', water_used_gal, 'dli_final', dli_final,
    'runtime_heat1_h', ROUND((runtime_heat1_min/60.0)::numeric, 1),
    'runtime_heat2_h', ROUND((runtime_heat2_min/60.0)::numeric, 1),
    'runtime_fog_h', ROUND((runtime_fog_min/60.0)::numeric, 1),
    'runtime_fan_h', ROUND(((runtime_fan1_min+runtime_fan2_min)/60.0)::numeric, 1),
    'runtime_grow_light_h', ROUND((runtime_grow_light_min/60.0)::numeric, 1)
  ) FROM daily_summary ORDER BY date DESC LIMIT 1
  ) AS yesterday_summary,

  -- 48h forecast (latest version per hour, 12 key params)
  (SELECT json_agg(row_to_json(sub) ORDER BY sub.ts)
   FROM (
     SELECT DISTINCT ON (ts) ts, temp_f, rh_pct, vpd_kpa, solar_w_m2,
       direct_radiation_w_m2, diffuse_radiation_w_m2, cloud_cover_pct,
       precip_prob_pct, wind_gust_mph, weather_code, sunshine_duration_s, et0_mm,
       dew_point_f, soil_temp_f, uv_index
     FROM weather_forecast
     WHERE ts BETWEEN now() AND now() + interval '48 hours'
     ORDER BY ts, fetched_at DESC
   ) sub
  ) AS forecast_48h,

  -- Current setpoints (all params)
  (SELECT json_object_agg(parameter, value)
   FROM (SELECT DISTINCT ON (parameter) parameter, value FROM setpoint_changes ORDER BY parameter, ts DESC) sub
  ) AS current_setpoints,

  -- Active plan (future waypoints)
  (SELECT json_agg(row_to_json(sub) ORDER BY sub.ts)
   FROM (
     SELECT ts, parameter, value, reason
     FROM setpoint_plan WHERE ts > now() AND parameter != 'plan_metadata'
     ORDER BY ts
   ) sub
  ) AS active_plan,

  -- System health
  (SELECT json_build_object(
    'composite_score', composite_score,
    'sensor_health_pct', sensor_health_pct,
    'compliance_24h_pct', compliance_24h_pct,
    'open_alerts', open_alerts
  ) FROM v_system_health_score
  ) AS system_health,

  -- 7-day cost trend
  (SELECT json_agg(row_to_json(sub) ORDER BY sub.date)
   FROM (
     SELECT date, cost_total, cost_electric, cost_gas, cost_water, kwh_estimated, water_used_gal
     FROM daily_summary WHERE date >= CURRENT_DATE - 7 ORDER BY date
   ) sub
  ) AS cost_trend_7d;

COMMENT ON VIEW v_iris_planning_context IS 'Single-query planning context for Iris. Returns current conditions, yesterday summary, 48h forecast, setpoints, active plan, health score, and 7-day cost trend as JSON columns.';
