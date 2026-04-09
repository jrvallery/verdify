-- Migration 032: Create irrigation_schedule + irrigation_log tables
-- Epic: E-IRR-02 (Irrigation Scheduling & Tracking)

-- ============================================================
-- Table 1: irrigation_schedule — programmed irrigation schedules
-- ============================================================
CREATE TABLE IF NOT EXISTS irrigation_schedule (
    id          SERIAL PRIMARY KEY,
    zone        TEXT NOT NULL CHECK (zone IN ('south_wall', 'west_wall', 'center', 'east_hydro')),
    start_time  TIME NOT NULL,
    duration_s  INTEGER NOT NULL CHECK (duration_s > 0 AND duration_s <= 3600),
    days_of_week INTEGER[] NOT NULL,
    enabled     BOOLEAN NOT NULL DEFAULT true,
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_irrigation_schedule_zone ON irrigation_schedule (zone);
CREATE TRIGGER trg_irrigation_schedule_updated_at BEFORE UPDATE ON irrigation_schedule
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE irrigation_schedule IS 'Programmed irrigation schedules per zone. days_of_week uses 0=Sun..6=Sat. Duration in seconds (max 1 hour).';

-- ============================================================
-- Table 2: irrigation_log — actual irrigation events (hypertable)
-- ============================================================
CREATE TABLE IF NOT EXISTS irrigation_log (
    id              SERIAL,
    ts              TIMESTAMPTZ NOT NULL,
    zone            TEXT NOT NULL CHECK (zone IN ('south_wall', 'west_wall', 'center', 'east_hydro')),
    schedule_id     INTEGER REFERENCES irrigation_schedule(id) ON DELETE SET NULL,
    scheduled_time  TIME,
    actual_start    TIMESTAMPTZ NOT NULL,
    actual_end      TIMESTAMPTZ,
    volume_gal      NUMERIC(8,2),
    source          TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'scheduled', 'override')),
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

SELECT create_hypertable('irrigation_log', 'ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_irrigation_log_zone ON irrigation_log (zone, ts DESC);
CREATE INDEX IF NOT EXISTS idx_irrigation_log_schedule ON irrigation_log (schedule_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_irrigation_log_ts ON irrigation_log (ts DESC);

COMMENT ON TABLE irrigation_log IS 'Actual irrigation events. Linked to schedule when triggered by automation, NULL schedule_id for manual runs. Hypertable partitioned on ts.';

-- ============================================================
-- View: duration computed from actual_start/actual_end
-- (Generated columns not supported on hypertable partition columns)
-- ============================================================
CREATE OR REPLACE VIEW v_irrigation_log AS
SELECT *,
    CASE WHEN actual_end IS NOT NULL THEN
        EXTRACT(EPOCH FROM (actual_end - actual_start))::INTEGER
    END AS duration_s
FROM irrigation_log;

COMMENT ON VIEW v_irrigation_log IS 'Irrigation log with computed duration_s from actual_start/actual_end.';

-- ============================================================
-- Seed data: current wall irrigation schedules
-- ============================================================
INSERT INTO irrigation_schedule (zone, start_time, duration_s, days_of_week, enabled, notes) VALUES
    ('south_wall', '06:00', 600, '{0,1,2,3,4,5,6}', true, 'Daily wall drip — south wall zone'),
    ('west_wall',  '06:00', 600, '{0,1,2,3,4,5,6}', true, 'Daily wall drip — west wall zone')
ON CONFLICT DO NOTHING;
