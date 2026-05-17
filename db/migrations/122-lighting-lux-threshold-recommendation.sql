-- Migration 122: evidence-derived Tempest lux threshold recommendation
--
-- Firmware uses Tempest outdoor illuminance as the primary light trigger.
-- This function turns recent observations into planner context so Iris can
-- tune gl_lux_threshold from evidence instead of carrying the old static value.

CREATE OR REPLACE FUNCTION fn_lighting_lux_threshold_recommendation(
    p_ts timestamptz DEFAULT now(),
    p_greenhouse_id text DEFAULT 'vallery',
    p_window interval DEFAULT interval '30 days'
)
RETURNS TABLE (
    greenhouse_id text,
    ts timestamptz,
    sample_count integer,
    overcast_sample_count integer,
    clear_sample_count integer,
    overcast_p80_lux double precision,
    clear_p20_lux double precision,
    recommended_gl_lux_threshold double precision,
    recommended_gl_lux_hysteresis double precision,
    current_gl_lux_threshold double precision,
    current_gl_lux_hysteresis double precision,
    source_chain text
)
LANGUAGE sql
STABLE
AS $$
WITH daylight AS (
    SELECT
        c.ts,
        c.outdoor_lux::double precision AS outdoor_lux,
        c.solar_irradiance_w_m2::double precision AS solar_w_m2,
        fn_solar_altitude(c.ts)::double precision AS altitude_deg
    FROM climate c
    WHERE c.ts >= p_ts - p_window
      AND c.ts <= p_ts
      AND COALESCE(c.greenhouse_id, 'vallery') = p_greenhouse_id
      AND c.outdoor_lux IS NOT NULL
      AND c.solar_irradiance_w_m2 IS NOT NULL
      AND fn_solar_altitude(c.ts) >= 10
),
normalized AS (
    SELECT
        *,
        outdoor_lux / NULLIF(sin(radians(greatest(altitude_deg, 1.0))), 0.0) AS lux_norm,
        solar_w_m2 / NULLIF(sin(radians(greatest(altitude_deg, 1.0))), 0.0) AS solar_norm
    FROM daylight
),
clear_reference AS (
    SELECT
        percentile_cont(0.90) WITHIN GROUP (ORDER BY solar_norm) AS clear_solar_norm
    FROM normalized
),
classified AS (
    SELECT
        n.*,
        n.solar_norm / NULLIF(c.clear_solar_norm, 0.0) AS solar_clear_ratio
    FROM normalized n
    CROSS JOIN clear_reference c
),
stats AS (
    SELECT
        count(*)::integer AS sample_count,
        count(*) FILTER (WHERE solar_clear_ratio < 0.35)::integer AS overcast_sample_count,
        count(*) FILTER (WHERE solar_clear_ratio > 0.70)::integer AS clear_sample_count,
        percentile_cont(0.80) WITHIN GROUP (ORDER BY outdoor_lux)
            FILTER (WHERE solar_clear_ratio < 0.35) AS overcast_p80_lux,
        percentile_cont(0.20) WITHIN GROUP (ORDER BY outdoor_lux)
            FILTER (WHERE solar_clear_ratio > 0.70) AS clear_p20_lux,
        percentile_cont(0.20) WITHIN GROUP (ORDER BY outdoor_lux) AS daylight_p20_lux
    FROM classified
),
latest_thresholds AS (
    SELECT DISTINCT ON (parameter)
        parameter,
        value::double precision AS value
    FROM setpoint_changes
    WHERE COALESCE(greenhouse_id, p_greenhouse_id) = p_greenhouse_id
      AND parameter IN ('gl_main_lux_threshold', 'gl_grow_lux_threshold', 'gl_lux_threshold')
      AND COALESCE(source, '') <> 'esp32'
    ORDER BY parameter, ts DESC
),
latest_hysteresis AS (
    SELECT DISTINCT ON (parameter)
        parameter,
        value::double precision AS value
    FROM setpoint_changes
    WHERE COALESCE(greenhouse_id, p_greenhouse_id) = p_greenhouse_id
      AND parameter IN ('gl_main_lux_hysteresis', 'gl_grow_lux_hysteresis', 'gl_lux_hysteresis')
      AND COALESCE(source, '') <> 'esp32'
    ORDER BY parameter, ts DESC
),
current_threshold AS (
    SELECT
        COALESCE(
            max(value) FILTER (WHERE parameter = 'gl_main_lux_threshold'),
            max(value) FILTER (WHERE parameter = 'gl_grow_lux_threshold'),
            max(value) FILTER (WHERE parameter = 'gl_lux_threshold')
        ) AS current_gl_lux_threshold
    FROM latest_thresholds
),
current_hysteresis AS (
    SELECT
        COALESCE(
            max(value) FILTER (WHERE parameter = 'gl_main_lux_hysteresis'),
            max(value) FILTER (WHERE parameter = 'gl_grow_lux_hysteresis'),
            max(value) FILTER (WHERE parameter = 'gl_lux_hysteresis')
        ) AS current_gl_lux_hysteresis
    FROM latest_hysteresis
),
current_policy AS (
    SELECT
        current_threshold.current_gl_lux_threshold,
        current_hysteresis.current_gl_lux_hysteresis
    FROM current_threshold
    CROSS JOIN current_hysteresis
),
recommendation AS (
    SELECT
        stats.*,
        round(
            greatest(
                5000.0,
                least(
                    40000.0,
                    COALESCE(
                        (stats.overcast_p80_lux + stats.clear_p20_lux) / 2.0,
                        stats.daylight_p20_lux,
                        30000.0
                    )
                )
            )::numeric,
            -2
        )::double precision AS recommended_gl_lux_threshold
    FROM stats
)
SELECT
    p_greenhouse_id AS greenhouse_id,
    p_ts AS ts,
    r.sample_count,
    r.overcast_sample_count,
    r.clear_sample_count,
    r.overcast_p80_lux,
    r.clear_p20_lux,
    r.recommended_gl_lux_threshold,
    round(greatest(1500.0, least(10000.0, r.recommended_gl_lux_threshold * 0.20))::numeric, -2)::double precision
        AS recommended_gl_lux_hysteresis,
    COALESCE(cp.current_gl_lux_threshold, r.recommended_gl_lux_threshold, 40000.0) AS current_gl_lux_threshold,
    COALESCE(
        cp.current_gl_lux_hysteresis,
        round(greatest(1500.0, least(10000.0, r.recommended_gl_lux_threshold * 0.20))::numeric, -2)::double precision,
        8000.0
    ) AS current_gl_lux_hysteresis,
    'Tempest outdoor_lux + solar_irradiance_w_m2 history -> fn_lighting_lux_threshold_recommendation() -> Iris planner -> per-circuit gl_main_*/gl_grow_* lux tunables -> dispatcher/API -> ESP32 lighting state machines'::text
        AS source_chain
FROM recommendation r
LEFT JOIN current_policy cp ON true;
$$;

COMMENT ON FUNCTION fn_lighting_lux_threshold_recommendation(timestamptz, text, interval) IS
    'Recommends grow-light lux threshold/hysteresis from recent Tempest outdoor lux and solar irradiance. Overcast is solar_clear_ratio < 0.35; clear sun is > 0.70; threshold is the midpoint between overcast p80 and clear p20, clamped 5k-40k lux.';
