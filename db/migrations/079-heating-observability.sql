-- 079-heating-observability.sql
-- Firmware version tracking, heating staging diagnostics, inversion alerts
-- Context: Two days debugging inverted dH2/heat_hysteresis thresholds with no
-- firmware versioning, no threshold diagnostics, and no staging inversion alerts.

BEGIN;

-- 1. Firmware version column in diagnostics table
ALTER TABLE diagnostics ADD COLUMN IF NOT EXISTS firmware_version TEXT;

CREATE INDEX IF NOT EXISTS idx_diagnostics_fw_version
    ON diagnostics (firmware_version, ts DESC) WHERE firmware_version IS NOT NULL;

-- 2. Heating staging inversion detection function
-- Returns a row when heat2 (gas) is ON while heat1 (electric) is OFF for >60s.
CREATE OR REPLACE FUNCTION fn_heat_staging_inversion()
RETURNS TABLE(
    heat2_on_since timestamptz,
    heat1_state boolean,
    duration_s double precision,
    temp_avg double precision,
    temp_low double precision,
    d_heat_stage_2 double precision
) LANGUAGE sql STABLE AS $$
    WITH latest_h2 AS (
        SELECT ts, state FROM equipment_state
        WHERE equipment = 'heat2' ORDER BY ts DESC LIMIT 1
    ),
    latest_h1 AS (
        SELECT ts, state FROM equipment_state
        WHERE equipment = 'heat1' ORDER BY ts DESC LIMIT 1
    ),
    latest_climate AS (
        SELECT temp_avg FROM climate
        WHERE temp_avg IS NOT NULL ORDER BY ts DESC LIMIT 1
    ),
    latest_sp AS (
        SELECT
            MAX(value) FILTER (WHERE parameter = 'temp_low') AS temp_low,
            MAX(value) FILTER (WHERE parameter = 'd_heat_stage_2') AS d_heat_stage_2
        FROM (
            SELECT DISTINCT ON (parameter) parameter, value
            FROM setpoint_snapshot
            WHERE parameter IN ('temp_low', 'd_heat_stage_2')
              AND ts > now() - interval '10 minutes'
            ORDER BY parameter, ts DESC
        ) sub
    )
    SELECT h2.ts, h1.state, EXTRACT(EPOCH FROM now() - h2.ts),
           c.temp_avg, sp.temp_low, sp.d_heat_stage_2
    FROM latest_h2 h2, latest_h1 h1, latest_climate c, latest_sp sp
    WHERE h2.state = true AND h1.state = false
      AND EXTRACT(EPOCH FROM now() - h2.ts) > 60;
$$;

-- 3. Heating staging analysis view
CREATE OR REPLACE VIEW v_heating_staging AS
WITH heat_events AS (
    SELECT ts, equipment, state,
        LEAD(ts) OVER (PARTITION BY equipment ORDER BY ts) AS next_ts
    FROM equipment_state WHERE equipment IN ('heat1', 'heat2')
),
heat2_on AS (
    SELECT ts AS on_ts, COALESCE(next_ts, now()) AS off_ts
    FROM heat_events WHERE equipment = 'heat2' AND state = true
)
SELECT
    h2.on_ts AT TIME ZONE 'America/Denver' AS heat2_on_mdt,
    h2.off_ts AT TIME ZONE 'America/Denver' AS heat2_off_mdt,
    ROUND(EXTRACT(EPOCH FROM h2.off_ts - h2.on_ts)::numeric / 60, 1) AS duration_min,
    (SELECT state FROM equipment_state
     WHERE equipment = 'heat1' AND ts <= h2.on_ts
     ORDER BY ts DESC LIMIT 1) AS heat1_was_on,
    (SELECT ROUND(temp_avg::numeric, 1) FROM climate
     WHERE ts <= h2.on_ts AND temp_avg IS NOT NULL
     ORDER BY ts DESC LIMIT 1) AS temp_at_engage,
    fn_setpoint_at('temp_low', h2.on_ts) AS setpoint_temp_low
FROM heat2_on h2
ORDER BY h2.on_ts DESC;

-- 4. Daily heating staging summary
CREATE OR REPLACE VIEW v_heating_staging_summary AS
SELECT
    date_trunc('day', heat2_on_mdt)::date AS date,
    COUNT(*) AS heat2_events,
    COUNT(*) FILTER (WHERE NOT COALESCE(heat1_was_on, false)) AS inversions,
    ROUND(100.0 * COUNT(*) FILTER (WHERE NOT COALESCE(heat1_was_on, false))
          / NULLIF(COUNT(*), 0), 1) AS inversion_pct,
    ROUND(AVG(temp_at_engage)::numeric, 1) AS avg_engage_temp,
    ROUND(SUM(duration_min)::numeric, 1) AS total_heat2_min
FROM v_heating_staging
GROUP BY 1 ORDER BY 1 DESC;

COMMIT;
