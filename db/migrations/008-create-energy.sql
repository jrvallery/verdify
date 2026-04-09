-- Migration 008: Create energy hypertable (P1)
-- High-frequency energy monitoring from CT clamp or smart meter.

CREATE TABLE IF NOT EXISTS energy (
    ts            TIMESTAMPTZ NOT NULL,
    watts_total   FLOAT,
    watts_heat    FLOAT,
    watts_fans    FLOAT,
    watts_other   FLOAT,
    kwh_today     FLOAT
);

SELECT create_hypertable('energy', 'ts', if_not_exists => TRUE);
