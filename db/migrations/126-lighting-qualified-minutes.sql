-- Migration 126: lighting qualified-minutes model
--
-- The production lighting controller is moving away from estimated DLI as the
-- primary control variable. With fixed-output lights and no interior PAR
-- sensor, the operational contract is a sunrise-based qualified-light-minutes
-- budget per circuit:
--
--   qualified minute = exterior/natural lux is above the circuit threshold
--                      OR the actual Lutron switch is ON
--
-- Natural and supplemental light are counted once via OR semantics, so a light
-- held ON inside the hysteresis band does not double-count the same minute.

CREATE OR REPLACE FUNCTION fn_lighting_minutes_policy(
    p_ts timestamptz DEFAULT now(),
    p_greenhouse_id text DEFAULT 'vallery'
)
RETURNS TABLE (
    greenhouse_id text,
    ts timestamptz,
    light_key text,
    equipment text,
    target_light_minutes integer,
    start_hour integer,
    cutoff_hour integer,
    lux_on_threshold double precision,
    lux_hysteresis double precision,
    lux_off_threshold double precision,
    min_on_s integer,
    min_off_s integer,
    auto_enabled boolean,
    legacy_dli_target double precision,
    source_chain text,
    controller_contract text
)
LANGUAGE sql
STABLE
ROWS 2
AS $$
WITH base AS (
    SELECT * FROM fn_lighting_policy(p_ts, p_greenhouse_id)
),
recommendation AS (
    SELECT * FROM fn_lighting_lux_threshold_recommendation(p_ts, p_greenhouse_id)
),
circuits AS (
    SELECT *
    FROM (VALUES
        ('main'::text, 'grow_light_main'::text),
        ('grow'::text, 'grow_light_grow'::text)
    ) AS v(light_key, equipment)
),
latest_changes AS (
    SELECT DISTINCT ON (parameter)
        parameter,
        value::double precision AS value
    FROM setpoint_changes
    WHERE COALESCE(greenhouse_id, p_greenhouse_id) = p_greenhouse_id
      AND COALESCE(source, '') <> 'esp32'
      AND parameter = ANY(ARRAY[
          'gl_dli_target',
          'gl_sunrise_hour',
          'gl_sunset_hour',
          'gl_lux_threshold',
          'gl_lux_hysteresis',
          'sw_gl_auto_mode',
          'gl_main_target_light_minutes',
          'gl_main_dli_target',
          'gl_main_sunrise_hour',
          'gl_main_sunset_hour',
          'gl_main_lux_threshold',
          'gl_main_lux_hysteresis',
          'gl_main_min_on_s',
          'gl_main_min_off_s',
          'sw_gl_main_auto_mode',
          'gl_grow_target_light_minutes',
          'gl_grow_dli_target',
          'gl_grow_sunrise_hour',
          'gl_grow_sunset_hour',
          'gl_grow_lux_threshold',
          'gl_grow_lux_hysteresis',
          'gl_grow_min_on_s',
          'gl_grow_min_off_s',
          'sw_gl_grow_auto_mode'
      ]::text[])
    ORDER BY parameter, ts DESC
),
resolved AS (
    SELECT
        c.light_key,
        c.equipment,
        COALESCE(target_min.value, b.target_light_hours * 60.0)::double precision AS target_light_minutes,
        COALESCE(start_h.value, legacy_start.value, b.sunrise_hour)::integer AS start_hour,
        COALESCE(cutoff_h.value, legacy_cutoff.value, b.cutoff_hour)::integer AS cutoff_hour,
        COALESCE(
            lux_on.value,
            legacy_lux.value,
            r.current_gl_lux_threshold,
            r.recommended_gl_lux_threshold,
            40000.0
        )::double precision AS lux_on_threshold,
        COALESCE(
            lux_hyst.value,
            legacy_hyst.value,
            r.current_gl_lux_hysteresis,
            r.recommended_gl_lux_hysteresis,
            8000.0
        )::double precision AS lux_hysteresis,
        COALESCE(min_on.value, 120.0)::integer AS min_on_s,
        COALESCE(min_off.value, 60.0)::integer AS min_off_s,
        COALESCE(auto_mode.value, legacy_auto.value, 1.0) >= 0.5 AS auto_enabled,
        COALESCE(dli.value, legacy_dli.value, b.target_dli)::double precision AS legacy_dli_target
    FROM circuits c
    CROSS JOIN base b
    CROSS JOIN recommendation r
    LEFT JOIN latest_changes legacy_dli ON legacy_dli.parameter = 'gl_dli_target'
    LEFT JOIN latest_changes legacy_start ON legacy_start.parameter = 'gl_sunrise_hour'
    LEFT JOIN latest_changes legacy_cutoff ON legacy_cutoff.parameter = 'gl_sunset_hour'
    LEFT JOIN latest_changes legacy_lux ON legacy_lux.parameter = 'gl_lux_threshold'
    LEFT JOIN latest_changes legacy_hyst ON legacy_hyst.parameter = 'gl_lux_hysteresis'
    LEFT JOIN latest_changes legacy_auto ON legacy_auto.parameter = 'sw_gl_auto_mode'
    LEFT JOIN latest_changes target_min ON target_min.parameter = 'gl_' || c.light_key || '_target_light_minutes'
    LEFT JOIN latest_changes dli ON dli.parameter = 'gl_' || c.light_key || '_dli_target'
    LEFT JOIN latest_changes start_h ON start_h.parameter = 'gl_' || c.light_key || '_sunrise_hour'
    LEFT JOIN latest_changes cutoff_h ON cutoff_h.parameter = 'gl_' || c.light_key || '_sunset_hour'
    LEFT JOIN latest_changes lux_on ON lux_on.parameter = 'gl_' || c.light_key || '_lux_threshold'
    LEFT JOIN latest_changes lux_hyst ON lux_hyst.parameter = 'gl_' || c.light_key || '_lux_hysteresis'
    LEFT JOIN latest_changes min_on ON min_on.parameter = 'gl_' || c.light_key || '_min_on_s'
    LEFT JOIN latest_changes min_off ON min_off.parameter = 'gl_' || c.light_key || '_min_off_s'
    LEFT JOIN latest_changes auto_mode ON auto_mode.parameter = 'sw_gl_' || c.light_key || '_auto_mode'
)
SELECT
    p_greenhouse_id AS greenhouse_id,
    p_ts AS ts,
    r.light_key,
    r.equipment,
    greatest(0, least(1080, round(r.target_light_minutes)::integer)) AS target_light_minutes,
    greatest(0, least(23, r.start_hour)) AS start_hour,
    greatest(0, least(23, r.cutoff_hour)) AS cutoff_hour,
    greatest(100.0, least(100000.0, r.lux_on_threshold)) AS lux_on_threshold,
    greatest(0.0, least(25000.0, r.lux_hysteresis)) AS lux_hysteresis,
    greatest(100.0, least(100000.0, r.lux_on_threshold))
        + greatest(0.0, least(25000.0, r.lux_hysteresis)) AS lux_off_threshold,
    greatest(0, least(3600, r.min_on_s)) AS min_on_s,
    greatest(0, least(3600, r.min_off_s)) AS min_off_s,
    r.auto_enabled,
    greatest(1.0, least(50.0, r.legacy_dli_target)) AS legacy_dli_target,
    'active crops.target_dli -> target_light_minutes default; Tempest outdoor_lux + planner per-circuit minutes/threshold tunables -> dispatcher/API -> ESP32 per-circuit qualified-minutes state machines -> Lutron switches -> equipment_state'::text
        AS source_chain,
    'Each circuit starts counting at sunrise. A minute qualifies once when natural lux is at or above the ON threshold OR the actual switch is ON. The circuit turns ON below threshold until target_light_minutes is met, with ON+hysteresis as the OFF threshold.'::text
        AS controller_contract
