-- Migration 049: Operator experience views (Iris friction points)
-- 7 new views for daily greenhouse operations

-- ============================================================
-- 1. v_greenhouse_now — Single-row current snapshot
-- ============================================================

CREATE OR REPLACE VIEW v_greenhouse_now AS
SELECT
  c.ts,
  -- Indoor climate
  ROUND(c.temp_avg::numeric, 1) AS temp_avg,
  ROUND(c.temp_north::numeric, 1) AS temp_north,
  ROUND(c.temp_south::numeric, 1) AS temp_south,
  ROUND(c.temp_east::numeric, 1) AS temp_east,
  ROUND(c.temp_west::numeric, 1) AS temp_west,
  ROUND(c.rh_avg::numeric, 1) AS rh_avg,
  ROUND(c.vpd_avg::numeric, 2) AS vpd_avg,
  ROUND(c.vpd_control::numeric, 2) AS vpd_control,
  ROUND(c.co2_ppm::numeric, 0) AS co2_ppm,
  ROUND(c.lux::numeric, 0) AS lux,
  ROUND(c.dli_today::numeric, 2) AS dli_today,
  -- Outdoor
  ROUND(c.outdoor_temp_f::numeric, 1) AS outdoor_temp_f,
  ROUND(c.outdoor_rh_pct::numeric, 0) AS outdoor_rh_pct,
  ROUND(c.wind_speed_mph::numeric, 1) AS wind_mph,
  ROUND(c.pressure_hpa::numeric, 1) AS pressure_hpa,
  -- Water
  ROUND(c.flow_gpm::numeric, 2) AS flow_gpm,
  ROUND(c.water_total_gal::numeric, 0) AS water_total_gal,
  ROUND(c.mister_water_today::numeric, 1) AS mister_water_today,
  -- Hydro
  c.hydro_ph, c.hydro_ec_us_cm, c.hydro_tds_ppm, c.hydro_water_temp_f,
  -- ESP32 diagnostics
  d.wifi_rssi, ROUND(d.heap_bytes::numeric, 0) AS heap_kb, ROUND(d.uptime_s::numeric, 0) AS uptime_s,
  -- State machine
  (SELECT value FROM system_state WHERE entity = 'greenhouse_state' ORDER BY ts DESC LIMIT 1) AS state,
  (SELECT value FROM system_state WHERE entity = 'lead_fan' ORDER BY ts DESC LIMIT 1) AS lead_fan,
  -- System health
  fn_system_health() AS health_score,
  (SELECT count(*) FROM alert_log WHERE disposition = 'open') AS open_alerts
FROM climate c
LEFT JOIN LATERAL (SELECT wifi_rssi, heap_bytes, uptime_s FROM diagnostics ORDER BY ts DESC LIMIT 1) d ON true
WHERE c.temp_avg IS NOT NULL
ORDER BY c.ts DESC LIMIT 1;

COMMENT ON VIEW v_greenhouse_now IS 'Single-row current snapshot: climate, zones, outdoor, hydro, ESP32 diagnostics, state machine, health. Iris queries this 10x/day.';

-- ============================================================
-- 2. v_state_durations — Time-in-state per day (30 days)
-- ============================================================

CREATE OR REPLACE VIEW v_state_durations AS
WITH transitions AS (
  SELECT ts, value AS state,
    LEAD(ts) OVER (ORDER BY ts) AS next_ts
  FROM system_state
  WHERE entity = 'greenhouse_state' AND ts > now() - interval '30 days'
)
SELECT
  ts::date AS date,
  state,
  ROUND(SUM(EXTRACT(EPOCH FROM COALESCE(next_ts, now()) - ts) / 3600)::numeric, 2) AS hours,
  count(*) AS transitions
FROM transitions
GROUP BY ts::date, state
ORDER BY ts::date DESC, hours DESC;

COMMENT ON VIEW v_state_durations IS 'Hours spent in each state per day. Feeds plan accuracy: predicted vs actual time in COOL/HEAT/HUMID states.';

