-- Migration 026: Add solar position sensors to registry + update staleness view
-- Also fixes expected_interval_s for on-change (event-driven) sensors

-- Step 1: Add solar position computed columns to sensor_registry
INSERT INTO sensor_registry (sensor_id, type, source_table, source_column, unit, expected_interval_s, active, description)
VALUES
  ('climate.solar_altitude_deg', 'derived', 'climate', 'solar_altitude_deg', 'degrees', 120, true,
   'Sun angle above horizon (0=horizon, 90=zenith, negative=below). Computed via NOAA algorithm on INSERT trigger.'),
  ('climate.solar_azimuth_deg', 'derived', 'climate', 'solar_azimuth_deg', 'degrees', 120, true,
   'Sun compass bearing (0=N, 90=E, 180=S, 270=W). Computed via NOAA algorithm on INSERT trigger.')
ON CONFLICT (sensor_id) DO NOTHING;

-- Step 2: Fix expected_interval_s for event-driven equipment sensors
-- Equipment relays fire on-change only. A relay that hasn't changed in 6h
-- during daytime is NOT stale — it's stable. But 24h with no event IS a concern.
UPDATE sensor_registry SET expected_interval_s = 21600
WHERE source_table = 'equipment_state'
  AND expected_interval_s <= 600
  AND sensor_id NOT IN (
    'equipment.economiser_enabled', 'equipment.fog_closes_vent',
    'equipment.irrigation_enabled', 'equipment.irrigation_wall_enabled',
    'equipment.irrigation_center_enabled', 'equipment.irrigation_weather_skip'
  );

-- Step 3: Fix expected_interval_s for event-driven system_state sensors
-- System state transitions are also on-change. greenhouse_state can go hours
-- without a transition when the greenhouse is stable.
UPDATE sensor_registry SET expected_interval_s = 21600
WHERE source_table = 'system_state'
  AND expected_interval_s <= 600
  AND sensor_id IN (
    'state.greenhouse_state', 'state.last_transition', 'state.lead_fan',
    'state.mister_state', 'state.mister_zone'
  );

-- HA-sourced system_state: these SHOULD update every 5 min via ha-sensor-sync.
-- If they're stale, that indicates a sync problem (not a sensor problem).
-- Set to 1800s (30 min) — allows for occasional sync misses.
UPDATE sensor_registry SET expected_interval_s = 1800
WHERE source_table = 'system_state'
  AND sensor_id IN (
    'state.fan_state', 'state.heat_state', 'state.humidifan_state',
    'state.dashboard_status', 'state.fog_vpd_delta', 'state.grow_light_reason',
    'state.forecast_today'
  );

