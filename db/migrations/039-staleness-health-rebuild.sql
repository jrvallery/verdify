-- Migration 039: Rebuild v_sensor_staleness + v_system_health_score
-- Part A (Task 1.15): v_sensor_staleness with is_stale, last_seen_at, seconds_since
-- Part B (Task 3.7): v_system_health_score as component-based + fn_system_health()

-- ============================================================
-- PART A: v_sensor_staleness
-- ============================================================

DROP VIEW IF EXISTS v_sensor_staleness CASCADE;
-- CASCADE will also drop v_system_health_score and v_iris_planning_context

CREATE OR REPLACE VIEW v_sensor_staleness AS
WITH last_readings AS (
  -- Climate sensors: find MAX(ts) WHERE column IS NOT NULL
  SELECT
    sr.sensor_id,
    sr.type,
    sr.zone,
    sr.expected_interval_s,
    sr.source_table,
    sr.source_column,
    CASE sr.source_table
      WHEN 'climate' THEN (
        SELECT MAX(c.ts) FROM climate c
        WHERE c.ts > now() - interval '2 hours'  -- limit scan window for performance
        AND CASE sr.source_column
          WHEN 'temp_avg' THEN c.temp_avg
          WHEN 'temp_north' THEN c.temp_north
          WHEN 'temp_south' THEN c.temp_south
          WHEN 'temp_east' THEN c.temp_east
          WHEN 'temp_west' THEN c.temp_west
          WHEN 'temp_case' THEN c.temp_case
          WHEN 'temp_control' THEN c.temp_control
          WHEN 'temp_intake' THEN c.temp_intake
          WHEN 'rh_avg' THEN c.rh_avg
          WHEN 'rh_north' THEN c.rh_north
          WHEN 'rh_south' THEN c.rh_south
          WHEN 'rh_east' THEN c.rh_east
          WHEN 'rh_west' THEN c.rh_west
          WHEN 'rh_case' THEN c.rh_case
          WHEN 'vpd_avg' THEN c.vpd_avg
          WHEN 'vpd_north' THEN c.vpd_north
          WHEN 'vpd_south' THEN c.vpd_south
          WHEN 'vpd_east' THEN c.vpd_east
          WHEN 'vpd_west' THEN c.vpd_west
          WHEN 'vpd_control' THEN c.vpd_control
          WHEN 'co2_ppm' THEN c.co2_ppm
          WHEN 'lux' THEN c.lux
          WHEN 'dli_today' THEN c.dli_today
          WHEN 'dew_point' THEN c.dew_point
          WHEN 'abs_humidity' THEN c.abs_humidity
          WHEN 'enthalpy_delta' THEN c.enthalpy_delta
          WHEN 'flow_gpm' THEN c.flow_gpm
          WHEN 'water_total_gal' THEN c.water_total_gal
          WHEN 'mister_water_today' THEN c.mister_water_today
          WHEN 'outdoor_temp_f' THEN c.outdoor_temp_f
          WHEN 'outdoor_rh_pct' THEN c.outdoor_rh_pct
          WHEN 'wind_speed_mph' THEN c.wind_speed_mph
          WHEN 'wind_direction_deg' THEN c.wind_direction_deg
          WHEN 'outdoor_lux' THEN c.outdoor_lux
          WHEN 'solar_irradiance_w_m2' THEN c.solar_irradiance_w_m2
          WHEN 'pressure_hpa' THEN c.pressure_hpa
          WHEN 'uv_index' THEN c.uv_index
          WHEN 'precip_in' THEN c.precip_in
          WHEN 'precip_intensity_in_h' THEN c.precip_intensity_in_h
          WHEN 'feels_like_f' THEN c.feels_like_f
          WHEN 'wet_bulb_temp_f' THEN c.wet_bulb_temp_f
          WHEN 'vapor_pressure_inhg' THEN c.vapor_pressure_inhg
          WHEN 'air_density_kg_m3' THEN c.air_density_kg_m3
          WHEN 'wind_gust_mph' THEN c.wind_gust_mph
          WHEN 'wind_lull_mph' THEN c.wind_lull_mph
          WHEN 'wind_speed_avg_mph' THEN c.wind_speed_avg_mph
          WHEN 'wind_direction_avg_deg' THEN c.wind_direction_avg_deg
          WHEN 'lightning_count' THEN c.lightning_count::float
          WHEN 'lightning_avg_dist_mi' THEN c.lightning_avg_dist_mi
          WHEN 'hydro_ec_us_cm' THEN c.hydro_ec_us_cm
          WHEN 'hydro_orp_mv' THEN c.hydro_orp_mv
          WHEN 'hydro_ph' THEN c.hydro_ph
          WHEN 'hydro_tds_ppm' THEN c.hydro_tds_ppm
          WHEN 'hydro_water_temp_f' THEN c.hydro_water_temp_f
          WHEN 'hydro_battery_pct' THEN c.hydro_battery_pct
          WHEN 'solar_altitude_deg' THEN c.solar_altitude_deg
          WHEN 'solar_azimuth_deg' THEN c.solar_azimuth_deg
          ELSE NULL
        END IS NOT NULL
      )
      WHEN 'equipment_state' THEN (
        SELECT MAX(es.ts) FROM equipment_state es
        WHERE es.ts > now() - interval '2 hours'
        AND es.equipment = sr.source_column
      )
      WHEN 'system_state' THEN (
        SELECT MAX(ss.ts) FROM system_state ss
        WHERE ss.ts > now() - interval '2 hours'
        AND ss.entity = sr.source_column
      )
      WHEN 'diagnostics' THEN (
        SELECT MAX(d.ts) FROM diagnostics d
        WHERE d.ts > now() - interval '2 hours'
      )
    END AS last_seen_at
  FROM sensor_registry sr
  WHERE sr.active = true
)
SELECT
  sensor_id,
  type,
  zone,
  expected_interval_s,
  last_seen_at,
  EXTRACT(EPOCH FROM now() - last_seen_at)::integer AS seconds_since,
  CASE
    WHEN last_seen_at IS NULL THEN true
    WHEN EXTRACT(EPOCH FROM now() - last_seen_at) > (expected_interval_s * 2) THEN true
    ELSE false
  END AS is_stale,
  CASE
    WHEN last_seen_at IS NULL THEN NULL
    ELSE ROUND((EXTRACT(EPOCH FROM now() - last_seen_at) / NULLIF(expected_interval_s, 0))::numeric, 1)
  END AS staleness_ratio