-- ============================================================
-- 3. v_mister_effectiveness — VPD delta per misting cycle
-- ============================================================

CREATE OR REPLACE VIEW v_mister_effectiveness AS
WITH mister_events AS (
  SELECT ts, equipment, state,
    LEAD(ts) OVER (PARTITION BY equipment ORDER BY ts) AS next_ts,
    LEAD(state) OVER (PARTITION BY equipment ORDER BY ts) AS next_state
  FROM equipment_state
  WHERE equipment IN ('mister_south', 'mister_west', 'mister_center')
  AND ts > now() - interval '14 days'
),
mister_cycles AS (
  SELECT ts AS on_ts, equipment, next_ts AS off_ts,
    EXTRACT(EPOCH FROM next_ts - ts)::int AS duration_s
  FROM mister_events
  WHERE state = true AND next_state = false
  AND next_ts - ts < interval '30 minutes'
  AND next_ts - ts > interval '5 seconds'
)
SELECT
  mc.on_ts, mc.equipment, mc.duration_s,
  ROUND(vpd_before.vpd::numeric, 2) AS vpd_before,
  ROUND(vpd_after.vpd::numeric, 2) AS vpd_after,
  ROUND((vpd_before.vpd - vpd_after.vpd)::numeric, 2) AS vpd_delta
FROM mister_cycles mc
LEFT JOIN LATERAL (
  SELECT vpd_avg AS vpd FROM climate WHERE ts <= mc.on_ts AND vpd_avg IS NOT NULL ORDER BY ts DESC LIMIT 1
) vpd_before ON true
LEFT JOIN LATERAL (
  SELECT vpd_avg AS vpd FROM climate WHERE ts >= mc.off_ts AND vpd_avg IS NOT NULL ORDER BY ts LIMIT 1
) vpd_after ON true
ORDER BY mc.on_ts DESC;

COMMENT ON VIEW v_mister_effectiveness IS 'VPD before/after each misting cycle. vpd_delta = improvement per cycle. Key feedback loop for tuning pulse duration.';

-- ============================================================
-- 4. v_forecast_vs_actual — Hourly forecast accountability
-- ============================================================

CREATE OR REPLACE VIEW v_forecast_vs_actual AS
SELECT DISTINCT ON (f.ts)
  f.ts AS hour,
  ROUND(f.temp_f::numeric, 1) AS forecast_temp,
  ROUND(f.rh_pct::numeric, 0) AS forecast_rh,
  ROUND(f.vpd_kpa::numeric, 2) AS forecast_vpd,
  ROUND(f.solar_w_m2::numeric, 0) AS forecast_solar,
  ROUND(c.outdoor_temp::numeric, 1) AS actual_temp,
  ROUND(c.outdoor_rh::numeric, 0) AS actual_rh,
  ROUND(c.solar::numeric, 0) AS actual_solar,
  ROUND((f.temp_f - c.outdoor_temp)::numeric, 1) AS temp_error,
  ROUND((f.solar_w_m2 - c.solar)::numeric, 0) AS solar_error
FROM weather_forecast f
LEFT JOIN LATERAL (
  SELECT AVG(outdoor_temp_f) AS outdoor_temp, AVG(outdoor_rh_pct) AS outdoor_rh,
    AVG(solar_irradiance_w_m2) AS solar
  FROM climate
  WHERE ts >= f.ts AND ts < f.ts + interval '1 hour'
  AND outdoor_temp_f IS NOT NULL
) c ON true
WHERE f.ts < now() AND f.ts > now() - interval '7 days'
ORDER BY f.ts, f.fetched_at DESC;

COMMENT ON VIEW v_forecast_vs_actual IS 'Hourly Open-Meteo forecast vs actual outdoor conditions. temp_error/solar_error show systematic forecast bias.';

-- ============================================================
-- 5. v_cost_today — Real-time cost estimate
-- ============================================================

