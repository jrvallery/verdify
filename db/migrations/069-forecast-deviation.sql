-- 069-forecast-deviation.sql
-- Forecast deviation detection: compare observed vs forecasted, trigger replan on miss

CREATE TABLE IF NOT EXISTS forecast_deviation_thresholds (
    parameter TEXT PRIMARY KEY,
    threshold FLOAT NOT NULL,
    unit TEXT NOT NULL,
    cooldown_min INT NOT NULL DEFAULT 30,
    enabled BOOLEAN NOT NULL DEFAULT true
);

INSERT INTO forecast_deviation_thresholds VALUES
    ('temp_f', 5.0, '°F', 30, true),
    ('rh_pct', 15.0, '%', 30, true),
    ('solar_w_m2', 200.0, 'W/m²', 60, true)
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS forecast_deviation_log (
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    parameter TEXT NOT NULL,
    observed FLOAT,
    forecasted FLOAT,
    delta FLOAT,
    threshold FLOAT,
    triggered BOOLEAN NOT NULL DEFAULT true
);
SELECT create_hypertable('forecast_deviation_log', 'ts', if_not_exists => TRUE);