FROM resolved r;
$$;

COMMENT ON FUNCTION fn_lighting_minutes_policy(timestamptz, text) IS
    'Per-circuit qualified-light-minutes policy. This is the primary lighting-control contract replacing DLI-gated enforcement.';

CREATE OR REPLACE VIEW v_lighting_qualified_minutes_daily AS
WITH policy AS (
    SELECT * FROM fn_lighting_minutes_policy(now(), 'vallery')
),
days AS (
    SELECT generate_series(
        (now() AT TIME ZONE 'America/Denver')::date - 14,
        (now() AT TIME ZONE 'America/Denver')::date,
        interval '1 day'
    )::date AS local_date
),
windows AS (
    SELECT
        d.local_date,
        p.light_key,
        p.equipment,
        p.target_light_minutes,
        p.start_hour,
        p.cutoff_hour,
        p.lux_on_threshold,
        p.lux_hysteresis,
        p.lux_off_threshold,
        (d.local_date + make_interval(hours => p.start_hour)) AT TIME ZONE 'America/Denver' AS start_ts,
        LEAST(
            (d.local_date + make_interval(hours => p.cutoff_hour)) AT TIME ZONE 'America/Denver',
            now()
        ) AS end_ts
    FROM days d
    CROSS JOIN policy p
    WHERE (d.local_date + make_interval(hours => p.start_hour)) AT TIME ZONE 'America/Denver' < now()
),
lux_min AS (
    SELECT
        time_bucket('1 minute', c.ts) AS minute_ts,
        avg(COALESCE(c.outdoor_lux, c.lux)) AS natural_lux
    FROM climate c
    WHERE c.greenhouse_id = 'vallery'
      AND c.ts >= (SELECT min(start_ts) FROM windows)
      AND c.ts <= (SELECT max(end_ts) FROM windows)
      AND COALESCE(c.outdoor_lux, c.lux) IS NOT NULL
    GROUP BY 1
),
lux_samples AS (
    SELECT
        w.local_date,
        w.light_key,
        w.equipment,
        w.target_light_minutes,
        w.start_hour,
        w.cutoff_hour,
        w.lux_on_threshold,
        w.lux_hysteresis,
        w.lux_off_threshold,
        lm.minute_ts,
        lm.natural_lux,
        lm.natural_lux >= w.lux_on_threshold AS natural_qualified
    FROM windows w
    JOIN lux_min lm
      ON lm.minute_ts >= w.start_ts
     AND lm.minute_ts < w.end_ts
),
state_seed AS (
    SELECT
        w.local_date,
        w.light_key,
        w.equipment,
        w.start_ts AS ts,
        COALESCE((
            SELECT e.state
            FROM equipment_state e
            WHERE e.greenhouse_id = 'vallery'
              AND e.equipment = w.equipment
              AND e.ts <= w.start_ts
            ORDER BY e.ts DESC
            LIMIT 1
        ), false) AS state
    FROM windows w
),
state_events AS (
    SELECT w.local_date, w.light_key, w.equipment, e.ts, e.state
    FROM windows w
    JOIN equipment_state e
      ON e.greenhouse_id = 'vallery'
     AND e.equipment = w.equipment
     AND e.ts >= w.start_ts
     AND e.ts <= w.end_ts
),
state_timeline AS (
    SELECT
        x.local_date,
        x.light_key,
        x.equipment,
        x.ts,
        x.state,
        lead(x.ts, 1, w.end_ts) OVER (
            PARTITION BY x.local_date, x.light_key, x.equipment
            ORDER BY x.ts
        ) AS next_ts
    FROM (
        SELECT * FROM state_seed
        UNION ALL
        SELECT * FROM state_events
    ) x
    JOIN windows w
      ON w.local_date = x.local_date
     AND w.light_key = x.light_key
     AND w.equipment = x.equipment
),
state_segments AS (
    SELECT
        st.local_date,
        st.light_key,
        st.equipment,
        GREATEST(st.ts, w.start_ts) AS start_ts,
        LEAST(st.next_ts, w.end_ts) AS end_ts
    FROM state_timeline st
    JOIN windows w
      ON w.local_date = st.local_date
     AND w.light_key = st.light_key
     AND w.equipment = st.equipment
    WHERE st.state IS TRUE
      AND st.ts < w.end_ts
      AND st.next_ts > w.start_ts
),
switch_minutes AS (
    SELECT
        w.local_date,
        w.light_key,
        w.equipment,
        COALESCE(round((sum(extract(epoch FROM s.end_ts - s.start_ts)) / 60.0)::numeric, 0), 0)::integer AS switch_on_minutes
    FROM windows w
    LEFT JOIN state_segments s
      ON s.local_date = w.local_date
     AND s.light_key = w.light_key
     AND s.equipment = w.equipment
    GROUP BY w.local_date, w.light_key, w.equipment
),
minute_join AS (
    SELECT
        ls.*,
        s.start_ts IS NOT NULL AS switch_on
    FROM lux_samples ls
    LEFT JOIN state_segments s
      ON s.local_date = ls.local_date
     AND s.light_key = ls.light_key
     AND s.equipment = ls.equipment
     AND s.start_ts < ls.minute_ts + interval '1 minute'
     AND s.end_ts > ls.minute_ts
),
minute_rollup AS (
    SELECT
        local_date,
        light_key,
        equipment,
        max(target_light_minutes)::integer AS target_light_minutes,
        count(DISTINCT minute_ts)::integer AS observed_minutes,
        count(DISTINCT minute_ts) FILTER (WHERE natural_qualified)::integer AS natural_qualified_minutes,
        count(DISTINCT minute_ts) FILTER (WHERE natural_qualified AND switch_on)::integer AS overlap_minutes,
        count(DISTINCT minute_ts) FILTER (WHERE natural_qualified OR switch_on)::integer AS qualified_light_minutes,
        count(DISTINCT minute_ts) FILTER (WHERE NOT natural_qualified AND NOT switch_on)::integer AS below_threshold_off_minutes,
        round(avg(natural_lux)::numeric, 0) AS avg_natural_lux,
        max(start_hour)::integer AS start_hour,
        max(cutoff_hour)::integer AS cutoff_hour,
        max(lux_on_threshold)::double precision AS lux_on_threshold,
        max(lux_hysteresis)::double precision AS lux_hysteresis,
        max(lux_off_threshold)::double precision AS lux_off_threshold
    FROM minute_join
    GROUP BY local_date, light_key, equipment
)
SELECT
    w.local_date,
    w.light_key,
    w.equipment,
    w.target_light_minutes,
    COALESCE(m.observed_minutes, 0) AS observed_minutes,
    COALESCE(m.natural_qualified_minutes, 0) AS natural_qualified_minutes,
    COALESCE(s.switch_on_minutes, 0) AS switch_on_minutes,
    COALESCE(m.overlap_minutes, 0) AS overlap_minutes,
    (COALESCE(m.natural_qualified_minutes, 0) + COALESCE(s.switch_on_minutes, 0) - COALESCE(m.overlap_minutes, 0))::integer AS qualified_light_minutes,
    greatest(
        0,
        w.target_light_minutes
          - (COALESCE(m.natural_qualified_minutes, 0) + COALESCE(s.switch_on_minutes, 0) - COALESCE(m.overlap_minutes, 0))::integer
    ) AS remaining_light_minutes,
    COALESCE(m.below_threshold_off_minutes, 0) AS below_threshold_off_minutes,
    m.avg_natural_lux,
    w.start_hour,
    w.cutoff_hour,
    w.lux_on_threshold,
    w.lux_hysteresis,
    w.lux_off_threshold,
    now() AS computed_at