CREATE OR REPLACE VIEW v_cost_today AS
WITH today_start AS (
  SELECT date_trunc('day', now() AT TIME ZONE 'America/Denver') AT TIME ZONE 'America/Denver' AS ts
),
runtimes AS (
  SELECT e.equipment, ea.wattage,
    SUM(
      CASE WHEN e.state = true THEN
        EXTRACT(EPOCH FROM COALESCE(
          LEAD(e.ts) OVER (PARTITION BY e.equipment ORDER BY e.ts),
          now()
        ) - e.ts) / 3600
      ELSE 0 END
    ) AS hours_on
  FROM equipment_state e
  CROSS JOIN today_start t
  LEFT JOIN equipment_assets ea ON e.equipment = ea.equipment
  WHERE e.ts >= t.ts
  GROUP BY e.equipment, ea.wattage
)
SELECT
  ROUND(COALESCE(SUM(hours_on * COALESCE(wattage, 0) / 1000.0 * 0.105), 0)::numeric, 2) AS cost_electric,
  ROUND(COALESCE((
    SELECT (MAX(water_total_gal) - MIN(water_total_gal)) * 0.007
    FROM climate c, today_start t WHERE c.ts >= t.ts AND water_total_gal > 0
  ), 0)::numeric, 2) AS cost_water,
  ROUND((
    COALESCE(SUM(hours_on * COALESCE(wattage, 0) / 1000.0 * 0.105), 0)
    + COALESCE((SELECT (MAX(water_total_gal) - MIN(water_total_gal)) * 0.007
        FROM climate c, today_start t WHERE c.ts >= t.ts AND water_total_gal > 0), 0)
  )::numeric, 2) AS cost_total
FROM runtimes;

COMMENT ON VIEW v_cost_today IS 'Real-time cost estimate for today: electric (runtime x wattage x rate) + water (meter delta x rate).';

-- ============================================================
-- 6. v_hydro_status — Latest hydro readings with range flags
-- ============================================================

CREATE OR REPLACE VIEW v_hydro_status AS
SELECT
  c.ts,
  ROUND(c.hydro_ph::numeric, 1) AS ph,
  ROUND(c.hydro_ec_us_cm::numeric, 0) AS ec_us_cm,
  ROUND(c.hydro_tds_ppm::numeric, 0) AS tds_ppm,
  ROUND(c.hydro_orp_mv::numeric, 0) AS orp_mv,
  ROUND(c.hydro_water_temp_f::numeric, 1) AS water_temp_f,
  ROUND(c.hydro_battery_pct::numeric, 0) AS battery_pct,
  c.hydro_ph BETWEEN 5.5 AND 6.5 AS ph_in_range,
  c.hydro_ec_us_cm BETWEEN 800 AND 2000 AS ec_in_range,
  c.hydro_water_temp_f BETWEEN 60 AND 75 AS temp_in_range,
  c.hydro_battery_pct > 20 AS battery_ok
FROM climate c
WHERE c.hydro_ph IS NOT NULL
ORDER BY c.ts DESC LIMIT 1;

COMMENT ON VIEW v_hydro_status IS 'Latest hydroponic water quality: pH, EC, TDS, ORP, temp, battery. Boolean flags for out-of-range.';

-- ============================================================
-- 7. v_equipment_now — Current state of every relay
-- ============================================================

CREATE OR REPLACE VIEW v_equipment_now AS
SELECT DISTINCT ON (equipment)
  equipment,
  state,
  ts AS since,
  ROUND(EXTRACT(EPOCH FROM now() - ts)::numeric) AS seconds_ago
FROM equipment_state
ORDER BY equipment, ts DESC;

COMMENT ON VIEW v_equipment_now IS 'Current state of every equipment relay: ON/OFF, since when, how long ago.';

-- ============================================================
-- 8. Deprecate setpoint_schedule from compliance path
-- ============================================================

COMMENT ON TABLE setpoint_schedule IS 'DEPRECATED for compliance. Seasonal reference defaults only. Active compliance uses v_plan_compliance (plan-based, not schedule-based).';