FROM last_readings;

COMMENT ON VIEW v_sensor_staleness IS 'Flags active sensors whose last reading exceeds 2x expected_interval_s. Scans last 2 hours for performance.';

-- ============================================================
-- PART B: v_system_health_score (component-based)
-- ============================================================

CREATE OR REPLACE VIEW v_system_health_score AS

-- Component 1: Sensor Health (% of active sensors reporting on time)
SELECT
  'sensor_health' AS component,
  ROUND(100.0 * COUNT(*) FILTER (WHERE NOT is_stale) / NULLIF(COUNT(*), 0), 1) AS score_pct,
  jsonb_build_object(
    'total_sensors', COUNT(*),
    'healthy', COUNT(*) FILTER (WHERE NOT is_stale),
    'stale', COUNT(*) FILTER (WHERE is_stale),
    'never_seen', COUNT(*) FILTER (WHERE last_seen_at IS NULL)
  ) AS details,
  now() AS checked_at
FROM v_sensor_staleness

UNION ALL

-- Component 2: Alert Load (penalty from open alerts, weighted by severity)
SELECT
  'alert_load',
  GREATEST(0, ROUND(100.0 - (
    COALESCE(SUM(CASE severity WHEN 'critical' THEN 10 WHEN 'warning' THEN 3 WHEN 'info' THEN 1 ELSE 0 END), 0)
  )::numeric, 1)),
  jsonb_build_object(
    'open_total', COUNT(*),
    'critical', COUNT(*) FILTER (WHERE severity = 'critical'),
    'warning', COUNT(*) FILTER (WHERE severity = 'warning'),
    'info', COUNT(*) FILTER (WHERE severity = 'info')
  ),
  now()
FROM alert_log
WHERE disposition = 'open'

UNION ALL

-- Component 3: Equipment Health (from fn_equipment_health)
SELECT
  'equipment_health',
  fn_equipment_health()::numeric,
  jsonb_build_object('score', fn_equipment_health()),
  now()