FROM windows w
LEFT JOIN minute_rollup m
  ON m.local_date = w.local_date
 AND m.light_key = w.light_key
 AND m.equipment = w.equipment
LEFT JOIN switch_minutes s
  ON s.local_date = w.local_date
 AND s.light_key = w.light_key
 AND s.equipment = w.equipment;

COMMENT ON VIEW v_lighting_qualified_minutes_daily IS
    'Per-circuit daily qualified light minutes from climate outdoor_lux and actual Lutron equipment_state. Natural and switch minutes use OR semantics to avoid double counting.';

DROP VIEW IF EXISTS v_lighting_minutes_status_now;

CREATE OR REPLACE VIEW v_lighting_minutes_status_now AS
WITH policy AS (
    SELECT * FROM fn_lighting_minutes_policy(now(), 'vallery')
),
today_window AS (
    SELECT
        p.light_key,
        p.equipment,
        p.target_light_minutes,
        p.start_hour,
        p.cutoff_hour,
        p.lux_on_threshold,
        p.lux_hysteresis,
        p.lux_off_threshold,
        ((now() AT TIME ZONE 'America/Denver')::date + make_interval(hours => p.start_hour)) AT TIME ZONE 'America/Denver' AS start_ts,
        LEAST(
            ((now() AT TIME ZONE 'America/Denver')::date + make_interval(hours => p.cutoff_hour)) AT TIME ZONE 'America/Denver',
            now()
        ) AS end_ts
    FROM policy p
),
minute_grid AS (
    SELECT
        w.*,
        gs.minute_ts
    FROM today_window w
    LEFT JOIN LATERAL generate_series(
        w.start_ts,
        w.end_ts - interval '1 minute',
        interval '1 minute'
    ) AS gs(minute_ts) ON w.end_ts > w.start_ts
),
lux_min AS (
    SELECT
        time_bucket('1 minute', c.ts) AS minute_ts,
        avg(COALESCE(c.outdoor_lux, c.lux)) AS natural_lux
    FROM climate c
    WHERE c.greenhouse_id = 'vallery'
      AND c.ts >= (SELECT min(start_ts) FROM today_window)
      AND c.ts <= (SELECT max(end_ts) FROM today_window)
      AND COALESCE(c.outdoor_lux, c.lux) IS NOT NULL
    GROUP BY 1
),
state_seed AS (
    SELECT
        w.light_key,
        w.equipment,
        w.start_ts AS ts,
        COALESCE((
            SELECT e.state
            FROM equipment_state e
            WHERE e.greenhouse_id = 'vallery'
              AND e.equipment = w.equipment
              AND e.ts <= w.start_ts
            ORDER BY e.ts DESC
            LIMIT 1
        ), false) AS state
    FROM today_window w
),
state_events AS (
    SELECT w.light_key, w.equipment, e.ts, e.state
    FROM today_window w
    JOIN equipment_state e
      ON e.greenhouse_id = 'vallery'
     AND e.equipment = w.equipment
     AND e.ts >= w.start_ts
     AND e.ts <= w.end_ts
),
state_timeline AS (
    SELECT
        x.light_key,
        x.equipment,
        x.ts,
        x.state,
        lead(x.ts, 1, w.end_ts) OVER (
            PARTITION BY x.light_key, x.equipment
            ORDER BY x.ts
        ) AS next_ts
    FROM (
        SELECT * FROM state_seed
        UNION ALL
        SELECT * FROM state_events
    ) x
    JOIN today_window w
      ON w.light_key = x.light_key
     AND w.equipment = x.equipment
),
state_segments AS (
    SELECT
        st.light_key,
        st.equipment,
        GREATEST(st.ts, w.start_ts) AS start_ts,
        LEAST(st.next_ts, w.end_ts) AS end_ts
    FROM state_timeline st
    JOIN today_window w
      ON w.light_key = st.light_key
     AND w.equipment = st.equipment
    WHERE st.state IS TRUE
      AND st.ts < w.end_ts
      AND st.next_ts > w.start_ts
),
minute_eval AS (
    SELECT
        mg.light_key,
        mg.equipment,
        mg.minute_ts,
        COALESCE(lm.natural_lux, 0.0) >= mg.lux_on_threshold AS natural_qualified,
        EXISTS (
            SELECT 1
            FROM state_segments s
            WHERE s.light_key = mg.light_key
              AND s.equipment = mg.equipment
              AND s.start_ts < mg.minute_ts + interval '1 minute'
              AND s.end_ts > mg.minute_ts
        ) AS switch_on
    FROM minute_grid mg
    LEFT JOIN lux_min lm
      ON lm.minute_ts = mg.minute_ts
),
today AS (
    SELECT
        w.light_key,
        w.equipment,
        count(me.minute_ts)::integer AS observed_minutes,
        count(me.minute_ts) FILTER (WHERE me.natural_qualified)::integer AS natural_qualified_minutes,
        count(me.minute_ts) FILTER (WHERE me.switch_on)::integer AS switch_on_minutes,
        count(me.minute_ts) FILTER (WHERE me.natural_qualified AND me.switch_on)::integer AS overlap_minutes,
        count(me.minute_ts) FILTER (WHERE me.natural_qualified OR me.switch_on)::integer AS qualified_light_minutes,
        count(me.minute_ts) FILTER (WHERE NOT me.natural_qualified AND NOT me.switch_on)::integer AS below_threshold_off_minutes
    FROM today_window w
    LEFT JOIN minute_eval me
      ON me.light_key = w.light_key
     AND me.equipment = w.equipment
    GROUP BY w.light_key, w.equipment
),
latest_climate AS (
    SELECT ts, dli_today, lux, outdoor_lux
    FROM climate
    WHERE greenhouse_id = 'vallery'
    ORDER BY ts DESC
    LIMIT 1
),
latest_equipment AS (
    SELECT DISTINCT ON (equipment) equipment, state, ts
    FROM equipment_state
    WHERE greenhouse_id = 'vallery'
      AND equipment IN ('grow_light_main', 'grow_light_grow')
    ORDER BY equipment, ts DESC
),
current_firmware_start AS (
    WITH firmware_ordered AS (
        SELECT
            ts,
            firmware_version,
            lag(firmware_version) OVER (ORDER BY ts) AS previous_firmware_version
        FROM diagnostics
        WHERE firmware_version IS NOT NULL
          AND firmware_version <> ''
          AND ts > now() - interval '30 days'
    ),
    current_firmware AS (
        SELECT firmware_version
        FROM diagnostics
        WHERE firmware_version IS NOT NULL
          AND firmware_version <> ''
        ORDER BY ts DESC
        LIMIT 1
    )
    SELECT max(fo.ts) AS ts
    FROM firmware_ordered fo
    CROSS JOIN current_firmware cf
    WHERE fo.firmware_version = cf.firmware_version
      AND fo.previous_firmware_version IS DISTINCT FROM fo.firmware_version
),
latest_reason AS (
    SELECT DISTINCT ON (entity) entity, value, ts
    FROM system_state
    WHERE entity IN ('gl_main_state', 'gl_main_reason', 'gl_grow_state', 'gl_grow_reason')
    ORDER BY entity, ts DESC
)
SELECT
    p.*,
    COALESCE(t.qualified_light_minutes, 0) AS qualified_light_minutes,
    COALESCE(t.natural_qualified_minutes, 0) AS natural_qualified_minutes,
    COALESCE(t.switch_on_minutes, 0) AS switch_on_minutes,
    COALESCE(t.overlap_minutes, 0) AS overlap_minutes,
    greatest(0, p.target_light_minutes - COALESCE(t.qualified_light_minutes, 0)) AS remaining_light_minutes,
    c.ts AS climate_ts,
    c.dli_today,
    c.lux AS indoor_lux,
    c.outdoor_lux,
    COALESCE(c.outdoor_lux, c.lux, 0.0) AS natural_lux,
    COALESCE(c.outdoor_lux, c.lux, 0.0) >= p.lux_on_threshold AS natural_qualified_now,
    EXTRACT(hour FROM now() AT TIME ZONE 'America/Denver')::integer AS local_hour,
    CASE
        WHEN p.start_hour <= p.cutoff_hour THEN
            EXTRACT(hour FROM now() AT TIME ZONE 'America/Denver')::integer >= p.start_hour
            AND EXTRACT(hour FROM now() AT TIME ZONE 'America/Denver')::integer < p.cutoff_hour
        ELSE
            EXTRACT(hour FROM now() AT TIME ZONE 'America/Denver')::integer >= p.start_hour
            OR EXTRACT(hour FROM now() AT TIME ZONE 'America/Denver')::integer < p.cutoff_hour
    END AS in_light_window,
    COALESCE(t.qualified_light_minutes, 0) < p.target_light_minutes AS minutes_below_target,
    COALESCE(c.outdoor_lux, c.lux, 0.0) < p.lux_on_threshold AS lux_below_on_threshold,
    COALESCE(c.outdoor_lux, c.lux, 0.0) < p.lux_off_threshold AS lux_below_off_threshold,
    (
        p.auto_enabled
        AND (
            CASE
                WHEN p.start_hour <= p.cutoff_hour THEN
                    EXTRACT(hour FROM now() AT TIME ZONE 'America/Denver')::integer >= p.start_hour
                    AND EXTRACT(hour FROM now() AT TIME ZONE 'America/Denver')::integer < p.cutoff_hour
                ELSE
                    EXTRACT(hour FROM now() AT TIME ZONE 'America/Denver')::integer >= p.start_hour
                    OR EXTRACT(hour FROM now() AT TIME ZONE 'America/Denver')::integer < p.cutoff_hour
            END
        )
        AND COALESCE(t.qualified_light_minutes, 0) < p.target_light_minutes
        AND (
            COALESCE(c.outdoor_lux, c.lux, 0.0) < p.lux_on_threshold
            OR (
                COALESCE(e.state, false)
                OR upper(COALESCE(state_row.value, '')) = 'ON'
            ) AND COALESCE(c.outdoor_lux, c.lux, 0.0) < p.lux_off_threshold
        )
    ) AS expected_on,
    COALESCE(e.state, false) AS actual_on,
    state_row.value AS firmware_state,
    reason_row.value AS firmware_reason,
    (
        state_row.ts >= COALESCE((SELECT ts FROM current_firmware_start), now() - interval '24 hours')
        AND reason_row.ts >= COALESCE((SELECT ts FROM current_firmware_start), now() - interval '24 hours')
        AND state_row.ts > now() - interval '15 minutes'
        AND reason_row.ts > now() - interval '15 minutes'
    ) AS firmware_telemetry_fresh,
    e.ts AS equipment_ts
