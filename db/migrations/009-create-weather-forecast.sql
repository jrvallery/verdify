-- Migration 009: Create weather_forecast hypertable (P1)
-- 72-hour hourly forecast from Open-Meteo. Ingested every 6 hours.

CREATE TABLE IF NOT EXISTS weather_forecast (
    ts              TIMESTAMPTZ NOT NULL,
    fetched_at      TIMESTAMPTZ NOT NULL,
    temp_f          FLOAT,
    rh_pct          FLOAT,
    wind_speed_mph  FLOAT,
    wind_dir_deg    FLOAT,
    cloud_cover_pct FLOAT,
    precip_prob_pct FLOAT,
    solar_w_m2      FLOAT
);

SELECT create_hypertable('weather_forecast', 'ts', if_not_exists => TRUE);