UNION ALL

-- Component 4: Controller Connectivity (WiFi, uptime, heartbeat freshness)
SELECT
  'controller',
  ROUND(CASE
    -- No data in 10 min = 0
    WHEN d.ts IS NULL THEN 0
    -- Score: 40pts for heartbeat recency + 30pts for WiFi + 30pts for uptime
    ELSE LEAST(100, (
      -- Heartbeat: 40 pts if < 2 min, linear decay to 0 at 10 min
      GREATEST(0, 40 - (EXTRACT(EPOCH FROM now() - d.ts) / 15.0))
      -- WiFi: 30 pts if > -50 dBm, 0 if < -80 dBm
      + LEAST(30, GREATEST(0, (d.wifi_rssi + 80) * 1.0))
      -- Uptime: 30 pts if > 1 hour, linear ramp
      + LEAST(30, d.uptime_s / 120.0)
    ))
  END::numeric, 1),
  jsonb_build_object(
    'last_heartbeat', d.ts,
    'wifi_rssi_dbm', d.wifi_rssi,
    'uptime_s', d.uptime_s,
    'heap_bytes', d.heap_bytes
  ),
  now()
FROM (
  SELECT ts, wifi_rssi, uptime_s, heap_bytes
  FROM diagnostics
  WHERE ts > now() - interval '10 minutes'
  ORDER BY ts DESC LIMIT 1
) d;

COMMENT ON VIEW v_system_health_score IS 'Component-based system health. 4 components: sensor_health, alert_load, equipment_health, controller. Each scored 0-100 with JSONB details.';

-- ============================================================
-- fn_system_health() — composite 0-100 score
-- ============================================================

CREATE OR REPLACE FUNCTION fn_system_health()
RETURNS INTEGER AS $$
  SELECT ROUND(
    -- Weighted: 30% sensor, 25% alerts, 20% equipment, 25% controller
    COALESCE((SELECT score_pct FROM v_system_health_score WHERE component = 'sensor_health'), 0) * 0.30
    + COALESCE((SELECT score_pct FROM v_system_health_score WHERE component = 'alert_load'), 0) * 0.25
    + COALESCE((SELECT score_pct FROM v_system_health_score WHERE component = 'equipment_health'), 0) * 0.20
    + COALESCE((SELECT score_pct FROM v_system_health_score WHERE component = 'controller'), 0) * 0.25
  )::integer;
$$ LANGUAGE sql STABLE;

COMMENT ON FUNCTION fn_system_health() IS 'Composite 0-100 health score. Weights: sensor 30%, alerts 25%, equipment 20%, controller 25%.';

-- ============================================================
-- Rebuild v_iris_planning_context (depends on v_system_health_score)
-- ============================================================

CREATE OR REPLACE VIEW v_iris_planning_context AS
SELECT
  now() AS query_ts,
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
  (SELECT json_object_agg(parameter, value)
   FROM (SELECT DISTINCT ON (parameter) parameter, value FROM setpoint_changes ORDER BY parameter, ts DESC) sub
  ) AS current_setpoints,
  (SELECT json_agg(row_to_json(sub) ORDER BY sub.ts)
   FROM (
     SELECT ts, parameter, value, reason
     FROM setpoint_plan WHERE ts > now() AND parameter != 'plan_metadata'
     ORDER BY ts
   ) sub
  ) AS active_plan,
  (SELECT json_build_object(
    'composite_score', fn_system_health(),
    'components', (SELECT json_agg(json_build_object('component', component, 'score', score_pct, 'details', details)) FROM v_system_health_score)
  )) AS system_health,
  (SELECT json_agg(row_to_json(sub) ORDER BY sub.date)
   FROM (
     SELECT date, cost_total, cost_electric, cost_gas, cost_water, kwh_estimated, water_used_gal
     FROM daily_summary WHERE date >= CURRENT_DATE - 7 ORDER BY date
   ) sub
  ) AS cost_trend_7d;

COMMENT ON VIEW v_iris_planning_context IS 'Single-query planning context for Iris. Returns current conditions, yesterday summary, 48h forecast, setpoints, active plan, health score, and 7-day cost trend as JSON columns.';
