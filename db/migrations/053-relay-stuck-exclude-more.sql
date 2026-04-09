-- 053-relay-stuck-exclude-more.sql
-- Add gl_auto_mode and occupancy_inhibit to v_relay_stuck exclusion list.
-- These are config switches, not equipment relays.

-- Must drop + recreate (materialized view, not regular view)
-- First drop the refresh function that depends on it
DROP FUNCTION IF EXISTS refresh_relay_stuck();

DROP MATERIALIZED VIEW IF EXISTS v_relay_stuck;

CREATE MATERIALIZED VIEW v_relay_stuck AS
WITH latest_on AS (
    SELECT equipment, max(ts) AS last_on_ts
    FROM equipment_state
    WHERE state = true AND equipment NOT IN (
        'economiser_enabled', 'economiser_blocked', 'fog_closes_vent',
        'irrigation_enabled', 'irrigation_wall_enabled', 'irrigation_center_enabled',
        'irrigation_weather_skip', 'sntp_status', 'mister_budget_exceeded',
        'fan_burst_active', 'fog_burst_active', 'vent_bypass_active',
        'leak_detected', 'water_flowing', 'mister_any',
        'gl_auto_mode', 'occupancy_inhibit'
    )
    GROUP BY equipment
),
latest_off AS (
    SELECT equipment, max(ts) AS last_off_ts
    FROM equipment_state
    WHERE state = false
    GROUP BY equipment
),
stuck_check AS (
    SELECT lo.equipment, lo.last_on_ts, lf.last_off_ts,
        EXTRACT(epoch FROM now() - lo.last_on_ts) / 3600.0 AS hours_on,
        CASE lo.equipment
            WHEN 'heat1' THEN 3 WHEN 'heat2' THEN 3
            WHEN 'fan1' THEN 4 WHEN 'fan2' THEN 4
            WHEN 'fog' THEN 2 WHEN 'vent' THEN 6
            ELSE 8
        END AS threshold_hours
    FROM latest_on lo
    LEFT JOIN latest_off lf ON lo.equipment = lf.equipment
    WHERE lo.last_on_ts > COALESCE(lf.last_off_ts, '1970-01-01'::timestamptz)
)
SELECT equipment, last_on_ts, hours_on, threshold_hours,
    (hours_on > threshold_hours::numeric) AS is_stuck
FROM stuck_check;

-- Recreate the refresh function
CREATE OR REPLACE FUNCTION refresh_relay_stuck() RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW v_relay_stuck;
END;
$$ LANGUAGE plpgsql;
