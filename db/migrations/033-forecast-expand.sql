-- Migration 033: Expand weather_forecast with full Open-Meteo parameters
-- From 7 params / 3 days → 25 params / 16 days

ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS dew_point_f DOUBLE PRECISION;
ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS feels_like_f DOUBLE PRECISION;
ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS vpd_kpa DOUBLE PRECISION;
ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS precip_in DOUBLE PRECISION;
ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS rain_in DOUBLE PRECISION;
ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS snow_in DOUBLE PRECISION;
ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS wind_gust_mph DOUBLE PRECISION;
ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS uv_index DOUBLE PRECISION;
ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS et0_mm DOUBLE PRECISION;
ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS direct_radiation_w_m2 DOUBLE PRECISION;
ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS diffuse_radiation_w_m2 DOUBLE PRECISION;
ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS sunshine_duration_s DOUBLE PRECISION;
ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS weather_code INTEGER;
ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS cloud_cover_low_pct DOUBLE PRECISION;
ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS cloud_cover_high_pct DOUBLE PRECISION;
ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS surface_pressure_hpa DOUBLE PRECISION;
ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS soil_temp_f DOUBLE PRECISION;
ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS visibility_m DOUBLE PRECISION;

COMMENT ON TABLE weather_forecast IS 'Open-Meteo hourly forecast. 16-day horizon, 1km local resolution blending to 11km global. 25 parameters covering temperature, humidity, VPD, precipitation, radiation, wind, soil, and visibility.';
