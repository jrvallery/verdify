-- Migration 129: exact firmware epoch telemetry from text sensors
--
-- ESPHome numeric sensors publish single-precision floats, which quantize
-- current Unix epochs into 128-second buckets. Firmware now publishes full
-- epoch values as text_sensor strings; parse them to bigint in DB views.

DROP VIEW IF EXISTS v_lighting_traceability_now;

CREATE VIEW v_lighting_traceability_now AS
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
    'Lighting policy traceability split into desired setpoint rows, confirmed cfg readbacks, exact firmware decision epoch text, and physical Lutron state.';
