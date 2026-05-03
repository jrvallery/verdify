-- Migration 095: make v_stress_hours_today time-weighted.
--
-- The live climate cadence is roughly 60s, but the old view counted every row
-- as a fixed 2 minutes. That inflated daily stress counters and could leave
-- stale vpd_stress warnings open even after the controller recovered.

CREATE OR REPLACE VIEW v_stress_hours_today AS
WITH bounds AS (
    SELECT
        date_trunc('day', now() AT TIME ZONE 'America/Denver') AT TIME ZONE 'America/Denver' AS start_ts,
        (date_trunc('day', now() AT TIME ZONE 'America/Denver') + interval '1 day') AT TIME ZONE 'America/Denver' AS end_ts
),
readings AS (
    SELECT
        c.ts,
        date_trunc('day', c.ts AT TIME ZONE 'America/Denver') AT TIME ZONE 'America/Denver' AS date,
        c.temp_avg,
        c.vpd_avg,
        lead(c.ts) OVER (
            PARTITION BY date_trunc('day', c.ts AT TIME ZONE 'America/Denver')
            ORDER BY c.ts
        ) AS next_ts
    FROM climate c
    CROSS JOIN bounds b
    WHERE c.ts >= b.start_ts
      AND c.ts < b.end_ts
      AND c.temp_avg IS NOT NULL
      AND c.vpd_avg IS NOT NULL
),
weighted AS (
    SELECT
        r.*,
        least(
            greatest(
                extract(epoch FROM (coalesce(r.next_ts, least(now(), r.ts + interval '2 minutes')) - r.ts)) / 3600.0,
                0
            ),
            5.0 / 60.0
        ) AS sample_hours
    FROM readings r
)
SELECT
    date,
    round(sum(CASE WHEN temp_avg < fn_setpoint_at('temp_low', ts) THEN sample_hours ELSE 0 END)::numeric, 2) AS cold_stress_hours,
    round(sum(CASE WHEN temp_avg > fn_setpoint_at('temp_high', ts) THEN sample_hours ELSE 0 END)::numeric, 2) AS heat_stress_hours,
    round(sum(CASE WHEN vpd_avg > fn_setpoint_at('vpd_high', ts) THEN sample_hours ELSE 0 END)::numeric, 2) AS vpd_stress_hours,
    round(sum(CASE WHEN vpd_avg < fn_setpoint_at('vpd_low', ts) THEN sample_hours ELSE 0 END)::numeric, 2) AS vpd_low_hours
FROM weighted
GROUP BY date;
