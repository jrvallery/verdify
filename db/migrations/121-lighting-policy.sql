-- Migration 121: crop-driven lighting policy
--
-- Grow-light automation is enforced on the ESP32, but the policy values must
-- be derived from crop targets rather than stale planner rows. This function
-- converts the highest active crop DLI target into a photoperiod window that
-- starts at local sunrise and extends as needed.

CREATE OR REPLACE FUNCTION fn_lighting_policy(
    p_ts timestamptz DEFAULT now(),
    p_greenhouse_id text DEFAULT 'vallery'
)
RETURNS TABLE (
    greenhouse_id text,
    ts timestamptz,
    local_date date,
    target_dli double precision,
    target_ppfd_umol_m2_s double precision,
    target_light_hours integer,
    sunrise_hour integer,
    natural_sunset_hour integer,
    cutoff_hour integer,
    max_crop_name text,
    max_crop_stage text,
    source_chain text,
    controller_contract text
)
LANGUAGE sql
STABLE
AS $$
WITH crop_targets AS (
    SELECT
        c.name,
        c.stage,
        COALESCE(c.target_dli, max(ctp.dli_target_mol))::double precision AS target_dli
    FROM crops c
    LEFT JOIN crop_target_profiles ctp
      ON COALESCE(ctp.greenhouse_id, 'vallery') = p_greenhouse_id
     AND lower(ctp.crop_type) = lower(c.name)
     AND lower(COALESCE(ctp.growth_stage, 'vegetative')) = lower(COALESCE(c.stage, 'vegetative'))
    WHERE c.is_active IS TRUE
      AND COALESCE(c.greenhouse_id, 'vallery') = p_greenhouse_id
    GROUP BY c.id, c.name, c.stage, c.target_dli
),
max_crop AS (
    SELECT name, stage, target_dli
    FROM crop_targets
    WHERE target_dli IS NOT NULL
    ORDER BY target_dli DESC, name
    LIMIT 1
),
policy_input AS (
    SELECT
        COALESCE((SELECT target_dli FROM max_crop), 14.0)::double precision AS target_dli,
        400.0::double precision AS target_ppfd_umol_m2_s,
        COALESCE((SELECT name FROM max_crop), 'fallback') AS max_crop_name,
        COALESCE((SELECT stage FROM max_crop), 'unknown') AS max_crop_stage
),
local_day AS (
    SELECT date_trunc('day', p_ts AT TIME ZONE 'America/Denver') AS midnight_local
),
hourly_sun AS (
    SELECT
        h.hour_of_day,
        fn_solar_altitude((d.midnight_local + make_interval(hours => h.hour_of_day)) AT TIME ZONE 'America/Denver') AS altitude_deg
    FROM local_day d
    CROSS JOIN generate_series(0, 23) AS h(hour_of_day)
),
sun_window AS (
    SELECT
        COALESCE(min(hour_of_day) FILTER (WHERE altitude_deg > 0), 6)::integer AS sunrise_hour,
        LEAST(COALESCE(max(hour_of_day) FILTER (WHERE altitude_deg > 0), 20) + 1, 23)::integer AS natural_sunset_hour
    FROM hourly_sun
),
policy AS (
    SELECT
        p.target_dli,
        p.target_ppfd_umol_m2_s,
        GREATEST(
            10,
            LEAST(
                18,
                CEIL(p.target_dli * 1000000.0 / (p.target_ppfd_umol_m2_s * 3600.0))::integer
            )
        ) AS target_light_hours,
        p.max_crop_name,
        p.max_crop_stage
    FROM policy_input p
)
SELECT
    p_greenhouse_id AS greenhouse_id,
    p_ts AS ts,
    (p_ts AT TIME ZONE 'America/Denver')::date AS local_date,
    policy.target_dli,
    policy.target_ppfd_umol_m2_s,
    policy.target_light_hours,
    sun_window.sunrise_hour,
    sun_window.natural_sunset_hour,
    LEAST(sun_window.sunrise_hour + policy.target_light_hours, 23)::integer AS cutoff_hour,
    policy.max_crop_name,
    policy.max_crop_stage,
    'active crops.target_dli -> fn_lighting_policy() -> setpoint_dispatcher/API fallback -> ESP32 grow-light loop -> Home Assistant light services'::text AS source_chain,
    'ESP32 turns both grow-light circuits on during the crop light window when DLI is below target and lux is below threshold; deterministic cutoff remains local-hour based.'::text AS controller_contract
FROM policy
CROSS JOIN sun_window;
$$;

COMMENT ON FUNCTION fn_lighting_policy(timestamptz, text) IS
    'Crop-driven grow-light policy. Highest active crop DLI sets target_light_hours at 400 umol/m2/s; window starts at computed local sunrise and ends at the ESP32 cutoff hour.';

