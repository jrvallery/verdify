-- Migration 018: Close data coverage gaps
-- New climate columns for extended Tempest weather data
-- New daily_summary columns for drip and grow light runtimes

-- Extended Tempest weather fields
ALTER TABLE climate ADD COLUMN IF NOT EXISTS wind_gust_mph          FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS wind_lull_mph          FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS wind_speed_avg_mph     FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS wind_direction_avg_deg FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS feels_like_f           FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS wet_bulb_temp_f        FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS vapor_pressure_inhg    FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS air_density_kg_m3      FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS precip_intensity_in_h  FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS lightning_count        INT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS lightning_avg_dist_mi  FLOAT;

-- Daily summary: drip runtimes + grow light
ALTER TABLE daily_summary ADD COLUMN IF NOT EXISTS runtime_drip_wall_h    FLOAT;
ALTER TABLE daily_summary ADD COLUMN IF NOT EXISTS runtime_drip_center_h  FLOAT;

-- Derived views for exterior VPD, light transmission, fog VPD delta
CREATE OR REPLACE VIEW v_exterior_vpd AS
SELECT ts,
  CASE WHEN outdoor_temp_f IS NOT NULL AND outdoor_rh_pct IS NOT NULL THEN
    ROUND((0.6108 * EXP(17.27 * ((outdoor_temp_f - 32) * 5.0/9.0) / (((outdoor_temp_f - 32) * 5.0/9.0) + 237.3))
      * (1 - outdoor_rh_pct / 100.0))::numeric, 3)
  END AS exterior_vpd_kpa
FROM climate
WHERE outdoor_temp_f IS NOT NULL;

CREATE OR REPLACE VIEW v_light_transmission AS
SELECT ts,
  CASE WHEN outdoor_ppfd > 0 AND lux IS NOT NULL THEN
    ROUND((lux / outdoor_ppfd * 100)::numeric, 1)
  END AS transmission_pct
FROM climate
WHERE outdoor_ppfd > 0 AND lux IS NOT NULL;