FROM policy p
LEFT JOIN today t
  ON t.light_key = p.light_key
 AND t.equipment = p.equipment
LEFT JOIN latest_climate c ON true
LEFT JOIN latest_equipment e ON e.equipment = p.equipment
LEFT JOIN latest_reason state_row ON state_row.entity = 'gl_' || p.light_key || '_state'
LEFT JOIN latest_reason reason_row ON reason_row.entity = 'gl_' || p.light_key || '_reason';

COMMENT ON VIEW v_lighting_minutes_status_now IS
    'Current per-circuit qualified-light-minutes policy, minutes progress, expected state, firmware text state, and actual Lutron switch state.';

CREATE OR REPLACE VIEW v_equipment_runtime_daily AS
WITH transitions AS (
    SELECT
        (ts AT TIME ZONE 'America/Denver')::date AS day,
        equipment,
        ts,
        state,
        lag(state) OVER (
            PARTITION BY equipment, (ts AT TIME ZONE 'America/Denver')::date
            ORDER BY ts
        ) AS prev_state,
        lead(ts) OVER (
            PARTITION BY equipment, (ts AT TIME ZONE 'America/Denver')::date
            ORDER BY ts
        ) AS next_ts
    FROM equipment_state
    WHERE equipment IN (
        'fan1','fan2','heat1','heat2','fog','vent',
        'mister_south','mister_west','mister_center',
        'grow_light_main','grow_light_grow',
        'drip_wall','drip_center'
    )
)
SELECT
    day,
    equipment,
    round(
        (
            sum(
                extract(epoch FROM LEAST(
                    COALESCE(next_ts, (day + 1)::timestamp AT TIME ZONE 'America/Denver'),
                    now()
                ) - ts)
                / 60.0
            ) FILTER (WHERE state IS TRUE)
        )::numeric,
        1
    ) AS on_minutes,
    count(*) FILTER (WHERE state IS TRUE AND COALESCE(prev_state, false) IS FALSE) AS cycles
FROM transitions
WHERE ts <= now()
GROUP BY day, equipment;

COMMENT ON VIEW v_equipment_runtime_daily IS
    'Daily equipment runtime from equipment_state transitions. Runtime integrates TRUE spans only up to now for the current day; cycles count TRUE rising edges only.';