DO $$
BEGIN
    -- Migration 123 upgrades these views to per-circuit lighting policy. If 121
    -- is re-run after 123, keep the newer shape instead of replacing it with the
    -- original compatibility projection.
    IF to_regprocedure('fn_lighting_circuit_policy(timestamptz,text)') IS NULL THEN
        EXECUTE $view$
            CREATE OR REPLACE VIEW v_lighting_status_now AS
            WITH policy AS (
                SELECT * FROM fn_lighting_policy(now(), 'vallery')
            ),
            latest_climate AS (
                SELECT ts, dli_today, lux, outdoor_lux
                FROM climate
                WHERE greenhouse_id = 'vallery'
                ORDER BY ts DESC
                LIMIT 1
            ),
            latest_threshold AS (
                SELECT value AS gl_lux_threshold
                FROM setpoint_changes
                WHERE parameter = 'gl_lux_threshold'
                ORDER BY ts DESC
                LIMIT 1
            ),
            latest_hysteresis AS (
                SELECT value AS gl_lux_hysteresis
                FROM setpoint_changes
                WHERE parameter = 'gl_lux_hysteresis'
                ORDER BY ts DESC
                LIMIT 1
            ),
            latest_equipment AS (
                SELECT DISTINCT ON (equipment) equipment, state, ts
                FROM equipment_state
                WHERE equipment IN ('grow_light_main', 'grow_light_grow')
                ORDER BY equipment, ts DESC
            ),
            base AS (
                SELECT
                    policy.*,
                    climate.ts AS climate_ts,
                    climate.dli_today,
                    climate.lux,
                    climate.outdoor_lux,
                    COALESCE(threshold.gl_lux_threshold, 3000.0) AS gl_lux_threshold,
                    COALESCE(hysteresis.gl_lux_hysteresis, 1500.0) AS gl_lux_hysteresis,
                    COALESCE(main.state, false) AS grow_light_main_on,
                    COALESCE(grow.state, false) AS grow_light_grow_on,
                    EXTRACT(hour FROM now() AT TIME ZONE 'America/Denver')::integer AS local_hour
                FROM policy
                LEFT JOIN latest_climate climate ON true
                LEFT JOIN latest_threshold threshold ON true
                LEFT JOIN latest_hysteresis hysteresis ON true
                LEFT JOIN latest_equipment main ON main.equipment = 'grow_light_main'
                LEFT JOIN latest_equipment grow ON grow.equipment = 'grow_light_grow'
            )
            SELECT
                *,
                local_hour >= sunrise_hour AND local_hour < cutoff_hour AS in_light_window,
                COALESCE(dli_today, 0.0) < target_dli AS dli_below_target,
                COALESCE(outdoor_lux, lux, 0.0) < gl_lux_threshold AS lux_below_threshold,
                (
                    local_hour >= sunrise_hour
                    AND local_hour < cutoff_hour
                    AND COALESCE(dli_today, 0.0) < target_dli
                    AND COALESCE(outdoor_lux, lux, 0.0) < gl_lux_threshold
                ) AS expected_lights_on
            FROM base
        $view$;

        EXECUTE $view$
            COMMENT ON VIEW v_lighting_status_now IS
                'Current lighting policy, sensor state, and both grow-light circuits in one traceable row.'
        $view$;

        EXECUTE $view$
            CREATE OR REPLACE VIEW v_lighting_daily AS
            SELECT
                ds.date,
                (ds.date + time '12:00')::timestamptz AS ts,
                ds.dli_final AS sensor_dli,
                ds.runtime_grow_light_min / 60.0 AS grow_light_hours,
                p.target_dli,
                p.target_light_hours,
                p.sunrise_hour,
                p.natural_sunset_hour,
                p.cutoff_hour,
                p.max_crop_name
            FROM daily_summary ds
            CROSS JOIN LATERAL fn_lighting_policy((ds.date + time '12:00')::timestamptz, 'vallery') p
            WHERE ds.dli_final IS NOT NULL
        $view$;

        EXECUTE $view$
            COMMENT ON VIEW v_lighting_daily IS
                'Daily DLI and grow-light runtime joined to the crop-driven lighting policy used by the dispatcher.'
        $view$;
    END IF;
END$$;

-- Remove stale planner ownership of lighting policy rows. The dispatcher now
-- derives these values every cycle from fn_lighting_policy().
UPDATE setpoint_plan
SET is_active = false
WHERE is_active = true
  AND parameter IN ('gl_dli_target', 'gl_sunrise_hour', 'gl_sunset_hour', 'sw_gl_auto_mode');
