-- Migration 028: Create dedicated weather_station table
-- Stores raw Tempest/Panorama observations separate from the climate table.
-- Climate table still receives outdoor columns for backward compat.

CREATE TABLE IF NOT EXISTS weather_station (
    ts              TIMESTAMPTZ NOT NULL,
    source          TEXT        NOT NULL DEFAULT 'tempest',
    temp_f          DOUBLE PRECISION,
    rh_pct          DOUBLE PRECISION,
    wind_speed_mph  DOUBLE PRECISION,
    wind_gust_mph   DOUBLE PRECISION,
    wind_lull_mph   DOUBLE PRECISION,
    wind_dir_deg    DOUBLE PRECISION,
    wind_speed_avg_mph DOUBLE PRECISION,
    wind_dir_avg_deg   DOUBLE PRECISION,
    pressure_hpa    DOUBLE PRECISION,
    solar_irradiance_w_m2 DOUBLE PRECISION,
    outdoor_lux     DOUBLE PRECISION,
    uv_index        DOUBLE PRECISION,
    precip_in       DOUBLE PRECISION,
    precip_intensity_in_h DOUBLE PRECISION,
    lightning_count INTEGER,
    lightning_avg_dist_mi DOUBLE PRECISION,
    feels_like_f    DOUBLE PRECISION,
    wet_bulb_temp_f DOUBLE PRECISION,
    dew_point_f     DOUBLE PRECISION,
    vapor_pressure_inhg DOUBLE PRECISION,
    air_density_kg_m3   DOUBLE PRECISION
);

-- Convert to hypertable
SELECT create_hypertable('weather_station', 'ts', if_not_exists => TRUE);

-- Index for fast time-range queries
CREATE INDEX IF NOT EXISTS idx_weather_station_ts ON weather_station (ts DESC);
CREATE INDEX IF NOT EXISTS idx_weather_station_source ON weather_station (source, ts DESC);

COMMENT ON TABLE weather_station IS 'Raw weather station observations. Primary source: Tempest/Panorama via HA API.';
