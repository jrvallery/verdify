-- 119-band-traceability.sql
--
-- Canonical band traceability surface. The greenhouse has three distinct
-- band concepts that must not be collapsed in dashboards or public copy:
--   1. crop target band from crop profiles,
--   2. firmware-enforced band pushed through setpoint_changes,
--   3. cfg_* readback band reported by the ESP32.

CREATE INDEX IF NOT EXISTS idx_climate_ghid_ts_not_null
    ON climate (greenhouse_id, ts DESC)
    WHERE temp_avg IS NOT NULL AND vpd_avg IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_setpoint_changes_ghid_param_ts
    ON setpoint_changes (greenhouse_id, parameter, ts DESC);

CREATE INDEX IF NOT EXISTS idx_setpoint_snapshot_ghid_param_ts
    ON setpoint_snapshot (greenhouse_id, parameter, ts DESC);

CREATE INDEX IF NOT EXISTS idx_weather_forecast_ghid_ts_fetched
    ON weather_forecast (greenhouse_id, ts, fetched_at DESC);

CREATE OR REPLACE FUNCTION fn_setpoint_at(
    p_greenhouse_id text,
    p_param text,
    p_ts timestamptz
)
RETURNS double precision
LANGUAGE sql
STABLE
AS $$
    SELECT value
      FROM setpoint_changes
     WHERE greenhouse_id = p_greenhouse_id
       AND parameter = p_param
       AND ts <= p_ts
       AND (expired_at IS NULL OR expired_at > p_ts)
     ORDER BY ts DESC
     LIMIT 1;
$$;

COMMENT ON FUNCTION fn_setpoint_at(text, text, timestamptz) IS
    'Greenhouse-aware latest pushed setpoint value at a timestamp. Compatibility fn_setpoint_at(param, ts) remains for legacy vallery-only consumers.';

ALTER FUNCTION fn_band_setpoints(timestamptz) ROWS 1;
ALTER FUNCTION fn_zone_vpd_targets(timestamptz) ROWS 1;

