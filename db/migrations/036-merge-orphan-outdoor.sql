-- Migration 036: Merge orphan outdoor rows into ESP32 rows + delete Open-Meteo orphans
--
-- Problem: tempest-sync.py and outdoor-weather-sync.py created separate climate rows
-- containing only outdoor data. These orphan rows cause oscillation on dashboards.
--
-- Fix: Merge outdoor columns from Tempest orphan rows into nearest ESP32 row (within 5 min),
-- then delete all orphan rows. The weather_station table retains full Tempest history.
--
-- Run in stages to avoid long-running transactions on hypertable.

-- Stage 1: Delete pure Open-Meteo orphans (no wind data = Open-Meteo, not Tempest)
-- ~524 rows
DELETE FROM climate
WHERE outdoor_temp_f IS NOT NULL
AND temp_avg IS NULL
AND wind_speed_mph IS NULL;

-- Stage 2: Merge Tempest orphan rows into nearest ESP32 row
-- For each Tempest-only row, UPDATE the closest ESP32 row within 5 minutes
-- This is done via a CTE + lateral join for efficiency
WITH orphans AS (
  SELECT ctid AS orphan_ctid, ts AS orphan_ts,
    outdoor_temp_f, outdoor_rh_pct, wind_speed_mph, wind_direction_deg,
    outdoor_lux, solar_irradiance_w_m2, pressure_hpa, uv_index,
    wind_gust_mph, wind_lull_mph, wind_speed_avg_mph, wind_direction_avg_deg,
    feels_like_f, wet_bulb_temp_f, vapor_pressure_inhg, air_density_kg_m3,
    precip_in, precip_intensity_in_h, lightning_count, lightning_avg_dist_mi
  FROM climate
  WHERE temp_avg IS NULL AND wind_speed_mph IS NOT NULL
),
matched AS (
  SELECT o.*,
    (SELECT e.ts FROM climate e
     WHERE e.temp_avg IS NOT NULL
     AND e.ts BETWEEN o.orphan_ts - interval '5 minutes' AND o.orphan_ts + interval '5 minutes'
     ORDER BY ABS(EXTRACT(EPOCH FROM e.ts - o.orphan_ts))
     LIMIT 1
    ) AS target_ts
  FROM orphans o
)
UPDATE climate c SET
  outdoor_temp_f = COALESCE(c.outdoor_temp_f, m.outdoor_temp_f),
  outdoor_rh_pct = COALESCE(c.outdoor_rh_pct, m.outdoor_rh_pct),
  wind_speed_mph = COALESCE(c.wind_speed_mph, m.wind_speed_mph),
  wind_direction_deg = COALESCE(c.wind_direction_deg, m.wind_direction_deg),
  outdoor_lux = COALESCE(c.outdoor_lux, m.outdoor_lux),
  solar_irradiance_w_m2 = COALESCE(c.solar_irradiance_w_m2, m.solar_irradiance_w_m2),
  pressure_hpa = COALESCE(c.pressure_hpa, m.pressure_hpa),
  uv_index = COALESCE(c.uv_index, m.uv_index),
  wind_gust_mph = COALESCE(c.wind_gust_mph, m.wind_gust_mph),
  wind_lull_mph = COALESCE(c.wind_lull_mph, m.wind_lull_mph),
  wind_speed_avg_mph = COALESCE(c.wind_speed_avg_mph, m.wind_speed_avg_mph),
  wind_direction_avg_deg = COALESCE(c.wind_direction_avg_deg, m.wind_direction_avg_deg),
  feels_like_f = COALESCE(c.feels_like_f, m.feels_like_f),
  wet_bulb_temp_f = COALESCE(c.wet_bulb_temp_f, m.wet_bulb_temp_f),
  vapor_pressure_inhg = COALESCE(c.vapor_pressure_inhg, m.vapor_pressure_inhg),
  air_density_kg_m3 = COALESCE(c.air_density_kg_m3, m.air_density_kg_m3),
  precip_in = COALESCE(c.precip_in, m.precip_in),
  precip_intensity_in_h = COALESCE(c.precip_intensity_in_h, m.precip_intensity_in_h),
  lightning_count = COALESCE(c.lightning_count, m.lightning_count),
  lightning_avg_dist_mi = COALESCE(c.lightning_avg_dist_mi, m.lightning_avg_dist_mi)
FROM matched m
WHERE c.ts = m.target_ts AND m.target_ts IS NOT NULL;

-- Stage 3: Delete all remaining orphan outdoor rows (merged or unmatched)
DELETE FROM climate WHERE temp_avg IS NULL AND outdoor_temp_f IS NOT NULL;
