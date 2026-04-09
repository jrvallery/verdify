-- Migration 043: Fix v_water_daily phantom zeros + build v_indoor_outdoor_correlation

-- ============================================================
-- 1. Fix v_water_daily — filter phantom zero readings
-- ============================================================

CREATE OR REPLACE VIEW v_water_daily AS
SELECT
  date_trunc('day', ts) AS day,
  max(water_total_gal) - min(water_total_gal) AS used_gal
FROM climate
WHERE water_total_gal IS NOT NULL
AND water_total_gal > 0  -- exclude phantom zeros from counter resets
GROUP BY date_trunc('day', ts)
ORDER BY date_trunc('day', ts) DESC;

COMMENT ON VIEW v_water_daily IS 'Daily water usage from cumulative pulse counter. Filters phantom zeros to prevent inflated readings.';

-- ============================================================
-- 2. v_indoor_outdoor_correlation — hourly thermal model
-- ============================================================

CREATE OR REPLACE VIEW v_indoor_outdoor_correlation AS
SELECT
  time_bucket('1 hour', ts) AS hour,
  ROUND(AVG(temp_avg)::numeric, 1) AS indoor_temp,
  ROUND(AVG(outdoor_temp_f)::numeric, 1) AS outdoor_temp,
  ROUND((AVG(temp_avg) - AVG(outdoor_temp_f))::numeric, 1) AS thermal_gain,
  ROUND(AVG(solar_irradiance_w_m2)::numeric, 0) AS solar_w_m2,
  ROUND(AVG(vpd_avg)::numeric, 2) AS indoor_vpd,
  ROUND(AVG(outdoor_rh_pct)::numeric, 0) AS outdoor_rh,
  ROUND(AVG(wind_speed_mph)::numeric, 1) AS wind_mph,
  -- Thermal model: gain per unit solar radiation
  CASE WHEN AVG(solar_irradiance_w_m2) > 50
    THEN ROUND(((AVG(temp_avg) - AVG(outdoor_temp_f)) / NULLIF(AVG(solar_irradiance_w_m2), 0) * 100)::numeric, 2)
  END AS gain_per_100w,
  count(*) AS samples
FROM climate
WHERE temp_avg IS NOT NULL AND outdoor_temp_f IS NOT NULL
GROUP BY time_bucket('1 hour', ts)
ORDER BY hour DESC;

COMMENT ON VIEW v_indoor_outdoor_correlation IS 'Hourly indoor vs outdoor temperature correlation. thermal_gain = indoor - outdoor. gain_per_100w = thermal gain coefficient per 100 W/m² solar load.';

-- ============================================================
-- 3. Index for v_plan_compliance performance (climate ts lookups)
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_climate_ts_temp_avg ON climate (ts) WHERE temp_avg IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_climate_ts_vpd_avg ON climate (ts) WHERE vpd_avg IS NOT NULL;
