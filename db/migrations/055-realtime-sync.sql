-- 055-realtime-sync.sql
-- Real-time setpoint push via PostgreSQL LISTEN/NOTIFY
-- + data_gaps table for outage tracking and backfill

-- Notify on every setpoint_changes INSERT so ingestor can push to ESP32 in real-time
CREATE OR REPLACE FUNCTION notify_setpoint_change() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('setpoint_changed', NEW.parameter || '=' || NEW.value::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_setpoint_notify
    AFTER INSERT ON setpoint_changes
    FOR EACH ROW EXECUTE FUNCTION notify_setpoint_change();

-- Track data gaps for outage recovery
CREATE TABLE IF NOT EXISTS data_gaps (
    id SERIAL PRIMARY KEY,
    start_ts TIMESTAMPTZ NOT NULL,
    end_ts TIMESTAMPTZ NOT NULL,
    duration_s FLOAT NOT NULL,
    reason TEXT DEFAULT 'ingestor_restart',
    backfill_status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT now()
);
