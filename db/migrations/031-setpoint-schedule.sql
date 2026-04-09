-- Migration 031: Create setpoint_schedule table
-- Epic: E-HVAC-02 — Time-of-day setpoint profiles for compliance calculation

CREATE TABLE IF NOT EXISTS setpoint_schedule (
    zone            TEXT NOT NULL,
    hour_of_day     INT NOT NULL CHECK (hour_of_day >= 0 AND hour_of_day <= 23),
    season          TEXT NOT NULL CHECK (season IN ('spring', 'summer', 'fall', 'winter')),
    temp_target_f   NUMERIC(5,1),
    humidity_target_pct NUMERIC(5,1),
    vpd_target_kpa  NUMERIC(4,2),
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (zone, hour_of_day, season)
);

CREATE INDEX IF NOT EXISTS idx_setpoint_schedule_season ON setpoint_schedule (season, hour_of_day);
CREATE TRIGGER trg_setpoint_schedule_updated_at BEFORE UPDATE ON setpoint_schedule
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE setpoint_schedule IS 'Time-of-day setpoint profiles per zone and season. Used by v_setpoint_compliance to compare actual vs planned climate.';

-- Populate spring profiles for all 6 zones
-- Day (7-19): 72°F / 55% RH / 1.2 kPa VPD
-- Night (20-6): 60°F / 60% RH / 0.95 kPa VPD
-- Transitions (6-7, 19-20): interpolated

INSERT INTO setpoint_schedule (zone, hour_of_day, season, temp_target_f, humidity_target_pct, vpd_target_kpa, notes)
SELECT zone, hour, 'spring', temp, rh, vpd, note
FROM (VALUES
    (0,  60.0, 60.0, 0.95, 'night'),
    (1,  60.0, 60.0, 0.95, 'night'),
    (2,  60.0, 60.0, 0.95, 'night'),
    (3,  60.0, 60.0, 0.95, 'night'),
    (4,  60.0, 60.0, 0.95, 'night'),
    (5,  60.0, 60.0, 0.95, 'night'),
    (6,  64.0, 58.0, 1.04, 'dawn transition'),
    (7,  68.0, 56.0, 1.12, 'morning ramp'),
    (8,  72.0, 55.0, 1.20, 'day'),
    (9,  72.0, 55.0, 1.20, 'day'),
    (10, 72.0, 55.0, 1.20, 'day'),
    (11, 72.0, 55.0, 1.20, 'day'),
    (12, 72.0, 55.0, 1.20, 'day'),
    (13, 72.0, 55.0, 1.20, 'day'),
    (14, 72.0, 55.0, 1.20, 'day'),
    (15, 72.0, 55.0, 1.20, 'day'),
    (16, 72.0, 55.0, 1.20, 'day'),
    (17, 72.0, 55.0, 1.20, 'day'),
    (18, 72.0, 55.0, 1.20, 'day'),
    (19, 68.0, 56.0, 1.12, 'dusk transition'),
    (20, 64.0, 58.0, 1.04, 'evening ramp-down'),
    (21, 60.0, 60.0, 0.95, 'night'),
    (22, 60.0, 60.0, 0.95, 'night'),
    (23, 60.0, 60.0, 0.95, 'night')
) AS v(hour, temp, rh, vpd, note)
CROSS JOIN (VALUES ('north'),('south'),('east'),('west'),('center'),('case')) AS z(zone)
ON CONFLICT DO NOTHING;
