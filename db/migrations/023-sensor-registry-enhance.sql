-- Migration 023: Enhance sensor_registry to match Iris's Task 1.13 spec
-- Adds: description, installed_date, updated_at + auto-trigger, zone index, CHECK constraint

-- Add missing columns
ALTER TABLE sensor_registry ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE sensor_registry ADD COLUMN IF NOT EXISTS installed_date DATE;
ALTER TABLE sensor_registry ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Add CHECK constraint
ALTER TABLE sensor_registry DROP CONSTRAINT IF EXISTS chk_interval_positive;
ALTER TABLE sensor_registry ADD CONSTRAINT chk_interval_positive CHECK (expected_interval_s > 0);

-- Add zone index
CREATE INDEX IF NOT EXISTS idx_sensor_registry_zone ON sensor_registry(zone);

-- Auto-update updated_at on row change
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sensor_registry_updated_at ON sensor_registry;
CREATE TRIGGER trg_sensor_registry_updated_at
    BEFORE UPDATE ON sensor_registry
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
