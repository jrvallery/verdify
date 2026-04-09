-- Migration 017: Add columns for Tempest weather station + hydroponic water tester
-- Panorama/Tempest: solar irradiance, precipitation, UV index
-- YINMIK: hydroponic TDS and water temperature

ALTER TABLE climate ADD COLUMN IF NOT EXISTS solar_irradiance_w_m2 FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS precip_in             FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS uv_index              FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS hydro_tds_ppt         FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS hydro_water_temp_f    FLOAT;
