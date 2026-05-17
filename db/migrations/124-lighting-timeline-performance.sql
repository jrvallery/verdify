-- Migration 124: make lighting forecast-band timeline graph-safe
--
-- Migration 123 called fn_lighting_circuit_policy() twice for every generated
-- time bucket. That is correct but far too slow for homepage Grafana panels
-- because the policy function resolves latest setpoint_changes history. The
-- graph only needs the current planner/default lighting policy projected over
-- observed and forecast natural light, so resolve main/grow policy once and
-- cross join it across the timeline.

CREATE OR REPLACE FUNCTION fn_lighting_timeline(
    p_start timestamptz,
    p_end timestamptz,
    p_step interval DEFAULT interval '30 minutes',
    p_greenhouse_id text DEFAULT 'vallery'
)
RETURNS TABLE (
    ts timestamptz,
    natural_lux double precision,
    natural_lux_source text,
    main_lux_on_threshold double precision,
    main_lux_off_threshold double precision,
    grow_lux_on_threshold double precision,
    grow_lux_off_threshold double precision,
    main_expected_on double precision,
    grow_expected_on double precision,
    main_dli_target double precision,
    grow_dli_target double precision
)
LANGUAGE sql
STABLE
AS $$
WITH RECURSIVE bounds AS (
    SELECT
        p_start AS start_ts,
        p_end AS end_ts,
        p_step AS step,
        now() AS now_ts
),
series AS (
    SELECT generate_series(b.start_ts, b.end_ts, b.step) AS ts
    FROM bounds b
),
observed AS (
    SELECT
        time_bucket((SELECT step FROM bounds), c.ts) AS bucket,
        avg(COALESCE(c.outdoor_lux, c.lux))::double precision AS natural_lux,
        max(c.dli_today)::double precision AS dli_today
    FROM climate c
    CROSS JOIN bounds b
    WHERE c.ts >= b.start_ts
      AND c.ts <= least(b.end_ts, b.now_ts)
      AND COALESCE(c.greenhouse_id, p_greenhouse_id) = p_greenhouse_id
      AND COALESCE(c.outdoor_lux, c.lux) IS NOT NULL
    GROUP BY 1
),
latest_dli AS (
    SELECT COALESCE((
        SELECT c.dli_today::double precision
        FROM climate c
        WHERE c.ts <= (SELECT now_ts FROM bounds)
          AND COALESCE(c.greenhouse_id, p_greenhouse_id) = p_greenhouse_id
          AND c.dli_today IS NOT NULL
        ORDER BY c.ts DESC
        LIMIT 1
    ), 0.0) AS dli_today
),
forecast AS (
    SELECT DISTINCT ON (time_bucket((SELECT step FROM bounds), wf.ts))
        time_bucket((SELECT step FROM bounds), wf.ts) AS bucket,
        (wf.solar_w_m2 * 120.0)::double precision AS natural_lux
    FROM weather_forecast wf
    CROSS JOIN bounds b
    WHERE wf.ts > b.now_ts
      AND wf.ts >= b.start_ts
      AND wf.ts <= b.end_ts
      AND wf.solar_w_m2 IS NOT NULL
    ORDER BY time_bucket((SELECT step FROM bounds), wf.ts), wf.fetched_at DESC
),
policy AS (
    SELECT * FROM fn_lighting_circuit_policy((SELECT now_ts FROM bounds), p_greenhouse_id)
),
main_policy AS (
    SELECT * FROM policy WHERE light_key = 'main'
),
grow_policy AS (
    SELECT * FROM policy WHERE light_key = 'grow'
),
seed AS (
    SELECT
        COALESCE(
            (
                SELECT e.state
                FROM equipment_state e
                CROSS JOIN bounds b
                WHERE e.equipment = 'grow_light_main'
                  AND e.ts <= b.start_ts
                ORDER BY e.ts DESC
                LIMIT 1
            ),
            (
                SELECT e.state
                FROM equipment_state e
                WHERE e.equipment = 'grow_light_main'
                ORDER BY e.ts DESC
                LIMIT 1
            ),
            false
        ) AS main_seed_on,
        COALESCE(
            (
                SELECT e.state
                FROM equipment_state e
                CROSS JOIN bounds b
                WHERE e.equipment = 'grow_light_grow'
                  AND e.ts <= b.start_ts
                ORDER BY e.ts DESC
                LIMIT 1
            ),
            (
                SELECT e.state
                FROM equipment_state e
                WHERE e.equipment = 'grow_light_grow'
                ORDER BY e.ts DESC
                LIMIT 1
            ),
            false
        ) AS grow_seed_on
),
timeline AS (
    SELECT
        row_number() OVER (ORDER BY s.ts) AS rn,
        s.ts,
        COALESCE(o.natural_lux, f.natural_lux, 0.0) AS natural_lux,
        CASE
            WHEN o.natural_lux IS NOT NULL THEN 'tempest_observed'
            WHEN f.natural_lux IS NOT NULL THEN 'forecast_solar_w_m2_x120'
            ELSE 'missing'
        END AS natural_lux_source,
        COALESCE(
            o.dli_today,
            CASE
                WHEN DATE(s.ts AT TIME ZONE 'America/Denver')
                   > DATE((SELECT now_ts FROM bounds) AT TIME ZONE 'America/Denver') THEN 0.0
                ELSE (SELECT dli_today FROM latest_dli)
            END
        ) AS dli_today,
        m.dli_target AS main_dli_target,
        m.start_hour AS main_start_hour,
        m.cutoff_hour AS main_cutoff_hour,
        m.lux_on_threshold AS main_lux_on_threshold,
        m.lux_off_threshold AS main_lux_off_threshold,
        m.auto_enabled AS main_auto_enabled,
        g.dli_target AS grow_dli_target,
        g.start_hour AS grow_start_hour,
        g.cutoff_hour AS grow_cutoff_hour,
        g.lux_on_threshold AS grow_lux_on_threshold,
        g.lux_off_threshold AS grow_lux_off_threshold,
        g.auto_enabled AS grow_auto_enabled
    FROM series s
    LEFT JOIN observed o ON o.bucket = time_bucket((SELECT step FROM bounds), s.ts)
    LEFT JOIN forecast f ON f.bucket = time_bucket((SELECT step FROM bounds), s.ts)
    CROSS JOIN main_policy m
    CROSS JOIN grow_policy g
),
ordered AS (
    SELECT
        t.*,
        (
            t.main_auto_enabled
            AND t.dli_today < t.main_dli_target
            AND CASE
                WHEN t.main_start_hour <= t.main_cutoff_hour THEN
                    EXTRACT(hour FROM t.ts AT TIME ZONE 'America/Denver')::integer >= t.main_start_hour
                    AND EXTRACT(hour FROM t.ts AT TIME ZONE 'America/Denver')::integer < t.main_cutoff_hour
                ELSE
                    EXTRACT(hour FROM t.ts AT TIME ZONE 'America/Denver')::integer >= t.main_start_hour
                    OR EXTRACT(hour FROM t.ts AT TIME ZONE 'America/Denver')::integer < t.main_cutoff_hour
            END
        ) AS main_gate_open,
        (
            t.grow_auto_enabled
            AND t.dli_today < t.grow_dli_target
            AND CASE
                WHEN t.grow_start_hour <= t.grow_cutoff_hour THEN
                    EXTRACT(hour FROM t.ts AT TIME ZONE 'America/Denver')::integer >= t.grow_start_hour
                    AND EXTRACT(hour FROM t.ts AT TIME ZONE 'America/Denver')::integer < t.grow_cutoff_hour
                ELSE
                    EXTRACT(hour FROM t.ts AT TIME ZONE 'America/Denver')::integer >= t.grow_start_hour
                    OR EXTRACT(hour FROM t.ts AT TIME ZONE 'America/Denver')::integer < t.grow_cutoff_hour
            END
        ) AS grow_gate_open
    FROM timeline t
),
stateful AS (
    SELECT
        o.*,
        (
            o.main_gate_open
            AND (
                (NOT seed.main_seed_on AND o.natural_lux < o.main_lux_on_threshold)
                OR (seed.main_seed_on AND o.natural_lux < o.main_lux_off_threshold)
            )
        ) AS main_state_on,
        (
            o.grow_gate_open
            AND (
                (NOT seed.grow_seed_on AND o.natural_lux < o.grow_lux_on_threshold)
                OR (seed.grow_seed_on AND o.natural_lux < o.grow_lux_off_threshold)
            )
        ) AS grow_state_on
    FROM ordered o
    CROSS JOIN seed
    WHERE o.rn = 1

    UNION ALL

    SELECT
        o.*,
        (
            o.main_gate_open
            AND (
                (NOT s.main_state_on AND o.natural_lux < o.main_lux_on_threshold)
                OR (s.main_state_on AND o.natural_lux < o.main_lux_off_threshold)
            )
        ) AS main_state_on,
        (
            o.grow_gate_open
            AND (
                (NOT s.grow_state_on AND o.natural_lux < o.grow_lux_on_threshold)
                OR (s.grow_state_on AND o.natural_lux < o.grow_lux_off_threshold)
            )
        ) AS grow_state_on
    FROM stateful s
    JOIN ordered o ON o.rn = s.rn + 1
)
SELECT
    s.ts,
    NULLIF(s.natural_lux, 0.0) AS natural_lux,
    s.natural_lux_source,
    s.main_lux_on_threshold,
    s.main_lux_off_threshold,
    s.grow_lux_on_threshold,
    s.grow_lux_off_threshold,
    CASE WHEN s.main_state_on THEN 1.0 ELSE 0.0 END AS main_expected_on,
    CASE WHEN s.grow_state_on THEN 1.0 ELSE 0.0 END AS grow_expected_on,
    s.main_dli_target,
    s.grow_dli_target
FROM stateful s
ORDER BY s.ts;
$$;

COMMENT ON FUNCTION fn_lighting_timeline(timestamptz, timestamptz, interval, text) IS
    'Graph-safe historical Tempest lux plus forecast solar-derived lux joined to current per-circuit lighting thresholds; expected-on projection follows firmware ON/OFF hysteresis, DLI, window, and auto gates.';
