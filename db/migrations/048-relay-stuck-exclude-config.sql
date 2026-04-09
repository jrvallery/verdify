-- Migration 048: Exclude config switches from v_relay_stuck stuck detection
-- Problem: always-on config switches (economiser_enabled, irrigation_enabled, etc.)
-- falsely flag as "stuck" after 8h, dragging equipment_health to 20/100.

DROP MATERIALIZED VIEW IF EXISTS v_relay_stuck CASCADE;

CREATE MATERIALIZED VIEW v_relay_stuck AS
WITH latest_on AS (
    SELECT equipment, max(ts) AS last_on_ts
    FROM equipment_state
    WHERE state = true
    AND equipment NOT IN (
        -- Config switches: supposed to stay ON indefinitely
        'economiser_enabled', 'economiser_blocked',
        'fog_closes_vent',
        'irrigation_enabled', 'irrigation_wall_enabled',
        'irrigation_center_enabled', 'irrigation_weather_skip',
        -- Virtual/diagnostic: not physical relays
        'sntp_status', 'mister_budget_exceeded',
        'fan_burst_active', 'fog_burst_active', 'vent_bypass_active',
        'leak_detected', 'water_flowing', 'mister_any'
    )
    GROUP BY equipment
), latest_off AS (
    SELECT equipment, max(ts) AS last_off_ts
    FROM equipment_state
    WHERE state = false
    GROUP BY equipment
), stuck_check AS (
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
    hours_on > threshold_hours::numeric AS is_stuck
FROM stuck_check;

COMMENT ON MATERIALIZED VIEW v_relay_stuck IS 'Detects actuator relays stuck ON beyond threshold. Excludes config switches and virtual states.';
