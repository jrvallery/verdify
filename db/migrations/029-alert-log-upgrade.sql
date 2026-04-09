-- Migration 029: Upgrade alert_log to match full spec
-- Adds: category, metric_value, threshold_value, notes
-- Renames: status → disposition, adds false_positive
-- Updates: severity 'warn' → 'warning', id to BIGSERIAL

-- Step 1: Add missing columns
ALTER TABLE alert_log ADD COLUMN IF NOT EXISTS category TEXT;
ALTER TABLE alert_log ADD COLUMN IF NOT EXISTS metric_value DOUBLE PRECISION;
ALTER TABLE alert_log ADD COLUMN IF NOT EXISTS threshold_value DOUBLE PRECISION;
ALTER TABLE alert_log ADD COLUMN IF NOT EXISTS notes TEXT;

-- Step 2: Rename status → disposition
ALTER TABLE alert_log RENAME COLUMN status TO disposition;

-- Step 3: Update existing severity values (warn → warning)
UPDATE alert_log SET severity = 'warning' WHERE severity = 'warn';

-- Step 4: Drop old constraints and recreate with new values
ALTER TABLE alert_log DROP CONSTRAINT IF EXISTS chk_alert_severity;
ALTER TABLE alert_log DROP CONSTRAINT IF EXISTS chk_alert_status;
ALTER TABLE alert_log ADD CONSTRAINT chk_alert_severity
    CHECK (severity IN ('info', 'warning', 'critical'));
ALTER TABLE alert_log ADD CONSTRAINT chk_alert_disposition
    CHECK (disposition IN ('open', 'acknowledged', 'resolved', 'false_positive', 'suppressed'));

-- Step 5: Set category NOT NULL with default, then backfill existing rows
UPDATE alert_log SET category = 'sensor' WHERE category IS NULL AND alert_type = 'sensor_offline';
UPDATE alert_log SET category = 'climate' WHERE category IS NULL AND alert_type IN ('vpd_stress', 'temp_safety');
UPDATE alert_log SET category = 'equipment' WHERE category IS NULL AND alert_type IN ('relay_stuck', 'leak_detected');
UPDATE alert_log SET category = 'system' WHERE category IS NULL AND alert_type = 'esp32_reboot';
UPDATE alert_log SET category = 'system' WHERE category IS NULL;
ALTER TABLE alert_log ALTER COLUMN category SET NOT NULL;
ALTER TABLE alert_log ALTER COLUMN category SET DEFAULT 'system';

-- Step 6: Update severity default
ALTER TABLE alert_log ALTER COLUMN severity SET DEFAULT 'warning';

-- Step 7: Drop old indexes referencing 'status' and recreate for 'disposition'
DROP INDEX IF EXISTS idx_alert_log_open;
DROP INDEX IF EXISTS idx_alert_log_status;
CREATE INDEX idx_alert_log_open ON alert_log (disposition) WHERE disposition = 'open';
CREATE INDEX idx_alert_log_disposition ON alert_log (disposition, created_at DESC);
CREATE INDEX idx_alert_log_disposition_severity ON alert_log (disposition, severity);

-- Step 8: Add category and zone indexes
CREATE INDEX IF NOT EXISTS idx_alert_log_category ON alert_log (category, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_log_zone ON alert_log (zone, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_log_created ON alert_log (created_at DESC);

-- Step 9: Add FK reference to sensor_registry (soft — SET NULL on delete)
-- Don't add FK constraint since some sensor_ids may not be in registry (e.g., composite IDs)
-- The column already exists and is nullable
