-- Migration 123: per-circuit lighting state-machine policy and timeline
--
-- The ESP32 now evaluates the two Lutron lighting circuits independently.
-- Crop policy seeds the defaults; Iris may tune each circuit's goal, lux
-- thresholds, window, dwell, and auto mode through normal setpoint plumbing.

CREATE OR REPLACE FUNCTION fn_lighting_circuit_policy(
    p_ts timestamptz DEFAULT now(),
    p_greenhouse_id text DEFAULT 'vallery'
)
RETURNS TABLE (
    greenhouse_id text,
    ts timestamptz,
    light_key text,
    equipment text,
    dli_target double precision,
    start_hour integer,
    cutoff_hour integer,
    lux_on_threshold double precision,
    lux_hysteresis double precision,
    lux_off_threshold double precision,
    min_on_s integer,
    min_off_s integer,
    auto_enabled boolean,
    source_chain text,
    controller_contract text
)
LANGUAGE sql
STABLE
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
    ORDER BY parameter, ts DESC
),
resolved AS (
    SELECT
        c.light_key,
        c.equipment,
        COALESCE(dli.value, legacy_dli.value, b.target_dli)::double precision AS dli_target,
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
        COALESCE(auto_mode.value, legacy_auto.value, 1.0) >= 0.5 AS auto_enabled
    FROM circuits c
    CROSS JOIN base b
    CROSS JOIN recommendation r
    LEFT JOIN latest_changes legacy_dli ON legacy_dli.parameter = 'gl_dli_target'
    LEFT JOIN latest_changes legacy_start ON legacy_start.parameter = 'gl_sunrise_hour'
    LEFT JOIN latest_changes legacy_cutoff ON legacy_cutoff.parameter = 'gl_sunset_hour'
    LEFT JOIN latest_changes legacy_lux ON legacy_lux.parameter = 'gl_lux_threshold'
    LEFT JOIN latest_changes legacy_hyst ON legacy_hyst.parameter = 'gl_lux_hysteresis'
    LEFT JOIN latest_changes legacy_auto ON legacy_auto.parameter = 'sw_gl_auto_mode'
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
    greatest(1.0, least(50.0, r.dli_target)) AS dli_target,
    greatest(0, least(23, r.start_hour)) AS start_hour,
    greatest(0, least(23, r.cutoff_hour)) AS cutoff_hour,
    greatest(100.0, least(100000.0, r.lux_on_threshold)) AS lux_on_threshold,
    greatest(0.0, least(25000.0, r.lux_hysteresis)) AS lux_hysteresis,
    greatest(100.0, least(100000.0, r.lux_on_threshold))
        + greatest(0.0, least(25000.0, r.lux_hysteresis)) AS lux_off_threshold,
    greatest(0, least(3600, r.min_on_s)) AS min_on_s,
    greatest(0, least(3600, r.min_off_s)) AS min_off_s,
    r.auto_enabled,
    'active crops.target_dli + Tempest lux history -> fn_lighting_circuit_policy() -> planner/default setpoints -> dispatcher/API -> ESP32 per-circuit lighting state machines -> Lutron switches -> equipment_state'::text
        AS source_chain,
    'Each circuit turns on independently inside its window when DLI is below its goal and Tempest outdoor lux is below its ON threshold; each circuit holds until lux reaches ON+hysteresis or the window/DLI/auto gate exits.'::text
        AS controller_contract
FROM resolved r;
$$;

COMMENT ON FUNCTION fn_lighting_circuit_policy(timestamptz, text) IS
    'Per-circuit lighting policy for ESP32 lighting state machines. Crop/DLI policy seeds defaults; planner-managed gl_main_* and gl_grow_* setpoints can diverge each circuit.';

CREATE OR REPLACE VIEW v_lighting_circuit_status_now AS
WITH policy AS (
    SELECT * FROM fn_lighting_circuit_policy(now(), 'vallery')
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
    WHERE equipment IN ('grow_light_main', 'grow_light_grow')
    ORDER BY equipment, ts DESC
),
latest_reason AS (
    SELECT DISTINCT ON (entity) entity, value, ts
    FROM system_state
    WHERE entity IN ('gl_main_state', 'gl_main_reason', 'gl_grow_state', 'gl_grow_reason')
    ORDER BY entity, ts DESC
)
SELECT
    p.*,
    c.ts AS climate_ts,
    c.dli_today,
    c.lux AS indoor_lux,
    c.outdoor_lux,
    COALESCE(c.outdoor_lux, c.lux, 0.0) AS natural_lux,
    EXTRACT(hour FROM now() AT TIME ZONE 'America/Denver')::integer AS local_hour,
    CASE
        WHEN p.start_hour <= p.cutoff_hour THEN
            EXTRACT(hour FROM now() AT TIME ZONE 'America/Denver')::integer >= p.start_hour
            AND EXTRACT(hour FROM now() AT TIME ZONE 'America/Denver')::integer < p.cutoff_hour
        ELSE
            EXTRACT(hour FROM now() AT TIME ZONE 'America/Denver')::integer >= p.start_hour
            OR EXTRACT(hour FROM now() AT TIME ZONE 'America/Denver')::integer < p.cutoff_hour
    END AS in_light_window,
    COALESCE(c.dli_today, 0.0) < p.dli_target AS dli_below_target,
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
        AND COALESCE(c.dli_today, 0.0) < p.dli_target
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
    e.ts AS equipment_ts
FROM policy p
LEFT JOIN latest_climate c ON true
LEFT JOIN latest_equipment e ON e.equipment = p.equipment
LEFT JOIN latest_reason state_row ON state_row.entity = 'gl_' || p.light_key || '_state'
LEFT JOIN latest_reason reason_row ON reason_row.entity = 'gl_' || p.light_key || '_reason';

COMMENT ON VIEW v_lighting_circuit_status_now IS
    'Current per-circuit lighting policy, expected state, firmware text state, and actual Lutron equipment_state.';

CREATE OR REPLACE VIEW v_lighting_status_now AS
WITH policy AS (
    SELECT * FROM fn_lighting_policy(now(), 'vallery')
),
circuits AS (
    SELECT * FROM v_lighting_circuit_status_now
),
main AS (
    SELECT * FROM circuits WHERE light_key = 'main'
),
grow AS (
    SELECT * FROM circuits WHERE light_key = 'grow'
)
SELECT
    policy.*,
    main.climate_ts,
    main.dli_today,
    main.indoor_lux AS lux,
    main.outdoor_lux,
    main.lux_on_threshold AS gl_lux_threshold,
    main.lux_hysteresis AS gl_lux_hysteresis,
    main.actual_on AS grow_light_main_on,
    grow.actual_on AS grow_light_grow_on,
    main.local_hour,
    main.in_light_window,
    main.dli_below_target,
    main.lux_below_on_threshold AS lux_below_threshold,
    main.expected_on OR grow.expected_on AS expected_lights_on,
    main.dli_target AS main_dli_target,
    main.start_hour AS main_start_hour,
    main.cutoff_hour AS main_cutoff_hour,
    main.lux_on_threshold AS main_lux_on_threshold,
    main.lux_off_threshold AS main_lux_off_threshold,
    main.lux_hysteresis AS main_lux_hysteresis,
    main.expected_on AS main_expected_on,
    main.firmware_state AS main_firmware_state,
    main.firmware_reason AS main_firmware_reason,
    grow.dli_target AS grow_dli_target,
    grow.start_hour AS grow_start_hour,
    grow.cutoff_hour AS grow_cutoff_hour,
    grow.lux_on_threshold AS grow_lux_on_threshold,
    grow.lux_off_threshold AS grow_lux_off_threshold,
    grow.lux_hysteresis AS grow_lux_hysteresis,
    grow.expected_on AS grow_expected_on,
    grow.firmware_state AS grow_firmware_state,
    grow.firmware_reason AS grow_firmware_reason
FROM policy
CROSS JOIN main
CROSS JOIN grow;

COMMENT ON VIEW v_lighting_status_now IS
    'Compatibility one-row lighting status with per-circuit policy, expected state, and Lutron state.';

DROP VIEW IF EXISTS v_lighting_daily;

CREATE OR REPLACE VIEW v_lighting_daily AS
WITH runtime AS (
    SELECT *
    FROM v_equipment_runtime_daily
    WHERE equipment IN ('grow_light_main', 'grow_light_grow')
)
SELECT
    ds.date,
    (ds.date + time '12:00')::timestamptz AS ts,
    ds.dli_final AS sensor_dli,
    ds.runtime_grow_light_min / 60.0 AS grow_light_hours,
    COALESCE(main_rt.on_minutes, 0.0) / 60.0 AS main_light_hours,
    COALESCE(grow_rt.on_minutes, 0.0) / 60.0 AS grow_light_circuit_hours,
    COALESCE(main_rt.cycles, 0) AS main_light_cycles,
    COALESCE(grow_rt.cycles, 0) AS grow_light_circuit_cycles,
    p.target_dli,
    p.target_light_hours,
    p.sunrise_hour,
    p.natural_sunset_hour,
    p.cutoff_hour,
    p.max_crop_name
FROM daily_summary ds
CROSS JOIN LATERAL fn_lighting_policy((ds.date + time '12:00')::timestamptz, 'vallery') p
LEFT JOIN runtime main_rt ON main_rt.day = ds.date AND main_rt.equipment = 'grow_light_main'
LEFT JOIN runtime grow_rt ON grow_rt.day = ds.date AND grow_rt.equipment = 'grow_light_grow'
WHERE ds.dli_final IS NOT NULL;

COMMENT ON VIEW v_lighting_daily IS
    'Daily DLI and separate lighting-circuit runtimes joined to crop-driven lighting policy.';

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
WITH series AS (
    SELECT generate_series(p_start, p_end, p_step) AS ts
),
timeline AS (
    SELECT
        s.ts,
        obs.natural_lux AS observed_lux,
        fcst.natural_lux AS forecast_lux
    FROM series s
    LEFT JOIN LATERAL (
        SELECT avg(COALESCE(c.outdoor_lux, c.lux))::double precision AS natural_lux
        FROM climate c
        WHERE c.ts >= s.ts
          AND c.ts < s.ts + p_step
          AND c.ts <= now()
          AND COALESCE(c.greenhouse_id, p_greenhouse_id) = p_greenhouse_id
          AND COALESCE(c.outdoor_lux, c.lux) IS NOT NULL
    ) obs ON s.ts <= now()
    LEFT JOIN LATERAL (
        SELECT (wf.solar_w_m2 * 120.0)::double precision AS natural_lux
        FROM weather_forecast wf
        WHERE wf.ts >= s.ts - p_step / 2
          AND wf.ts < s.ts + p_step / 2
          AND wf.ts > now()
          AND wf.solar_w_m2 IS NOT NULL
        ORDER BY wf.fetched_at DESC
        LIMIT 1
    ) fcst ON s.ts > now()
),
policy AS (
    SELECT
        t.ts,
        COALESCE(t.observed_lux, t.forecast_lux, 0.0) AS natural_lux,
        CASE
            WHEN t.observed_lux IS NOT NULL THEN 'tempest_observed'
            WHEN t.forecast_lux IS NOT NULL THEN 'forecast_solar_w_m2_x120'
            ELSE 'missing'
        END AS natural_lux_source,
        main.dli_target AS main_dli_target,
        main.start_hour AS main_start_hour,
        main.cutoff_hour AS main_cutoff_hour,
        main.lux_on_threshold AS main_lux_on_threshold,
        main.lux_off_threshold AS main_lux_off_threshold,
        grow.dli_target AS grow_dli_target,
        grow.start_hour AS grow_start_hour,
        grow.cutoff_hour AS grow_cutoff_hour,
        grow.lux_on_threshold AS grow_lux_on_threshold,
        grow.lux_off_threshold AS grow_lux_off_threshold
    FROM timeline t
    JOIN LATERAL (
        SELECT * FROM fn_lighting_circuit_policy(t.ts, p_greenhouse_id)
        WHERE light_key = 'main'
    ) main ON true
    JOIN LATERAL (
        SELECT * FROM fn_lighting_circuit_policy(t.ts, p_greenhouse_id)
        WHERE light_key = 'grow'
    ) grow ON true
)
SELECT
    p.ts,
    NULLIF(p.natural_lux, 0.0) AS natural_lux,
    p.natural_lux_source,
    p.main_lux_on_threshold,
    p.main_lux_off_threshold,
    p.grow_lux_on_threshold,
    p.grow_lux_off_threshold,
    CASE
        WHEN (
            CASE
                WHEN p.main_start_hour <= p.main_cutoff_hour THEN
                    EXTRACT(hour FROM p.ts AT TIME ZONE 'America/Denver')::integer >= p.main_start_hour
                    AND EXTRACT(hour FROM p.ts AT TIME ZONE 'America/Denver')::integer < p.main_cutoff_hour
                ELSE
                    EXTRACT(hour FROM p.ts AT TIME ZONE 'America/Denver')::integer >= p.main_start_hour
                    OR EXTRACT(hour FROM p.ts AT TIME ZONE 'America/Denver')::integer < p.main_cutoff_hour
            END
        ) AND p.natural_lux < p.main_lux_on_threshold THEN 1.0 ELSE 0.0 END AS main_expected_on,
    CASE
        WHEN (
            CASE
                WHEN p.grow_start_hour <= p.grow_cutoff_hour THEN
                    EXTRACT(hour FROM p.ts AT TIME ZONE 'America/Denver')::integer >= p.grow_start_hour
                    AND EXTRACT(hour FROM p.ts AT TIME ZONE 'America/Denver')::integer < p.grow_cutoff_hour
                ELSE
                    EXTRACT(hour FROM p.ts AT TIME ZONE 'America/Denver')::integer >= p.grow_start_hour
                    OR EXTRACT(hour FROM p.ts AT TIME ZONE 'America/Denver')::integer < p.grow_cutoff_hour
            END
        ) AND p.natural_lux < p.grow_lux_on_threshold THEN 1.0 ELSE 0.0 END AS grow_expected_on,
    p.main_dli_target,
    p.grow_dli_target
FROM policy p
ORDER BY p.ts;
$$;

COMMENT ON FUNCTION fn_lighting_timeline(timestamptz, timestamptz, interval, text) IS
    'Historical Tempest lux plus forecast solar-derived lux joined to per-circuit lighting thresholds for Grafana/homepage lighting forecast bands.';
