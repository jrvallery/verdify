-- Migration 025: Create alert_log table (E-OWN-03)
-- Tracks alert lifecycle: raised → acknowledged → resolved
-- Used by alerting pipeline (Sprint 3.4) and ops dashboard

CREATE TABLE IF NOT EXISTS alert_log (
    id              SERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    alert_type      TEXT NOT NULL,          -- 'sensor_offline', 'relay_stuck', 'vpd_stress', 'temp_safety', 'disease_risk', 'budget_exceeded', 'reboot'
    severity        TEXT NOT NULL DEFAULT 'warn',  -- 'info', 'warn', 'critical'
    sensor_id       TEXT,                   -- FK-like reference to sensor_registry.sensor_id (nullable for system-wide alerts)
    zone            TEXT,                   -- affected zone (nullable)
    message         TEXT NOT NULL,          -- human-readable alert text
    details         JSONB,                  -- structured metadata (thresholds, actual values, etc.)
    source          TEXT DEFAULT 'system',  -- 'system', 'agent', 'manual'
    status          TEXT NOT NULL DEFAULT 'open',  -- 'open', 'acknowledged', 'resolved', 'suppressed'
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by TEXT,
    resolved_at     TIMESTAMPTZ,
    resolved_by     TEXT,
    resolution      TEXT,                   -- how it was resolved
    slack_ts        TEXT,                   -- Slack message timestamp for threading
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_alert_log_status ON alert_log(status, ts DESC);
CREATE INDEX IF NOT EXISTS idx_alert_log_type ON alert_log(alert_type, ts DESC);
CREATE INDEX IF NOT EXISTS idx_alert_log_sensor ON alert_log(sensor_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_alert_log_severity ON alert_log(severity, ts DESC);
CREATE INDEX IF NOT EXISTS idx_alert_log_open ON alert_log(status) WHERE status = 'open';

-- CHECK constraints
ALTER TABLE alert_log ADD CONSTRAINT chk_alert_severity
    CHECK (severity IN ('info', 'warn', 'critical'));
ALTER TABLE alert_log ADD CONSTRAINT chk_alert_status
    CHECK (status IN ('open', 'acknowledged', 'resolved', 'suppressed'));

-- Auto-update updated_at trigger (reuse the function from migration 023)
DROP TRIGGER IF EXISTS trg_alert_log_updated_at ON alert_log;
CREATE TRIGGER trg_alert_log_updated_at
    BEFORE UPDATE ON alert_log
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
