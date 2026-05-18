-- Migration 128: lighting traceability uses confirmed/readback state
--
-- `fn_lighting_minutes_policy` is used by public panels and the ESP32 pull
-- endpoint as the controller-facing lighting policy. It must not let stale
-- pending rows override confirmed cfg readbacks. Pending desired rows remain
-- visible through `v_lighting_traceability_now`.

ALTER TABLE diagnostics
    ADD COLUMN IF NOT EXISTS controller_time_epoch bigint,
    ADD COLUMN IF NOT EXISTS controller_local_hour integer,
    ADD COLUMN IF NOT EXISTS sntp_valid integer,
    ADD COLUMN IF NOT EXISTS sntp_miss_count integer,
    ADD COLUMN IF NOT EXISTS last_sntp_sync_age_s integer;

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
tracked_params AS (
    SELECT unnest(ARRAY[
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
    ]::text[]) AS parameter
),
latest_snapshot AS (
    SELECT DISTINCT ON (ss.parameter)
        ss.parameter,
        ss.value::double precision AS value,
        ss.ts,
        1 AS source_rank
    FROM setpoint_snapshot ss
    JOIN tracked_params tp ON tp.parameter = ss.parameter
    WHERE COALESCE(ss.greenhouse_id, p_greenhouse_id) = p_greenhouse_id
    ORDER BY ss.parameter, ss.ts DESC
),
latest_confirmed_changes AS (
    SELECT DISTINCT ON (sc.parameter)
        sc.parameter,
        sc.value::double precision AS value,
        COALESCE(sc.confirmed_at, sc.ts) AS ts,
        2 AS source_rank
    FROM setpoint_changes sc
    JOIN tracked_params tp ON tp.parameter = sc.parameter
    WHERE COALESCE(sc.greenhouse_id, p_greenhouse_id) = p_greenhouse_id
      AND COALESCE(sc.source, '') <> 'esp32'
      AND (
          sc.confirmed_at IS NOT NULL
          OR COALESCE(sc.delivery_status, '') = 'confirmed'
      )
      AND COALESCE(sc.delivery_status, '') NOT IN ('pending', 'superseded', 'expired', 'deferred_heap_pressure')
    ORDER BY sc.parameter, COALESCE(sc.confirmed_at, sc.ts) DESC
),
latest_switch_actual AS (
    SELECT
        'sw_gl_auto_mode'::text AS parameter,
        CASE WHEN e.state THEN 1.0 ELSE 0.0 END AS value,
        e.ts,
        0 AS source_rank
    FROM (
        SELECT DISTINCT ON (equipment) equipment, state, ts
        FROM equipment_state
        WHERE COALESCE(greenhouse_id, p_greenhouse_id) = p_greenhouse_id
          AND equipment = 'gl_auto_mode'
        ORDER BY equipment, ts DESC
    ) e
),
latest_values AS (
    SELECT DISTINCT ON (parameter)
        parameter,
        value
    FROM (
        SELECT * FROM latest_switch_actual
        UNION ALL
        SELECT * FROM latest_snapshot
        UNION ALL
        SELECT * FROM latest_confirmed_changes
    ) values_union
    ORDER BY parameter, source_rank, ts DESC
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
    LEFT JOIN latest_values legacy_dli ON legacy_dli.parameter = 'gl_dli_target'
    LEFT JOIN latest_values legacy_start ON legacy_start.parameter = 'gl_sunrise_hour'
    LEFT JOIN latest_values legacy_cutoff ON legacy_cutoff.parameter = 'gl_sunset_hour'
    LEFT JOIN latest_values legacy_lux ON legacy_lux.parameter = 'gl_lux_threshold'
    LEFT JOIN latest_values legacy_hyst ON legacy_hyst.parameter = 'gl_lux_hysteresis'
    LEFT JOIN latest_values legacy_auto ON legacy_auto.parameter = 'sw_gl_auto_mode'
    LEFT JOIN latest_values target_min ON target_min.parameter = 'gl_' || c.light_key || '_target_light_minutes'
    LEFT JOIN latest_values dli ON dli.parameter = 'gl_' || c.light_key || '_dli_target'
    LEFT JOIN latest_values start_h ON start_h.parameter = 'gl_' || c.light_key || '_sunrise_hour'
    LEFT JOIN latest_values cutoff_h ON cutoff_h.parameter = 'gl_' || c.light_key || '_sunset_hour'
    LEFT JOIN latest_values lux_on ON lux_on.parameter = 'gl_' || c.light_key || '_lux_threshold'
    LEFT JOIN latest_values lux_hyst ON lux_hyst.parameter = 'gl_' || c.light_key || '_lux_hysteresis'
    LEFT JOIN latest_values min_on ON min_on.parameter = 'gl_' || c.light_key || '_min_on_s'
    LEFT JOIN latest_values min_off ON min_off.parameter = 'gl_' || c.light_key || '_min_off_s'
    LEFT JOIN latest_values auto_mode ON auto_mode.parameter = 'sw_gl_' || c.light_key || '_auto_mode'
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
    'confirmed cfg/readback policy -> dispatcher/API -> ESP32 per-circuit qualified-minutes state machines -> Lutron switches -> equipment_state'::text
        AS source_chain,
    'Each circuit starts counting at sunrise. A minute qualifies once when natural lux is at or above the ON threshold OR the actual switch is ON. The circuit turns ON below threshold until target_light_minutes is met, with ON+hysteresis as the OFF threshold.'::text
        AS controller_contract
FROM resolved r;
$$;

COMMENT ON FUNCTION fn_lighting_minutes_policy(timestamptz, text) IS
    'Per-circuit qualified-light-minutes policy from confirmed cfg/readback state. Pending desired rows are intentionally excluded.';

CREATE OR REPLACE VIEW v_lighting_traceability_now AS
WITH status AS (
    SELECT * FROM v_lighting_minutes_status_now
),
latest_desired AS (
    SELECT DISTINCT ON (parameter)
        parameter,
        value,
        delivery_status,
        ts
    FROM setpoint_changes
    WHERE COALESCE(greenhouse_id, 'vallery') = 'vallery'
      AND COALESCE(source, '') <> 'esp32'
    ORDER BY parameter, ts DESC
),
latest_cfg AS (
    SELECT DISTINCT ON (parameter)
        parameter,
        value,
        ts
    FROM setpoint_snapshot
    WHERE COALESCE(greenhouse_id, 'vallery') = 'vallery'
    ORDER BY parameter, ts DESC
),
latest_decision AS (
    SELECT DISTINCT ON (entity)
        entity,
        value,
        ts
    FROM system_state
    WHERE entity IN ('gl_main_decision_epoch', 'gl_grow_decision_epoch')
    ORDER BY entity, ts DESC
)
SELECT
    s.*,
    cfg_target.value AS cfg_target_light_minutes,
    cfg_lux.value AS cfg_lux_on_threshold,
    cfg_hyst.value AS cfg_lux_hysteresis,
    cfg_auto.value >= 0.5 AS cfg_auto_enabled,
    cfg_auto.ts AS cfg_auto_ts,
    desired_target.value AS desired_target_light_minutes,
    desired_lux.value AS desired_lux_on_threshold,
    desired_hyst.value AS desired_lux_hysteresis,
    desired_auto.value >= 0.5 AS desired_auto_enabled,
    desired_auto.delivery_status AS desired_auto_delivery_status,
    desired_auto.ts AS desired_auto_ts,
    CASE
        WHEN decision.value ~ '^[0-9]+([.]0+)?$' THEN round(decision.value::numeric)::bigint
        ELSE NULL
    END AS firmware_decision_epoch,
    decision.ts AS firmware_decision_ts,
    decision.ts > now() - interval '15 minutes' AS firmware_decision_fresh,
    (
        s.auto_enabled IS NOT DISTINCT FROM (cfg_auto.value >= 0.5)
        AND s.target_light_minutes IS NOT DISTINCT FROM round(cfg_target.value)::integer
        AND COALESCE(abs(s.lux_on_threshold - cfg_lux.value) < 0.5, false)
        AND COALESCE(abs(s.lux_hysteresis - cfg_hyst.value) < 0.5, false)
    ) AS policy_matches_cfg
FROM status s
LEFT JOIN latest_cfg cfg_target ON cfg_target.parameter = 'gl_' || s.light_key || '_target_light_minutes'
LEFT JOIN latest_cfg cfg_lux ON cfg_lux.parameter = 'gl_' || s.light_key || '_lux_threshold'
LEFT JOIN latest_cfg cfg_hyst ON cfg_hyst.parameter = 'gl_' || s.light_key || '_lux_hysteresis'
LEFT JOIN latest_cfg cfg_auto ON cfg_auto.parameter = 'sw_gl_' || s.light_key || '_auto_mode'
LEFT JOIN latest_desired desired_target ON desired_target.parameter = 'gl_' || s.light_key || '_target_light_minutes'
LEFT JOIN latest_desired desired_lux ON desired_lux.parameter = 'gl_' || s.light_key || '_lux_threshold'
LEFT JOIN latest_desired desired_hyst ON desired_hyst.parameter = 'gl_' || s.light_key || '_lux_hysteresis'
LEFT JOIN latest_desired desired_auto ON desired_auto.parameter = 'sw_gl_' || s.light_key || '_auto_mode'
LEFT JOIN latest_decision decision ON decision.entity = 'gl_' || s.light_key || '_decision_epoch';

COMMENT ON VIEW v_lighting_traceability_now IS
    'Lighting policy traceability split into desired setpoint rows, confirmed cfg readbacks, firmware decision telemetry, and physical Lutron state.';

UPDATE setpoint_changes
   SET delivery_status = 'superseded',
       expired_at = COALESCE(expired_at, now()),
       superseded_by_ts = COALESCE(superseded_by_ts, now())
 WHERE confirmed_at IS NULL
   AND COALESCE(source, '') <> 'esp32'
   AND COALESCE(delivery_status, 'pending') = 'pending'
   AND parameter IN ('gl_dli_target', 'gl_sunrise_hour', 'gl_sunset_hour', 'gl_lux_threshold');

COMMENT ON TABLE weather_station IS
    'Legacy raw Tempest/Panorama weather table. Live controller weather and light policy now use climate Tempest columns; do not treat this table as a freshness source.';