-- Step 4: Recreate v_sensor_staleness with solar columns added
CREATE OR REPLACE VIEW v_sensor_staleness AS
WITH last_seen_data AS (

  -- Climate sensors: each has a specific source_column
  SELECT
    sr.sensor_id,
    (SELECT MAX(c.ts) FROM climate c
     WHERE CASE sr.source_column
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
       WHEN 'wind_gust_mph' THEN c.wind_gust_mph
       WHEN 'wind_lull_mph' THEN c.wind_lull_mph
       WHEN 'wind_speed_avg_mph' THEN c.wind_speed_avg_mph
       WHEN 'wind_direction_avg_deg' THEN c.wind_direction_avg_deg
       WHEN 'outdoor_ppfd' THEN c.outdoor_ppfd
       WHEN 'solar_irradiance_w_m2' THEN c.solar_irradiance_w_m2
       WHEN 'solar_altitude_deg' THEN c.solar_altitude_deg
       WHEN 'solar_azimuth_deg' THEN c.solar_azimuth_deg
       WHEN 'pressure_hpa' THEN c.pressure_hpa
       WHEN 'feels_like_f' THEN c.feels_like_f
       WHEN 'wet_bulb_temp_f' THEN c.wet_bulb_temp_f
       WHEN 'vapor_pressure_inhg' THEN c.vapor_pressure_inhg
       WHEN 'air_density_kg_m3' THEN c.air_density_kg_m3
       WHEN 'precip_in' THEN c.precip_in
       WHEN 'precip_intensity_in_h' THEN c.precip_intensity_in_h
       WHEN 'uv_index' THEN c.uv_index
       WHEN 'lightning_count' THEN c.lightning_count::float
       WHEN 'lightning_avg_dist_mi' THEN c.lightning_avg_dist_mi
       WHEN 'hydro_tds_ppt' THEN c.hydro_tds_ppt
       WHEN 'hydro_water_temp_f' THEN c.hydro_water_temp_f
     END IS NOT NULL
     AND c.ts >= now() - interval '24 hours'
    ) AS last_seen
  FROM sensor_registry sr
  WHERE sr.active AND sr.source_table = 'climate' AND sr.source_column IS NOT NULL

  UNION ALL

  -- Equipment state sensors: keyed by equipment name
  SELECT
    sr.sensor_id,
    (SELECT MAX(es.ts) FROM equipment_state es
     WHERE es.equipment = REPLACE(sr.sensor_id, 'equipment.', '')
     AND es.ts >= now() - interval '24 hours'
    ) AS last_seen
  FROM sensor_registry sr
  WHERE sr.active AND sr.source_table = 'equipment_state'

  UNION ALL

  -- System state sensors: keyed by entity name
  SELECT
    sr.sensor_id,
    (SELECT MAX(ss.ts) FROM system_state ss
     WHERE ss.entity = REPLACE(sr.sensor_id, 'state.', '')
     AND ss.ts >= now() - interval '24 hours'
    ) AS last_seen
  FROM sensor_registry sr
  WHERE sr.active AND sr.source_table = 'system_state'

  UNION ALL

  -- Diagnostics numeric sensors
  SELECT
    sr.sensor_id,
    (SELECT MAX(d.ts) FROM diagnostics d
     WHERE CASE REPLACE(sr.sensor_id, 'diag.', '')
       WHEN 'wifi_rssi' THEN d.wifi_rssi
       WHEN 'heap_bytes' THEN d.heap_bytes
       WHEN 'uptime_s' THEN d.uptime_s
     END IS NOT NULL
     AND d.ts >= now() - interval '24 hours'
    ) AS last_seen
  FROM sensor_registry sr
  WHERE sr.active AND sr.source_table = 'diagnostics'
    AND sr.source_column IN ('wifi_rssi', 'heap_bytes', 'uptime_s')

  UNION ALL

  -- Diagnostics text sensors: use global MAX(ts)
  SELECT
    sr.sensor_id,
    (SELECT MAX(d.ts) FROM diagnostics d
     WHERE d.ts >= now() - interval '24 hours'
    ) AS last_seen
  FROM sensor_registry sr
  WHERE sr.active AND sr.source_table = 'diagnostics'
    AND sr.source_column IN ('probe_health', 'reset_reason')
)
SELECT
  ls.sensor_id,
  sr.type,
  sr.zone,
  sr.expected_interval_s,
  ls.last_seen,
  EXTRACT(EPOCH FROM (now() - ls.last_seen))::int AS age_seconds,
  CASE
    WHEN ls.last_seen IS NULL THEN true
    ELSE EXTRACT(EPOCH FROM (now() - ls.last_seen)) > (2 * sr.expected_interval_s)
  END AS stale,
  CASE
    WHEN ls.last_seen IS NULL THEN NULL
    ELSE ROUND((EXTRACT(EPOCH FROM (now() - ls.last_seen)) / sr.expected_interval_s)::numeric, 1)
  END AS staleness_ratio
FROM last_seen_data ls
JOIN sensor_registry sr ON sr.sensor_id = ls.sensor_id
ORDER BY
  CASE WHEN ls.last_seen IS NULL THEN 1 ELSE 0 END DESC,
  staleness_ratio DESC NULLS LAST;
