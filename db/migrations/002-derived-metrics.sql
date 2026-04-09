-- Verdify Migration 002: Derived Metrics Views + Outdoor Columns
-- Run with: docker exec -i verdify-timescaledb-1 psql -U verdify -d verdify < 002-derived-metrics.sql

-- ============================================================
-- Outdoor weather columns (filled by outdoor-weather-sync.py)
-- ============================================================
ALTER TABLE climate ADD COLUMN IF NOT EXISTS outdoor_temp_f  FLOAT;
ALTER TABLE climate ADD COLUMN IF NOT EXISTS outdoor_rh_pct  FLOAT;

-- ============================================================
-- v_zone_temp_delta
-- Instantaneous north-south temperature difference.
-- ============================================================
CREATE OR REPLACE VIEW v_zone_temp_delta AS
SELECT
    ts,
    (temp_north - temp_south) AS zone_temp_delta
FROM climate
WHERE temp_north IS NOT NULL AND temp_south IS NOT NULL;

-- ============================================================
-- v_stress_hours_today
-- Stress hours per day derived from climate data vs current setpoints.
-- Each climate row = ~2 min, so 1/30 of an hour per row.
-- Uses the most recent setpoint for each parameter.
-- ============================================================
CREATE OR REPLACE VIEW v_stress_hours_today AS
WITH latest_setpoints AS (
    SELECT DISTINCT ON (parameter) parameter, value::float AS value
    FROM setpoint_changes
    ORDER BY parameter, ts DESC
)
SELECT
    date_trunc('day', ts) AS date,
    ROUND(SUM(CASE
        WHEN temp_avg < (SELECT value FROM latest_setpoints WHERE parameter = 'temp_low')
        THEN 2.0/60.0 ELSE 0 END)::numeric, 2) AS cold_stress_hours,
    ROUND(SUM(CASE
        WHEN temp_avg > (SELECT value FROM latest_setpoints WHERE parameter = 'temp_high')
        THEN 2.0/60.0 ELSE 0 END)::numeric, 2) AS heat_stress_hours,
    ROUND(SUM(CASE
        WHEN vpd_avg > (SELECT value FROM latest_setpoints WHERE parameter = 'vpd_high')
        THEN 2.0/60.0 ELSE 0 END)::numeric, 2) AS vpd_stress_hours,
    ROUND(SUM(CASE
        WHEN vpd_avg < (SELECT value FROM latest_setpoints WHERE parameter = 'vpd_low')
        THEN 2.0/60.0 ELSE 0 END)::numeric, 2) AS vpd_low_hours
FROM climate
WHERE temp_avg IS NOT NULL AND vpd_avg IS NOT NULL
GROUP BY 1
ORDER BY 1;
