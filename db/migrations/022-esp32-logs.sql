-- Migration 022: ESP32 log capture table
-- Stores all ESP32 log messages for tracing reboots, state transitions, probe failures

CREATE TABLE IF NOT EXISTS esp32_logs (
    ts      TIMESTAMPTZ NOT NULL,
    level   TEXT NOT NULL,       -- DEBUG, INFO, WARN, ERROR
    tag     TEXT,                -- 'ctl', 'modbus', 'sntp', 'watchdog', 'lambda'
    message TEXT NOT NULL
);

SELECT create_hypertable('esp32_logs', 'ts', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_esp32_logs_level ON esp32_logs (level, ts DESC);
CREATE INDEX IF NOT EXISTS idx_esp32_logs_tag ON esp32_logs (tag, ts DESC);
