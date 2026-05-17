-- Migration 127: make the lighting forecast timeline use qualified minutes
--
-- The old fn_lighting_timeline() projected expected-on state with the legacy
-- DLI gate. Runtime control now uses qualified light minutes: natural lux above
-- threshold OR switch-on time, counted once. Keep the historical DLI columns as
-- legacy compatibility fields, but drive expected-on projection from target
-- light minutes.

DROP FUNCTION IF EXISTS fn_lighting_timeline(timestamptz, timestamptz, interval, text);

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
    grow_dli_target double precision,
    main_target_light_minutes integer,
    grow_target_light_minutes integer,
    main_qualified_light_minutes double precision,
    grow_qualified_light_minutes double precision
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    r record;
    main_on boolean;
    grow_on boolean;
    main_minutes double precision := 0.0;
    grow_minutes double precision := 0.0;
    main_pre_minutes double precision;
    grow_pre_minutes double precision;
    main_in_window boolean;
    grow_in_window boolean;
    main_natural_qualified boolean;
    grow_natural_qualified boolean;
    main_want_on boolean;
    grow_want_on boolean;
    last_local_date date;
    last_local_hour integer := -1;
    step_minutes double precision := greatest(0.0, extract(epoch FROM p_step) / 60.0);
BEGIN
    SELECT COALESCE((
        SELECT e.state
        FROM equipment_state e
        WHERE COALESCE(e.greenhouse_id, p_greenhouse_id) = p_greenhouse_id
          AND e.equipment = 'grow_light_main'
          AND e.ts <= p_start
        ORDER BY e.ts DESC
        LIMIT 1
    ), false)
    INTO main_on;

    SELECT COALESCE((
        SELECT e.state
        FROM equipment_state e
        WHERE COALESCE(e.greenhouse_id, p_greenhouse_id) = p_greenhouse_id
          AND e.equipment = 'grow_light_grow'
          AND e.ts <= p_start
        ORDER BY e.ts DESC
        LIMIT 1
    ), false)
    INTO grow_on;

    FOR r IN
        WITH bounds AS (
            SELECT
                p_start AS start_ts,
                p_end AS end_ts,
                p_step AS step,
                now() AS now_ts
        ),
        series AS (
            SELECT generate_series(b.start_ts, b.end_ts, b.step) AS bucket_ts
            FROM bounds b
        ),
        observed AS (
            SELECT
                time_bucket((SELECT step FROM bounds), c.ts) AS bucket,
                avg(COALESCE(c.outdoor_lux, c.lux))::double precision AS natural_lux
            FROM climate c
            CROSS JOIN bounds b
            WHERE c.ts >= b.start_ts
              AND c.ts <= least(b.end_ts, b.now_ts)
              AND COALESCE(c.greenhouse_id, p_greenhouse_id) = p_greenhouse_id
              AND COALESCE(c.outdoor_lux, c.lux) IS NOT NULL
            GROUP BY 1
            ORDER BY 1
            LIMIT 2000
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
        policy AS MATERIALIZED (
            SELECT * FROM fn_lighting_minutes_policy((SELECT now_ts FROM bounds), p_greenhouse_id)
        ),
        main_policy AS (
            SELECT * FROM policy WHERE light_key = 'main'
        ),
        grow_policy AS (
            SELECT * FROM policy WHERE light_key = 'grow'
        )
        SELECT
            s.bucket_ts,
            COALESCE(o.natural_lux, f.natural_lux, 0.0)::double precision AS row_natural_lux,
            CASE
                WHEN o.natural_lux IS NOT NULL THEN 'tempest_observed'
                WHEN f.natural_lux IS NOT NULL THEN 'forecast_solar_w_m2_x120'
                ELSE 'missing'
            END AS row_natural_lux_source,
            (s.bucket_ts AT TIME ZONE 'America/Denver')::date AS row_local_date,
            EXTRACT(hour FROM s.bucket_ts AT TIME ZONE 'America/Denver')::integer AS row_local_hour,
            m.target_light_minutes AS row_main_target_light_minutes,
            m.start_hour AS row_main_start_hour,
            m.cutoff_hour AS row_main_cutoff_hour,
            m.lux_on_threshold AS row_main_lux_on_threshold,
            m.lux_off_threshold AS row_main_lux_off_threshold,
            m.auto_enabled AS row_main_auto_enabled,
            m.legacy_dli_target AS row_main_legacy_dli_target,
            g.target_light_minutes AS row_grow_target_light_minutes,
            g.start_hour AS row_grow_start_hour,
            g.cutoff_hour AS row_grow_cutoff_hour,
            g.lux_on_threshold AS row_grow_lux_on_threshold,
            g.lux_off_threshold AS row_grow_lux_off_threshold,
            g.auto_enabled AS row_grow_auto_enabled,
            g.legacy_dli_target AS row_grow_legacy_dli_target
        FROM series s
        LEFT JOIN observed o ON o.bucket = time_bucket((SELECT step FROM bounds), s.bucket_ts)
        LEFT JOIN forecast f ON f.bucket = time_bucket((SELECT step FROM bounds), s.bucket_ts)
        CROSS JOIN main_policy m
        CROSS JOIN grow_policy g
        ORDER BY s.bucket_ts
    LOOP
        IF last_local_date IS NULL OR r.row_local_date <> last_local_date THEN
            main_minutes := 0.0;
            grow_minutes := 0.0;
        END IF;

        IF r.row_local_hour = r.row_main_start_hour AND last_local_hour <> r.row_main_start_hour THEN
            main_minutes := 0.0;
        END IF;
        IF r.row_local_hour = r.row_grow_start_hour AND last_local_hour <> r.row_grow_start_hour THEN
            grow_minutes := 0.0;
        END IF;

        main_pre_minutes := main_minutes;
        grow_pre_minutes := grow_minutes;

        main_in_window := r.row_main_auto_enabled AND (
            CASE
                WHEN r.row_main_start_hour <= r.row_main_cutoff_hour THEN
                    r.row_local_hour >= r.row_main_start_hour
                    AND r.row_local_hour < r.row_main_cutoff_hour
                ELSE
                    r.row_local_hour >= r.row_main_start_hour
                    OR r.row_local_hour < r.row_main_cutoff_hour
            END
        );
        grow_in_window := r.row_grow_auto_enabled AND (
            CASE
                WHEN r.row_grow_start_hour <= r.row_grow_cutoff_hour THEN
                    r.row_local_hour >= r.row_grow_start_hour
                    AND r.row_local_hour < r.row_grow_cutoff_hour
                ELSE
                    r.row_local_hour >= r.row_grow_start_hour
                    OR r.row_local_hour < r.row_grow_cutoff_hour
            END
        );

        main_natural_qualified := r.row_natural_lux >= r.row_main_lux_on_threshold;
        grow_natural_qualified := r.row_natural_lux >= r.row_grow_lux_on_threshold;

        main_want_on := main_in_window
            AND main_pre_minutes < r.row_main_target_light_minutes
            AND (
                (NOT main_on AND r.row_natural_lux < r.row_main_lux_on_threshold)
                OR (main_on AND r.row_natural_lux < r.row_main_lux_off_threshold)
            );
        grow_want_on := grow_in_window
            AND grow_pre_minutes < r.row_grow_target_light_minutes
            AND (
                (NOT grow_on AND r.row_natural_lux < r.row_grow_lux_on_threshold)
                OR (grow_on AND r.row_natural_lux < r.row_grow_lux_off_threshold)
            );

        main_on := main_want_on;
        grow_on := grow_want_on;

        IF main_in_window AND (main_natural_qualified OR main_on) THEN
            main_minutes := main_minutes + step_minutes;
        END IF;
        IF grow_in_window AND (grow_natural_qualified OR grow_on) THEN
            grow_minutes := grow_minutes + step_minutes;
        END IF;

        ts := r.bucket_ts;
        natural_lux := NULLIF(r.row_natural_lux, 0.0);
        natural_lux_source := r.row_natural_lux_source;
        main_lux_on_threshold := r.row_main_lux_on_threshold;
        main_lux_off_threshold := r.row_main_lux_off_threshold;
        grow_lux_on_threshold := r.row_grow_lux_on_threshold;
        grow_lux_off_threshold := r.row_grow_lux_off_threshold;
        main_expected_on := CASE WHEN main_on THEN 1.0 ELSE 0.0 END;
        grow_expected_on := CASE WHEN grow_on THEN 1.0 ELSE 0.0 END;
        main_dli_target := r.row_main_legacy_dli_target;
        grow_dli_target := r.row_grow_legacy_dli_target;
        main_target_light_minutes := r.row_main_target_light_minutes;
        grow_target_light_minutes := r.row_grow_target_light_minutes;
        main_qualified_light_minutes := main_minutes;
        grow_qualified_light_minutes := grow_minutes;

        last_local_date := r.row_local_date;
        last_local_hour := r.row_local_hour;
        RETURN NEXT;
    END LOOP;
END;
$$;

COMMENT ON FUNCTION fn_lighting_timeline(timestamptz, timestamptz, interval, text) IS
    'Graph-safe observed/forecast lux timeline. Expected-on projection follows firmware ON/OFF hysteresis, target_light_minutes, window, and auto gates; legacy DLI target columns remain compatibility-only.';
