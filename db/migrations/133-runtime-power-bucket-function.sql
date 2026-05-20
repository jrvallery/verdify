-- Fast runtime-power bucket surface for public Grafana panels.
--
-- The first runtime-electric dashboard pass rebuilt power at request time with
-- generate_series(5 minutes) x equipment_assets x fn_equip_at(...). A 30-day
-- panel could spend 80+ seconds issuing repeated latest-state lookups. This
-- function walks equipment_state intervals once, then apportions active runtime
-- into 30-minute buckets.

BEGIN;

CREATE OR REPLACE FUNCTION fn_runtime_power_30m(
    p_start timestamptz,
    p_end timestamptz
)
RETURNS TABLE (
    bucket timestamptz,
    total_watts double precision,
    heat1_watts double precision,
    fans_watts double precision,
    other_watts double precision
)
LANGUAGE sql
STABLE
AS $$
WITH bounds AS (
    SELECT
        time_bucket('30 minutes', p_start) AS start_ts,
        time_bucket('30 minutes', p_end) + interval '30 minutes' AS end_ts
), wattages AS (
    SELECT equipment, wattage::double precision AS wattage
    FROM equipment_assets
    WHERE wattage IS NOT NULL
), seed AS (
    SELECT
        b.start_ts AS ts,
        w.equipment,
        COALESCE((
            SELECT es.state
            FROM equipment_state es
            WHERE es.equipment = w.equipment
              AND es.ts <= b.start_ts
            ORDER BY es.ts DESC
            LIMIT 1
        ), false) AS state,
        w.wattage
    FROM bounds b
    CROSS JOIN wattages w
), changes AS (
    SELECT es.ts, es.equipment, es.state, w.wattage
    FROM equipment_state es
    JOIN wattages w USING (equipment)
    CROSS JOIN bounds b
    WHERE es.ts > b.start_ts
      AND es.ts < b.end_ts
), events AS (
    SELECT * FROM seed
    UNION ALL
    SELECT * FROM changes
), segments AS (
    SELECT
        equipment,
        wattage,
        state,
        ts AS start_ts,
        LEAD(ts) OVER (PARTITION BY equipment ORDER BY ts) AS next_ts
    FROM events
), active_segments AS (
    SELECT
        s.equipment,
        s.wattage,
        GREATEST(s.start_ts, b.start_ts) AS start_ts,
        LEAST(COALESCE(s.next_ts, b.end_ts), b.end_ts) AS end_ts
    FROM segments s
    CROSS JOIN bounds b
    WHERE s.state IS TRUE
      AND COALESCE(s.next_ts, b.end_ts) > b.start_ts
      AND s.start_ts < b.end_ts
), expanded AS (
    SELECT
        gs.bucket,
        a.equipment,
        a.wattage
            * GREATEST(
                EXTRACT(EPOCH FROM LEAST(a.end_ts, gs.bucket + interval '30 minutes') - GREATEST(a.start_ts, gs.bucket)),
                0
            )
            / 1800.0 AS avg_watts
    FROM active_segments a
    CROSS JOIN LATERAL generate_series(
        time_bucket('30 minutes', a.start_ts),
        time_bucket('30 minutes', a.end_ts - interval '1 microsecond'),
        interval '30 minutes'
    ) AS gs(bucket)
), buckets AS (
    SELECT generate_series(
        (SELECT start_ts FROM bounds),
        (SELECT end_ts FROM bounds) - interval '30 minutes',
        interval '30 minutes'
    ) AS bucket
)
SELECT
    b.bucket,
    round(COALESCE(SUM(e.avg_watts), 0)::numeric, 2)::double precision AS total_watts,
    round(COALESCE(SUM(e.avg_watts) FILTER (WHERE e.equipment = 'heat1'), 0)::numeric, 2)::double precision AS heat1_watts,
    round(COALESCE(SUM(e.avg_watts) FILTER (WHERE e.equipment IN ('fan1', 'fan2')), 0)::numeric, 2)::double precision AS fans_watts,
    round(COALESCE(SUM(e.avg_watts) FILTER (WHERE e.equipment NOT IN ('heat1', 'fan1', 'fan2')), 0)::numeric, 2)::double precision AS other_watts
FROM buckets b
LEFT JOIN expanded e USING (bucket)
GROUP BY b.bucket
ORDER BY b.bucket;
$$;

COMMENT ON FUNCTION fn_runtime_power_30m(timestamptz, timestamptz) IS
'Returns 30-minute runtime-modeled greenhouse electric load from equipment_state intervals and published equipment_assets wattage. Used by public Grafana panels to avoid per-sample fn_equip_at lookups.';

COMMIT;
