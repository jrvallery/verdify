-- Migration 021: Create sensor_registry table
-- Universal prerequisite for staleness detection, alerting, ops dashboard (E-OPS-01)

CREATE TABLE IF NOT EXISTS sensor_registry (
    sensor_id           TEXT PRIMARY KEY,
    entity_id           TEXT,
    type                TEXT NOT NULL,
    zone                TEXT,
    position            TEXT,
    source_table        TEXT NOT NULL,
    source_column       TEXT,
    unit                TEXT,
    expected_interval_s INT NOT NULL,
    active              BOOLEAN DEFAULT true,
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sensor_registry_type ON sensor_registry(type);
CREATE INDEX IF NOT EXISTS idx_sensor_registry_active ON sensor_registry(active);