CREATE OR REPLACE FUNCTION fn_house_vpd_control_band(target_ts timestamptz)
RETURNS TABLE (
    crop_vpd_low double precision,
    crop_vpd_high double precision,
    vpd_target_south double precision,
    vpd_target_west double precision,
    vpd_target_east double precision,
    vpd_target_center double precision,
    zone_vpd_min double precision,
    zone_vpd_median double precision,
    zone_vpd_max double precision,
    house_vpd_low double precision,
    house_vpd_high double precision,
    house_vpd_min_width_kpa double precision,
    house_vpd_low_margin_kpa double precision
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_base_low double precision;
    v_base_high double precision;
    v_south double precision;
    v_west double precision;
    v_east double precision;
    v_center double precision;
    v_targets double precision[];
    v_n integer;
    v_house_low double precision;
    v_house_high double precision;
    v_min_width constant double precision := 0.55;
    v_low_margin constant double precision := 0.20;
BEGIN
    SELECT b.vpd_low, b.vpd_high
      INTO v_base_low, v_base_high
      FROM fn_band_setpoints(target_ts) AS b
     LIMIT 1;

    IF v_base_low IS NULL OR v_base_high IS NULL THEN
        RETURN;
    END IF;

    SELECT z.vpd_target_south,
           z.vpd_target_west,
           z.vpd_target_east,
           z.vpd_target_center
      INTO v_south, v_west, v_east, v_center
      FROM fn_zone_vpd_targets(target_ts) AS z
     LIMIT 1;

    SELECT array_agg(v ORDER BY v)
      INTO v_targets
      FROM (
          VALUES (v_south), (v_west), (v_east), (v_center)
      ) AS target_values(v)
     WHERE v IS NOT NULL
       AND v > 0
       AND v < 10;

    v_n := COALESCE(array_length(v_targets, 1), 0);

    crop_vpd_low := v_base_low;
    crop_vpd_high := v_base_high;
    vpd_target_south := v_south;
    vpd_target_west := v_west;
    vpd_target_east := v_east;
    vpd_target_center := v_center;
    house_vpd_min_width_kpa := v_min_width;
    house_vpd_low_margin_kpa := v_low_margin;

    IF v_n = 0 THEN
        house_vpd_low := v_base_low;
        house_vpd_high := v_base_high;
        RETURN NEXT;
        RETURN;
    END IF;

    zone_vpd_min := v_targets[1];
    zone_vpd_max := v_targets[v_n];
    IF mod(v_n, 2) = 1 THEN
        zone_vpd_median := v_targets[(v_n + 1) / 2];
    ELSE
        zone_vpd_median := (v_targets[v_n / 2] + v_targets[(v_n / 2) + 1]) / 2.0;
    END IF;

    v_house_high := least(zone_vpd_max, greatest(v_base_high, zone_vpd_median));
    v_house_low := greatest(v_base_low, zone_vpd_min - v_low_margin);
    v_house_low := least(v_house_low, v_house_high - v_min_width);
    v_house_low := greatest(0.1, v_house_low);

    IF v_house_high - v_house_low < v_min_width THEN
        v_house_low := greatest(0.1, v_house_high - v_min_width);
    END IF;

    house_vpd_low := round(v_house_low::numeric, 3)::double precision;
    house_vpd_high := round(v_house_high::numeric, 3)::double precision;
    RETURN NEXT;
END;
$$;

COMMENT ON FUNCTION fn_house_vpd_control_band(timestamptz) IS
    'Firmware house VPD band derived from crop VPD envelope plus zone VPD targets. Mirrors dispatcher control semantics: median zone high, 0.55 kPa minimum width, low-side relaxation.';

ALTER FUNCTION fn_house_vpd_control_band(timestamptz) ROWS 1;

CREATE OR REPLACE FUNCTION fn_timeline_setpoint_value(
    p_greenhouse_id text,
    p_param text,
    p_ts timestamptz,
    p_default double precision
)
RETURNS double precision
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(
        CASE
            WHEN p_ts <= now() THEN (
                SELECT sc.value
                  FROM setpoint_changes sc
                 WHERE sc.greenhouse_id = p_greenhouse_id
                   AND sc.parameter = p_param
                   AND sc.ts <= p_ts
                   AND (sc.expired_at IS NULL OR sc.expired_at > p_ts)
                 ORDER BY sc.ts DESC
                 LIMIT 1
            )
        END,
        (
            SELECT sp.value
              FROM setpoint_plan sp
             WHERE COALESCE(sp.greenhouse_id, 'vallery') = p_greenhouse_id
               AND sp.parameter = p_param
               AND sp.is_active = true
               AND sp.ts <= p_ts
             ORDER BY sp.created_at DESC, sp.ts DESC
             LIMIT 1
        ),
        (
            SELECT sc.value
              FROM setpoint_changes sc
             WHERE sc.greenhouse_id = p_greenhouse_id
               AND sc.parameter = p_param
               AND (sc.expired_at IS NULL OR sc.expired_at > now())
             ORDER BY sc.ts DESC
             LIMIT 1
        ),
        p_default
    );
$$;

COMMENT ON FUNCTION fn_timeline_setpoint_value(text, text, timestamptz, double precision) IS
    'Dashboard timeline resolver for non-band tunables: historical actual pushes through now, active/planned schedule after now, then latest push/default fallback.';

DROP FUNCTION IF EXISTS fn_band_timeline(timestamptz, timestamptz, interval, text);

CREATE OR REPLACE FUNCTION fn_band_timeline(
    p_start timestamptz,
    p_end timestamptz,
    p_step interval DEFAULT interval '30 minutes',
    p_greenhouse_id text DEFAULT 'vallery'
)
RETURNS TABLE (
    ts timestamptz,
    greenhouse_id text,
    timeline_phase text,
    crop_temp_low double precision,
    crop_temp_high double precision,
    crop_vpd_low double precision,
    crop_vpd_high double precision,
    projected_temp_low double precision,
    projected_temp_high double precision,
    projected_vpd_low double precision,
    projected_vpd_high double precision,
    actual_temp_low double precision,
    actual_temp_high double precision,
    actual_vpd_low double precision,
    actual_vpd_high double precision,
    firmware_temp_low double precision,
    firmware_temp_high double precision,
    firmware_vpd_low double precision,
    firmware_vpd_high double precision,
    temp_width_f double precision,
    vpd_width_kpa double precision,
    sw_fsm_controller_enabled boolean,
    indoor_temp_f double precision,
    indoor_vpd_kpa double precision,
    outdoor_temp_f double precision,
    outdoor_vpd_kpa double precision,
    solar_w_m2 double precision,
    outdoor_cold_for_vent boolean,
    temp_hysteresis_f double precision,
    heat_hysteresis_f double precision,
    d_heat_stage_2_f double precision,
    d_cool_stage_2_f double precision,
    bias_heat_f double precision,
    bias_cool_f double precision,
    vpd_hysteresis_kpa double precision,
    vpd_hysteresis_effective_kpa double precision,
    fog_escalation_kpa double precision,
    temp_heat_target_f double precision,
    temp_heat_on_below_f double precision,
    temp_heat2_on_below_f double precision,
    temp_heat2_clear_f double precision,
    temp_cool_on_above_f double precision,
    temp_cool_hold_until_f double precision,
    temp_cooling_entry_margin_f double precision,
    temp_cooling_exit_hysteresis_f double precision,
    solar_cooling_lead_f double precision,
    temp_cool_stage2_delta_f double precision,
    temp_cool_stage2_on_above_f double precision,
    vpd_humidify_on_above_kpa double precision,
    vpd_humidify_resolved_below_kpa double precision,
    vpd_dehum_on_below_kpa double precision,
    vpd_dehum_resolved_above_kpa double precision,
    vpd_low_eff_kpa double precision,
    vpd_high_eff_kpa double precision,
    vpd_vent_fog_on_above_kpa double precision,
    vpd_sealed_fog_on_above_kpa double precision
)
LANGUAGE sql
STABLE
AS $$
WITH timeline AS (
    SELECT generate_series(p_start, p_end, p_step) AS ts
),
forecast_hourly AS (
    SELECT DISTINCT ON (date_trunc('hour', wf.ts))
        date_trunc('hour', wf.ts) AS forecast_hour,
        wf.temp_f AS outdoor_temp_f,
        wf.vpd_kpa AS outdoor_vpd_kpa,
        wf.solar_w_m2
      FROM weather_forecast wf
     WHERE wf.greenhouse_id = p_greenhouse_id
       AND wf.ts >= p_start - interval '1 hour'
       AND wf.ts <= p_end + interval '1 hour'
     ORDER BY date_trunc('hour', wf.ts), wf.fetched_at DESC
),
resolved AS (
SELECT
    t.ts,
    p_greenhouse_id AS greenhouse_id,
    CASE WHEN t.ts <= now() THEN 'actual' ELSE 'forecast' END AS timeline_phase,
    crop.temp_low AS crop_temp_low,
    crop.temp_high AS crop_temp_high,
    house.crop_vpd_low,
    house.crop_vpd_high,
    crop.temp_low AS projected_temp_low,
    crop.temp_high AS projected_temp_high,
    house.house_vpd_low AS projected_vpd_low,
    house.house_vpd_high AS projected_vpd_high,
    actual_temp_low.value AS actual_temp_low,
    actual_temp_high.value AS actual_temp_high,
    actual_vpd_low.value AS actual_vpd_low,
    actual_vpd_high.value AS actual_vpd_high,
    actual_climate.temp_avg AS indoor_temp_f,
    actual_climate.vpd_avg AS indoor_vpd_kpa,
    CASE
        WHEN t.ts <= now() THEN actual_climate.outdoor_temp_f
        ELSE forecast.outdoor_temp_f
    END AS outdoor_temp_f,
    CASE
        WHEN t.ts <= now() THEN actual_climate.outdoor_vpd_kpa
        ELSE forecast.outdoor_vpd_kpa
    END AS outdoor_vpd_kpa,
    CASE
        WHEN t.ts <= now() THEN actual_climate.solar_w_m2
        ELSE forecast.solar_w_m2
    END AS solar_w_m2,
    CASE
        WHEN t.ts <= now() THEN COALESCE(actual_temp_low.value, crop.temp_low)
        ELSE crop.temp_low
    END AS firmware_temp_low,
    CASE
        WHEN t.ts <= now() THEN COALESCE(actual_temp_high.value, crop.temp_high)
        ELSE crop.temp_high
    END AS firmware_temp_high,
    CASE
        WHEN t.ts <= now() THEN COALESCE(actual_vpd_low.value, house.house_vpd_low)
        ELSE house.house_vpd_low
    END AS firmware_vpd_low,
    CASE
        WHEN t.ts <= now() THEN COALESCE(actual_vpd_high.value, house.house_vpd_high)
        ELSE house.house_vpd_high
    END AS firmware_vpd_high
FROM timeline t
CROSS JOIN LATERAL fn_band_setpoints(t.ts) AS crop
CROSS JOIN LATERAL fn_house_vpd_control_band(t.ts) AS house
LEFT JOIN LATERAL (
    SELECT value
      FROM setpoint_changes
     WHERE greenhouse_id = p_greenhouse_id
       AND parameter = 'temp_low'
       AND t.ts <= now()
       AND ts <= t.ts
       AND (expired_at IS NULL OR expired_at > t.ts)
     ORDER BY ts DESC
     LIMIT 1
) AS actual_temp_low ON true
LEFT JOIN LATERAL (
    SELECT value
      FROM setpoint_changes
     WHERE greenhouse_id = p_greenhouse_id
       AND parameter = 'temp_high'
       AND t.ts <= now()
       AND ts <= t.ts
       AND (expired_at IS NULL OR expired_at > t.ts)
     ORDER BY ts DESC
     LIMIT 1
) AS actual_temp_high ON true
LEFT JOIN LATERAL (
    SELECT value
      FROM setpoint_changes
     WHERE greenhouse_id = p_greenhouse_id
       AND parameter = 'vpd_low'
       AND t.ts <= now()
       AND ts <= t.ts
       AND (expired_at IS NULL OR expired_at > t.ts)
     ORDER BY ts DESC
     LIMIT 1
) AS actual_vpd_low ON true
LEFT JOIN LATERAL (
    SELECT value
      FROM setpoint_changes
     WHERE greenhouse_id = p_greenhouse_id
       AND parameter = 'vpd_high'
       AND t.ts <= now()
       AND ts <= t.ts
       AND (expired_at IS NULL OR expired_at > t.ts)
     ORDER BY ts DESC
     LIMIT 1
) AS actual_vpd_high ON true
LEFT JOIN LATERAL (
    SELECT
        c.temp_avg,
        c.vpd_avg,
        c.outdoor_temp_f,
        CASE
            WHEN c.outdoor_temp_f IS NOT NULL AND c.outdoor_rh_pct IS NOT NULL THEN
                0.6108
                * exp(17.27 * ((c.outdoor_temp_f - 32.0) / 1.8)
                      / (((c.outdoor_temp_f - 32.0) / 1.8) + 237.3))
                * (1.0 - c.outdoor_rh_pct / 100.0)
            ELSE NULL
        END AS outdoor_vpd_kpa,
        c.solar_irradiance_w_m2 AS solar_w_m2
      FROM climate c
     WHERE c.greenhouse_id = p_greenhouse_id
       AND t.ts <= now()
       AND c.ts <= t.ts
       AND c.ts >= t.ts - interval '15 minutes'
     ORDER BY c.ts DESC
    LIMIT 1
) AS actual_climate ON true
LEFT JOIN forecast_hourly forecast
       ON t.ts > now()
      AND forecast.forecast_hour = date_trunc('hour', t.ts + interval '30 minutes')
),
with_tunables AS (
    SELECT
        r.*,
        greatest(2.0, r.firmware_temp_high - r.firmware_temp_low) AS temp_width_f,
        greatest(0.2, r.firmware_vpd_high - r.firmware_vpd_low) AS vpd_width_kpa,
        fn_timeline_setpoint_value(p_greenhouse_id, 'sw_fsm_controller_enabled', r.ts, 1.0) >= 0.5
            AS sw_fsm_controller_enabled,
        fn_timeline_setpoint_value(p_greenhouse_id, 'temp_hysteresis', r.ts, 1.5)
            AS temp_hysteresis_f,
        fn_timeline_setpoint_value(p_greenhouse_id, 'heat_hysteresis', r.ts, 1.0)
            AS heat_hysteresis_f,
        fn_timeline_setpoint_value(p_greenhouse_id, 'd_heat_stage_2', r.ts, 5.0)
            AS d_heat_stage_2_f,
        fn_timeline_setpoint_value(p_greenhouse_id, 'd_cool_stage_2', r.ts, 3.0)
            AS d_cool_stage_2_f,
        fn_timeline_setpoint_value(p_greenhouse_id, 'bias_heat', r.ts, 0.0)
            AS bias_heat_f,
        fn_timeline_setpoint_value(p_greenhouse_id, 'bias_cool', r.ts, 0.0)
            AS bias_cool_f,
        fn_timeline_setpoint_value(p_greenhouse_id, 'vpd_hysteresis', r.ts, 0.3)
            AS vpd_hysteresis_kpa,
        fn_timeline_setpoint_value(p_greenhouse_id, 'fog_escalation_kpa', r.ts, 0.4)
            AS fog_escalation_kpa
    FROM resolved r
),
derived_base AS (
    SELECT
        t.*,
        CASE
            WHEN t.sw_fsm_controller_enabled THEN
                least(greatest(0.05, t.vpd_hysteresis_kpa), greatest(0.05, t.vpd_width_kpa * 0.33))
            ELSE
                least(greatest(0.05, t.vpd_hysteresis_kpa), t.firmware_vpd_high * 0.5)
        END AS vpd_hysteresis_effective_kpa,
        CASE
            WHEN t.sw_fsm_controller_enabled THEN
                (t.firmware_temp_low + t.firmware_temp_high) * 0.5
            ELSE
                t.firmware_temp_low + t.temp_width_f * 0.25 + t.bias_heat_f
        END AS temp_heat_target_f,
        CASE
            WHEN t.sw_fsm_controller_enabled THEN
                least(t.d_cool_stage_2_f, greatest(1.0, t.temp_width_f * 0.25))
            ELSE
                t.d_cool_stage_2_f
        END AS temp_cool_stage2_delta_f,
        t.firmware_vpd_low + t.vpd_width_kpa * 0.25 AS vpd_low_eff_kpa,
        t.firmware_vpd_high - t.vpd_width_kpa * 0.25 AS vpd_high_eff_kpa
    FROM with_tunables t
),
derived AS (
    SELECT
        b.*,
        (
            b.outdoor_temp_f IS NOT NULL
            AND b.outdoor_temp_f < (b.firmware_temp_low - 10.0)
        ) AS outdoor_cold_for_vent,
        CASE
            WHEN b.sw_fsm_controller_enabled
             AND b.outdoor_temp_f IS NOT NULL
             AND b.outdoor_temp_f < (b.firmware_temp_low - 10.0)
                THEN b.temp_cool_stage2_delta_f
            ELSE 0.0
        END AS temp_cooling_entry_margin_f,
        CASE
            WHEN b.sw_fsm_controller_enabled
             AND b.outdoor_temp_f IS NOT NULL
             AND b.outdoor_temp_f < (b.firmware_temp_low - 10.0)
                THEN greatest(b.temp_hysteresis_f, 3.0)
            ELSE b.temp_hysteresis_f
        END AS temp_cooling_exit_hysteresis_f,
        CASE
            WHEN b.sw_fsm_controller_enabled
             AND NOT (
                 b.outdoor_temp_f IS NOT NULL
                 AND b.outdoor_temp_f < (b.firmware_temp_low - 10.0)
             )
             AND b.solar_w_m2 IS NOT NULL
             AND b.solar_w_m2 >= 500.0
             AND extract(hour FROM b.ts AT TIME ZONE 'America/Denver') BETWEEN 10 AND 17
             AND b.indoor_vpd_kpa IS NOT NULL
             AND b.indoor_vpd_kpa <= (b.firmware_vpd_high - b.vpd_hysteresis_effective_kpa)
                THEN 1.0
            ELSE 0.0
        END AS solar_cooling_lead_f,
        CASE
            WHEN b.sw_fsm_controller_enabled THEN
                greatest(
                    b.firmware_temp_low + 1.0,
                    b.firmware_temp_high
                    + CASE
                        WHEN b.outdoor_temp_f IS NOT NULL
                         AND b.outdoor_temp_f < (b.firmware_temp_low - 10.0)
                            THEN b.temp_cool_stage2_delta_f
                        ELSE 0.0
                    END
                    - CASE
                        WHEN NOT (
                            b.outdoor_temp_f IS NOT NULL
                            AND b.outdoor_temp_f < (b.firmware_temp_low - 10.0)
                        )
                         AND b.solar_w_m2 IS NOT NULL
                         AND b.solar_w_m2 >= 500.0
                         AND extract(hour FROM b.ts AT TIME ZONE 'America/Denver') BETWEEN 10 AND 17
                         AND b.indoor_vpd_kpa IS NOT NULL
                         AND b.indoor_vpd_kpa <= (b.firmware_vpd_high - b.vpd_hysteresis_effective_kpa)
                            THEN 1.0
                        ELSE 0.0
                    END
                )
            ELSE
                b.firmware_temp_high - b.temp_width_f * 0.25 + b.bias_cool_f
        END AS temp_cool_on_above_f
    FROM derived_base b
)
SELECT
    d.ts,
    d.greenhouse_id,
    d.timeline_phase,
    d.crop_temp_low,
    d.crop_temp_high,
    d.crop_vpd_low,
    d.crop_vpd_high,
    d.projected_temp_low,
    d.projected_temp_high,
    d.projected_vpd_low,
    d.projected_vpd_high,
    d.actual_temp_low,
    d.actual_temp_high,
    d.actual_vpd_low,
    d.actual_vpd_high,
    d.firmware_temp_low,
    d.firmware_temp_high,
    d.firmware_vpd_low,
    d.firmware_vpd_high,
    d.temp_width_f,
    d.vpd_width_kpa,
    d.sw_fsm_controller_enabled,
    d.indoor_temp_f,
    d.indoor_vpd_kpa,
    d.outdoor_temp_f,
    d.outdoor_vpd_kpa,
    d.solar_w_m2,
    d.outdoor_cold_for_vent,
    d.temp_hysteresis_f,
    d.heat_hysteresis_f,
    d.d_heat_stage_2_f,
    d.d_cool_stage_2_f,
    d.bias_heat_f,
    d.bias_cool_f,
    d.vpd_hysteresis_kpa,
    d.vpd_hysteresis_effective_kpa,
    d.fog_escalation_kpa,
    d.temp_heat_target_f,
    d.temp_heat_target_f + d.heat_hysteresis_f AS temp_heat_on_below_f,
    CASE
        WHEN d.sw_fsm_controller_enabled THEN d.firmware_temp_low
        ELSE d.temp_heat_target_f - d.d_heat_stage_2_f
    END AS temp_heat2_on_below_f,
    CASE
        WHEN d.sw_fsm_controller_enabled THEN d.temp_heat_target_f
        ELSE d.temp_heat_target_f + d.heat_hysteresis_f
    END AS temp_heat2_clear_f,
    d.temp_cool_on_above_f,
    CASE
        WHEN d.sw_fsm_controller_enabled THEN
            least(
                d.firmware_temp_high - d.temp_cooling_exit_hysteresis_f,
                d.temp_cool_on_above_f - d.temp_cooling_exit_hysteresis_f
            )
        ELSE d.temp_cool_on_above_f - d.temp_hysteresis_f
    END AS temp_cool_hold_until_f,
    d.temp_cooling_entry_margin_f,
    d.temp_cooling_exit_hysteresis_f,
    d.solar_cooling_lead_f,
    d.temp_cool_stage2_delta_f,
    CASE
        WHEN d.sw_fsm_controller_enabled THEN d.firmware_temp_high + d.temp_cool_stage2_delta_f
        ELSE d.temp_cool_on_above_f + d.temp_cool_stage2_delta_f
    END AS temp_cool_stage2_on_above_f,
    d.firmware_vpd_high AS vpd_humidify_on_above_kpa,
    d.firmware_vpd_high - d.vpd_hysteresis_effective_kpa AS vpd_humidify_resolved_below_kpa,
    CASE
        WHEN d.sw_fsm_controller_enabled AND d.outdoor_cold_for_vent THEN
            d.firmware_vpd_low - d.vpd_hysteresis_effective_kpa
        ELSE d.firmware_vpd_low
    END AS vpd_dehum_on_below_kpa,
    d.firmware_vpd_low + d.vpd_hysteresis_effective_kpa AS vpd_dehum_resolved_above_kpa,
    d.vpd_low_eff_kpa,
    d.vpd_high_eff_kpa,
    d.vpd_high_eff_kpa + d.fog_escalation_kpa AS vpd_vent_fog_on_above_kpa,
    d.firmware_vpd_high + d.fog_escalation_kpa AS vpd_sealed_fog_on_above_kpa
FROM derived d
ORDER BY d.ts;
$$;

COMMENT ON FUNCTION fn_band_timeline(timestamptz, timestamptz, interval, text) IS
    'Actual-to-forecast band timeline for dashboards: historical firmware-pushed setpoints through now, dispatcher-projected band after now, crop provenance, and firmware-derived trigger/padding thresholds.';

ALTER FUNCTION fn_band_timeline(timestamptz, timestamptz, interval, text) ROWS 10000;

DROP FUNCTION IF EXISTS fn_band_setpoint_provenance(timestamptz, text);

CREATE OR REPLACE FUNCTION fn_band_setpoint_provenance(
    p_ts timestamptz DEFAULT now(),
    p_greenhouse_id text DEFAULT 'vallery'
)
RETURNS TABLE (
    ts timestamptz,
    greenhouse_id text,
    parameter text,
    axis text,
    edge text,
    crop_target_value double precision,
    dispatcher_value double precision,
    firmware_setpoint_value double precision,
    firmware_setpoint_ts timestamptz,
    cfg_readback_value double precision,
    cfg_readback_ts timestamptz,
    latest_plan_id text,
    latest_plan_created_at timestamptz,
    latest_planner_instance text,
    automation_source text,
    source_chain text,
    displayed_on_operator_graph boolean
)
LANGUAGE sql
STABLE
AS $$
WITH crop AS (
    SELECT *
      FROM fn_band_setpoints(p_ts)
     LIMIT 1
),
house AS (
    SELECT *
      FROM fn_house_vpd_control_band(p_ts)
     LIMIT 1
),
latest_plan AS (
    SELECT pj.plan_id, pj.created_at, pj.planner_instance
      FROM plan_journal pj
     WHERE COALESCE(pj.greenhouse_id, 'vallery') = p_greenhouse_id
       AND pj.created_at <= p_ts
     ORDER BY pj.created_at DESC
     LIMIT 1
),
params AS (
    SELECT *
      FROM (
          VALUES
              ('temp_low'::text,  'temp'::text, 'low'::text,  (SELECT temp_low FROM crop),       (SELECT temp_low FROM crop),       'fn_band_setpoints crop temperature curve'::text),
              ('temp_high'::text, 'temp'::text, 'high'::text, (SELECT temp_high FROM crop),      (SELECT temp_high FROM crop),      'fn_band_setpoints crop temperature curve'::text),
              ('vpd_low'::text,   'vpd'::text,  'low'::text,  (SELECT crop_vpd_low FROM house),  (SELECT house_vpd_low FROM house), 'fn_house_vpd_control_band crop plus zone VPD curve'::text),
              ('vpd_high'::text,  'vpd'::text,  'high'::text, (SELECT crop_vpd_high FROM house), (SELECT house_vpd_high FROM house), 'fn_house_vpd_control_band crop plus zone VPD curve'::text)
      ) AS p(parameter, axis, edge, crop_target_value, dispatcher_value, automation_source)
)
SELECT
    p_ts AS ts,
    p_greenhouse_id AS greenhouse_id,
    p.parameter,
    p.axis,
    p.edge,
    p.crop_target_value,
    p.dispatcher_value,
    fw.value AS firmware_setpoint_value,
    fw.ts AS firmware_setpoint_ts,
    rb.value AS cfg_readback_value,
    rb.ts AS cfg_readback_ts,
    lp.plan_id AS latest_plan_id,
    lp.created_at AS latest_plan_created_at,
    lp.planner_instance AS latest_planner_instance,
    p.automation_source,
    CASE
        WHEN p.axis = 'temp' THEN
            'crop profiles -> fn_band_setpoints() -> setpoint_dispatcher/API fallback -> setpoint_changes -> ESP32 cfg_* readback'
        ELSE
            'crop profiles + zone VPD targets -> fn_house_vpd_control_band() -> setpoint_dispatcher/API fallback -> setpoint_changes -> ESP32 cfg_* readback'
    END AS source_chain,
    true AS displayed_on_operator_graph
FROM params p
LEFT JOIN LATERAL (
    SELECT sc.value, sc.ts
      FROM setpoint_changes sc
     WHERE sc.greenhouse_id = p_greenhouse_id
       AND sc.parameter = p.parameter
       AND sc.ts <= p_ts
       AND (sc.expired_at IS NULL OR sc.expired_at > p_ts)
     ORDER BY sc.ts DESC
     LIMIT 1
) fw ON true
LEFT JOIN LATERAL (
    SELECT ss.value, ss.ts
      FROM setpoint_snapshot ss
     WHERE ss.greenhouse_id = p_greenhouse_id
       AND ss.parameter = p.parameter
       AND ss.ts <= p_ts
     ORDER BY ss.ts DESC
     LIMIT 1
) rb ON true
LEFT JOIN latest_plan lp ON true
ORDER BY p.axis, p.edge;
$$;

COMMENT ON FUNCTION fn_band_setpoint_provenance(timestamptz, text) IS
    'Current four-edge band provenance: crop target curve, dispatcher-derived value, latest pushed firmware setpoint, cfg_* readback, latest planner context, and source chain for operator table views.';

ALTER FUNCTION fn_band_setpoint_provenance(timestamptz, text) ROWS 4;

CREATE OR REPLACE FUNCTION fn_band_trace(
    p_start timestamptz,
    p_end timestamptz,
    p_greenhouse_id text DEFAULT 'vallery'
)
RETURNS TABLE (
    ts timestamptz,
    greenhouse_id text,
    temp_avg double precision,
    vpd_avg double precision,
    rh_avg double precision,
    dew_point double precision,
    temp_avg_smooth_15m double precision,
    vpd_avg_smooth_30m double precision,
    crop_temp_low double precision,
    crop_temp_high double precision,
    crop_vpd_low double precision,
    crop_vpd_high double precision,
    vpd_target_south double precision,
    vpd_target_west double precision,
    vpd_target_east double precision,
    vpd_target_center double precision,
    house_vpd_low double precision,
    house_vpd_high double precision,
    fw_temp_low double precision,
    fw_temp_high double precision,
    fw_vpd_low double precision,
    fw_vpd_high double precision,
    fw_temp_low_ts timestamptz,
    fw_temp_high_ts timestamptz,
    fw_vpd_low_ts timestamptz,
    fw_vpd_high_ts timestamptz,
    rb_temp_low double precision,
    rb_temp_high double precision,
    rb_vpd_low double precision,
    rb_vpd_high double precision,
    rb_temp_low_ts timestamptz,
    rb_temp_high_ts timestamptz,
    rb_vpd_low_ts timestamptz,
    rb_vpd_high_ts timestamptz,
    crop_temp_in_band boolean,
    crop_vpd_in_band boolean,
    crop_both_in_band boolean,
    fw_temp_in_band boolean,
    fw_vpd_in_band boolean,
    fw_both_in_band boolean,
    readback_matches_fw_temp boolean,
    readback_matches_fw_vpd boolean,
    readback_matches_fw_band boolean,
    fw_minus_crop_temp_low_f double precision,
    fw_minus_crop_temp_high_f double precision,
    fw_minus_crop_vpd_low_kpa double precision,
    fw_minus_crop_vpd_high_kpa double precision,
    trace_quality_flag text
)
LANGUAGE sql
STABLE
AS $$
WITH climate_window AS (
    SELECT
        c.ts,
        c.greenhouse_id,
        c.temp_avg,
        c.vpd_avg,
        c.rh_avg,
        c.dew_point,
        avg(c.temp_avg) OVER (
            PARTITION BY c.greenhouse_id
            ORDER BY c.ts
            RANGE BETWEEN interval '15 minutes' PRECEDING AND CURRENT ROW
        )::double precision AS temp_avg_smooth_15m,
        avg(c.vpd_avg) OVER (
            PARTITION BY c.greenhouse_id
            ORDER BY c.ts
            RANGE BETWEEN interval '30 minutes' PRECEDING AND CURRENT ROW
        )::double precision AS vpd_avg_smooth_30m
    FROM climate c
    WHERE c.greenhouse_id = p_greenhouse_id
      AND c.ts >= p_start
      AND c.ts <= p_end
      AND c.temp_avg IS NOT NULL
      AND c.vpd_avg IS NOT NULL
)
SELECT
    cw.ts,
    cw.greenhouse_id,
    cw.temp_avg,
    cw.vpd_avg,
    cw.rh_avg,
    cw.dew_point,
    cw.temp_avg_smooth_15m,
    cw.vpd_avg_smooth_30m,
    crop.temp_low AS crop_temp_low,
    crop.temp_high AS crop_temp_high,
    house.crop_vpd_low,
    house.crop_vpd_high,
    house.vpd_target_south,
    house.vpd_target_west,
    house.vpd_target_east,
    house.vpd_target_center,
    house.house_vpd_low,
    house.house_vpd_high,
    fw_temp_low.value AS fw_temp_low,
    fw_temp_high.value AS fw_temp_high,
    fw_vpd_low.value AS fw_vpd_low,
    fw_vpd_high.value AS fw_vpd_high,
    fw_temp_low.ts AS fw_temp_low_ts,
    fw_temp_high.ts AS fw_temp_high_ts,
    fw_vpd_low.ts AS fw_vpd_low_ts,
    fw_vpd_high.ts AS fw_vpd_high_ts,
    rb_temp_low.value AS rb_temp_low,
    rb_temp_high.value AS rb_temp_high,
    rb_vpd_low.value AS rb_vpd_low,
    rb_vpd_high.value AS rb_vpd_high,
    rb_temp_low.ts AS rb_temp_low_ts,
    rb_temp_high.ts AS rb_temp_high_ts,
    rb_vpd_low.ts AS rb_vpd_low_ts,
    rb_vpd_high.ts AS rb_vpd_high_ts,
    (cw.temp_avg BETWEEN crop.temp_low AND crop.temp_high) AS crop_temp_in_band,
    (cw.vpd_avg BETWEEN house.crop_vpd_low AND house.crop_vpd_high) AS crop_vpd_in_band,
    (
        cw.temp_avg BETWEEN crop.temp_low AND crop.temp_high
        AND cw.vpd_avg BETWEEN house.crop_vpd_low AND house.crop_vpd_high
    ) AS crop_both_in_band,
    (cw.temp_avg BETWEEN fw_temp_low.value AND fw_temp_high.value) AS fw_temp_in_band,
    (cw.vpd_avg BETWEEN fw_vpd_low.value AND fw_vpd_high.value) AS fw_vpd_in_band,
    (
        cw.temp_avg BETWEEN fw_temp_low.value AND fw_temp_high.value
        AND cw.vpd_avg BETWEEN fw_vpd_low.value AND fw_vpd_high.value
    ) AS fw_both_in_band,
    (
        rb_temp_low.value IS NOT NULL
        AND rb_temp_high.value IS NOT NULL
        AND fw_temp_low.value IS NOT NULL
        AND fw_temp_high.value IS NOT NULL
        AND abs(rb_temp_low.value - fw_temp_low.value) / greatest(abs(fw_temp_low.value), 1e-3) < 0.01
        AND abs(rb_temp_high.value - fw_temp_high.value) / greatest(abs(fw_temp_high.value), 1e-3) < 0.01
    ) AS readback_matches_fw_temp,
    (
        rb_vpd_low.value IS NOT NULL
        AND rb_vpd_high.value IS NOT NULL
        AND fw_vpd_low.value IS NOT NULL
        AND fw_vpd_high.value IS NOT NULL
        AND abs(rb_vpd_low.value - fw_vpd_low.value) / greatest(abs(fw_vpd_low.value), 1e-3) < 0.01
        AND abs(rb_vpd_high.value - fw_vpd_high.value) / greatest(abs(fw_vpd_high.value), 1e-3) < 0.01
    ) AS readback_matches_fw_vpd,
    (
        rb_temp_low.value IS NOT NULL
        AND rb_temp_high.value IS NOT NULL
        AND rb_vpd_low.value IS NOT NULL
        AND rb_vpd_high.value IS NOT NULL
        AND fw_temp_low.value IS NOT NULL
        AND fw_temp_high.value IS NOT NULL
        AND fw_vpd_low.value IS NOT NULL
        AND fw_vpd_high.value IS NOT NULL
        AND abs(rb_temp_low.value - fw_temp_low.value) / greatest(abs(fw_temp_low.value), 1e-3) < 0.01
        AND abs(rb_temp_high.value - fw_temp_high.value) / greatest(abs(fw_temp_high.value), 1e-3) < 0.01
        AND abs(rb_vpd_low.value - fw_vpd_low.value) / greatest(abs(fw_vpd_low.value), 1e-3) < 0.01
        AND abs(rb_vpd_high.value - fw_vpd_high.value) / greatest(abs(fw_vpd_high.value), 1e-3) < 0.01
    ) AS readback_matches_fw_band,
    fw_temp_low.value - crop.temp_low AS fw_minus_crop_temp_low_f,
    fw_temp_high.value - crop.temp_high AS fw_minus_crop_temp_high_f,
    fw_vpd_low.value - house.crop_vpd_low AS fw_minus_crop_vpd_low_kpa,
    fw_vpd_high.value - house.crop_vpd_high AS fw_minus_crop_vpd_high_kpa,
    CASE
        WHEN crop.temp_low IS NULL
          OR crop.temp_high IS NULL
          OR house.crop_vpd_low IS NULL
          OR house.crop_vpd_high IS NULL
            THEN 'missing_crop_band'
        WHEN fw_temp_low.value IS NULL
          OR fw_temp_high.value IS NULL
          OR fw_vpd_low.value IS NULL
          OR fw_vpd_high.value IS NULL
            THEN 'missing_fw_band'
        WHEN rb_temp_low.value IS NULL
          OR rb_temp_high.value IS NULL
          OR rb_vpd_low.value IS NULL
          OR rb_vpd_high.value IS NULL
            THEN 'missing_readback'
        WHEN NOT (
            abs(rb_temp_low.value - fw_temp_low.value) / greatest(abs(fw_temp_low.value), 1e-3) < 0.01
            AND abs(rb_temp_high.value - fw_temp_high.value) / greatest(abs(fw_temp_high.value), 1e-3) < 0.01
            AND abs(rb_vpd_low.value - fw_vpd_low.value) / greatest(abs(fw_vpd_low.value), 1e-3) < 0.01
            AND abs(rb_vpd_high.value - fw_vpd_high.value) / greatest(abs(fw_vpd_high.value), 1e-3) < 0.01
        )
            THEN 'readback_drift'
        ELSE 'ok'
    END AS trace_quality_flag
FROM climate_window cw
CROSS JOIN LATERAL fn_band_setpoints(cw.ts) AS crop
CROSS JOIN LATERAL fn_house_vpd_control_band(cw.ts) AS house
LEFT JOIN LATERAL (
    SELECT value, ts
      FROM setpoint_changes
     WHERE greenhouse_id = p_greenhouse_id
       AND parameter = 'temp_low'
       AND ts <= cw.ts
       AND (expired_at IS NULL OR expired_at > cw.ts)
     ORDER BY ts DESC
     LIMIT 1
) AS fw_temp_low ON true
LEFT JOIN LATERAL (
    SELECT value, ts
      FROM setpoint_changes
     WHERE greenhouse_id = p_greenhouse_id
       AND parameter = 'temp_high'
       AND ts <= cw.ts
       AND (expired_at IS NULL OR expired_at > cw.ts)
     ORDER BY ts DESC
     LIMIT 1
) AS fw_temp_high ON true
LEFT JOIN LATERAL (
    SELECT value, ts
      FROM setpoint_changes
     WHERE greenhouse_id = p_greenhouse_id
       AND parameter = 'vpd_low'
       AND ts <= cw.ts
       AND (expired_at IS NULL OR expired_at > cw.ts)
     ORDER BY ts DESC
     LIMIT 1
) AS fw_vpd_low ON true
LEFT JOIN LATERAL (
    SELECT value, ts
      FROM setpoint_changes
     WHERE greenhouse_id = p_greenhouse_id
       AND parameter = 'vpd_high'
       AND ts <= cw.ts
       AND (expired_at IS NULL OR expired_at > cw.ts)
     ORDER BY ts DESC
     LIMIT 1
) AS fw_vpd_high ON true
LEFT JOIN LATERAL (
    SELECT value, ts
      FROM setpoint_snapshot
     WHERE greenhouse_id = p_greenhouse_id
       AND parameter = 'temp_low'
       AND ts <= cw.ts
     ORDER BY ts DESC
     LIMIT 1
) AS rb_temp_low ON true
LEFT JOIN LATERAL (
    SELECT value, ts
      FROM setpoint_snapshot
     WHERE greenhouse_id = p_greenhouse_id
       AND parameter = 'temp_high'
       AND ts <= cw.ts
     ORDER BY ts DESC
     LIMIT 1
) AS rb_temp_high ON true
LEFT JOIN LATERAL (
    SELECT value, ts
      FROM setpoint_snapshot
     WHERE greenhouse_id = p_greenhouse_id
       AND parameter = 'vpd_low'
       AND ts <= cw.ts
     ORDER BY ts DESC
     LIMIT 1
) AS rb_vpd_low ON true
LEFT JOIN LATERAL (
    SELECT value, ts
      FROM setpoint_snapshot
     WHERE greenhouse_id = p_greenhouse_id
       AND parameter = 'vpd_high'
       AND ts <= cw.ts
     ORDER BY ts DESC
     LIMIT 1
) AS rb_vpd_high ON true
ORDER BY cw.ts;
$$;

COMMENT ON FUNCTION fn_band_trace(timestamptz, timestamptz, text) IS
    'Canonical sample-level band trace: raw/smoothed climate, crop targets, firmware setpoints, cfg readbacks, compliance flags, and trace quality.';

ALTER FUNCTION fn_band_trace(timestamptz, timestamptz, text) ROWS 10000;

CREATE OR REPLACE VIEW v_band_trace_recent AS
SELECT *
  FROM fn_band_trace(now() - interval '14 days', now(), 'vallery');

COMMENT ON VIEW v_band_trace_recent IS
    'Rolling 14-day canonical band trace for the production greenhouse.';

CREATE OR REPLACE VIEW v_band_trace_latest AS
SELECT *
  FROM fn_band_trace(now() - interval '2 hours', now(), 'vallery')
 ORDER BY ts DESC
 LIMIT 1;

COMMENT ON VIEW v_band_trace_latest IS
    'Latest production greenhouse band-trace sample with crop, firmware, and readback bands.';
