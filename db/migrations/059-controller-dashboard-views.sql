-- 059-controller-dashboard-views.sql
-- Supporting views for the ESP32 Controller Health dashboard
-- 4 views: v_setpoint_velocity, v_state_transition_rate, v_data_pipeline_health, v_reboot_log

-- v_setpoint_velocity: per-parameter write rate + oscillation detection
-- An "oscillation" = value changed then changed back within 10 minutes
CREATE OR REPLACE VIEW v_setpoint_velocity AS
WITH hourly AS (
    SELECT
        date_trunc('hour', ts) AS hour,
        parameter,
        source,
        COUNT(*) AS writes,
        COUNT(*) FILTER (WHERE EXISTS (
            SELECT 1 FROM setpoint_changes sc2
            WHERE sc2.parameter = sc.parameter
              AND sc2.ts > sc.ts
              AND sc2.ts < sc.ts + interval '10 minutes'
              AND sc2.value != sc.value
        )) AS oscillations
    FROM setpoint_changes sc
    WHERE ts > now() - interval '30 days'
    GROUP BY 1, 2, 3
)
SELECT hour, parameter, source, writes, oscillations
FROM hourly;

-- v_state_transition_rate: state machine transition frequency
CREATE OR REPLACE VIEW v_state_transition_rate AS
SELECT
    date_trunc('hour', ts) AS hour,
    COUNT(*) AS transitions,
    COUNT(DISTINCT value) AS unique_states
FROM system_state
WHERE entity = 'greenhouse_state' AND ts > now() - interval '30 days'
GROUP BY 1;

-- v_data_pipeline_health: per-source data rates and freshness
CREATE OR REPLACE VIEW v_data_pipeline_health AS
SELECT
    'climate' AS source,
    COUNT(*) FILTER (WHERE ts > now() - interval '1 hour') AS rows_1h,
    COUNT(*) FILTER (WHERE ts > now() - interval '24 hours') AS rows_24h,
    EXTRACT(EPOCH FROM now() - MAX(ts))::int AS age_s,
    COUNT(*) FILTER (WHERE temp_avg IS NULL AND ts > now() - interval '1 hour')::float
        / NULLIF(COUNT(*) FILTER (WHERE ts > now() - interval '1 hour'), 0) * 100 AS null_pct_1h
FROM climate
UNION ALL
SELECT 'equipment',
    COUNT(*) FILTER (WHERE ts > now() - interval '1 hour'),
    COUNT(*) FILTER (WHERE ts > now() - interval '24 hours'),
    EXTRACT(EPOCH FROM now() - MAX(ts))::int,
    NULL
FROM equipment_state
UNION ALL
SELECT 'diagnostics',
    COUNT(*) FILTER (WHERE ts > now() - interval '1 hour'),
    COUNT(*) FILTER (WHERE ts > now() - interval '24 hours'),
    EXTRACT(EPOCH FROM now() - MAX(ts))::int,
    NULL
FROM diagnostics
UNION ALL
SELECT 'energy',
    COUNT(*) FILTER (WHERE ts > now() - interval '1 hour'),
    COUNT(*) FILTER (WHERE ts > now() - interval '24 hours'),
    EXTRACT(EPOCH FROM now() - MAX(ts))::int,
    NULL
FROM energy
UNION ALL
SELECT 'setpoints',
    COUNT(*) FILTER (WHERE ts > now() - interval '1 hour'),
    COUNT(*) FILTER (WHERE ts > now() - interval '24 hours'),
    EXTRACT(EPOCH FROM now() - MAX(ts))::int,
    NULL
FROM setpoint_changes;

-- v_reboot_log: ESP32 reboots with uptime-before
CREATE OR REPLACE VIEW v_reboot_log AS
SELECT
    ts,
    uptime_s AS uptime_after,
    reset_reason,
    LAG(uptime_s) OVER (ORDER BY ts) AS uptime_before,
    EXTRACT(EPOCH FROM ts - LAG(ts) OVER (ORDER BY ts))::int AS gap_s
FROM diagnostics
WHERE uptime_s < 300  -- just rebooted
  AND ts > now() - interval '90 days'
ORDER BY ts DESC;
