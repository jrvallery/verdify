-- 060-complete-state-sync.sql
-- Complete ESP32 ↔ DB state alignment
-- 1. setpoint_snapshot: periodic full capture of ESP32 configured values
-- 2. New climate columns for unmapped sensors
-- 3. New diagnostics columns for cfg readback sensors

-- Setpoint snapshot: full state capture every 60s
-- Stores the ESP32's ACTUAL configured values (cfg_* sensors), not what we pushed
CREATE TABLE IF NOT EXISTS setpoint_snapshot (
    ts TIMESTAMPTZ NOT NULL,
    parameter TEXT NOT NULL,
    value FLOAT NOT NULL
);
SELECT create_hypertable('setpoint_snapshot', 'ts', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_snapshot_param ON setpoint_snapshot (parameter, ts DESC);

-- Compression + retention
SELECT add_compression_policy('setpoint_snapshot', INTERVAL '7 days', if_not_exists => TRUE);
SELECT add_retention_policy('setpoint_snapshot', INTERVAL '90 days', if_not_exists => TRUE);

-- Climate: add unmapped sensor columns
ALTER TABLE climate ADD COLUMN IF NOT EXISTS intake_rh DOUBLE PRECISION;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS intake_vpd DOUBLE PRECISION;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS outdoor_illuminance DOUBLE PRECISION;
