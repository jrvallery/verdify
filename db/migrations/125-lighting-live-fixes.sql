-- Migration 125: lighting live fixes
--
-- 1. Keep firmware lighting text telemetry from looking live after rollback.
-- 2. Count equipment cycles as rising edges instead of every duplicate TRUE row.

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
                extract(epoch FROM COALESCE(next_ts, (day + 1)::timestamp AT TIME ZONE 'America/Denver') - ts)
                / 60.0
            ) FILTER (WHERE state IS TRUE)
        )::numeric,
        1
    ) AS on_minutes,
    count(*) FILTER (WHERE state IS TRUE AND COALESCE(prev_state, false) IS FALSE) AS cycles
FROM transitions
GROUP BY day, equipment;

COMMENT ON VIEW v_equipment_runtime_daily IS
    'Daily equipment runtime from equipment_state transitions. Runtime integrates TRUE spans; cycles count TRUE rising edges only.';

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
firmware_ordered AS (
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
),
current_firmware_start AS (
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
),
joined AS (
    SELECT
        p.*,
        c.ts AS climate_ts,
        c.dli_today,
        c.lux AS indoor_lux,
        c.outdoor_lux,
        COALESCE(c.outdoor_lux, c.lux, 0.0) AS natural_lux,
        EXTRACT(hour FROM now() AT TIME ZONE 'America/Denver')::integer AS local_hour,
        e.state AS equipment_state,
        e.ts AS equipment_ts,
        state_row.value AS firmware_state_raw,
        state_row.ts AS firmware_state_ts,
        reason_row.value AS firmware_reason_raw,
        reason_row.ts AS firmware_reason_ts,
        (
            state_row.ts >= COALESCE((SELECT ts FROM current_firmware_start), now() - interval '10 minutes')
            AND reason_row.ts >= COALESCE((SELECT ts FROM current_firmware_start), now() - interval '10 minutes')
            AND state_row.ts > now() - interval '10 minutes'
            AND reason_row.ts > now() - interval '10 minutes'
        ) AS firmware_telemetry_fresh
    FROM policy p
    LEFT JOIN latest_climate c ON true
    LEFT JOIN latest_equipment e ON e.equipment = p.equipment
    LEFT JOIN latest_reason state_row ON state_row.entity = 'gl_' || p.light_key || '_state'
    LEFT JOIN latest_reason reason_row ON reason_row.entity = 'gl_' || p.light_key || '_reason'
)
SELECT
    j.greenhouse_id,
    j.ts,
    j.light_key,
    j.equipment,
    j.dli_target,
    j.start_hour,
    j.cutoff_hour,
    j.lux_on_threshold,
    j.lux_hysteresis,
    j.lux_off_threshold,
    j.min_on_s,
    j.min_off_s,
    j.auto_enabled,
    j.source_chain,
    j.controller_contract,
    j.climate_ts,
    j.dli_today,
    j.indoor_lux,
    j.outdoor_lux,
    j.natural_lux,
    j.local_hour,
    CASE
        WHEN j.start_hour <= j.cutoff_hour THEN
            j.local_hour >= j.start_hour AND j.local_hour < j.cutoff_hour
        ELSE
            j.local_hour >= j.start_hour OR j.local_hour < j.cutoff_hour
    END AS in_light_window,
    COALESCE(j.dli_today, 0.0) < j.dli_target AS dli_below_target,
    j.natural_lux < j.lux_on_threshold AS lux_below_on_threshold,
    j.natural_lux < j.lux_off_threshold AS lux_below_off_threshold,
    (
        j.auto_enabled
        AND (
            CASE
                WHEN j.start_hour <= j.cutoff_hour THEN
                    j.local_hour >= j.start_hour AND j.local_hour < j.cutoff_hour
                ELSE
                    j.local_hour >= j.start_hour OR j.local_hour < j.cutoff_hour
            END
        )
        AND COALESCE(j.dli_today, 0.0) < j.dli_target
        AND (
            j.natural_lux < j.lux_on_threshold
            OR (
                COALESCE(j.equipment_state, false)
                OR (
                    j.firmware_telemetry_fresh
                    AND upper(COALESCE(j.firmware_state_raw, '')) = 'ON'
                )
            ) AND j.natural_lux < j.lux_off_threshold
        )
    ) AS expected_on,
    COALESCE(j.equipment_state, false) AS actual_on,
    CASE WHEN j.firmware_telemetry_fresh THEN j.firmware_state_raw END AS firmware_state,
    CASE WHEN j.firmware_telemetry_fresh THEN j.firmware_reason_raw END AS firmware_reason,
    j.equipment_ts,
    j.firmware_state_raw,
    j.firmware_reason_raw,
    j.firmware_state_ts,
    j.firmware_reason_ts,
    j.firmware_telemetry_fresh
FROM joined j;

COMMENT ON VIEW v_lighting_circuit_status_now IS
    'Current per-circuit lighting policy, expected state, fresh firmware text state, and actual Lutron equipment_state. Firmware state/reason are NULL unless updated after current firmware start and within 10 minutes.';

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
    grow.firmware_reason AS grow_firmware_reason,
    main.firmware_state_ts AS main_firmware_state_ts,
    main.firmware_reason_ts AS main_firmware_reason_ts,
    main.firmware_telemetry_fresh AS main_firmware_telemetry_fresh,
    grow.firmware_state_ts AS grow_firmware_state_ts,
    grow.firmware_reason_ts AS grow_firmware_reason_ts,
    grow.firmware_telemetry_fresh AS grow_firmware_telemetry_fresh
FROM policy
CROSS JOIN main
CROSS JOIN grow;

COMMENT ON VIEW v_lighting_status_now IS
    'Compatibility one-row lighting status with per-circuit policy, expected state, Lutron state, and firmware telemetry freshness.';
