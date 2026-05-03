-- Migration 102: data backlog completion surfaces
--
-- Completes the software/data portion of the 2026-05-01 data-science audit:
-- historical daily_summary repair, water/irrigation event ledgers, energy
-- reconciliation, alert lifecycle cleanup, sensor registry coverage, forecast
-- action outcomes, setpoint delivery lifecycle, crop outcome readiness, and
-- owner-facing story marts. Physical sensors remain represented as explicit
-- instrumentation requirements until hardware is installed.

-- ---------------------------------------------------------------------------
-- 1. Historical daily_summary backfill and measured energy reconciliation
-- ---------------------------------------------------------------------------

WITH climate_daily AS (
    SELECT
        (ts AT TIME ZONE 'America/Denver')::date AS date,
        min(temp_avg) AS temp_min,
        max(temp_avg) AS temp_max,
        avg(temp_avg) AS temp_avg,
        min(rh_avg) AS rh_min,
        max(rh_avg) AS rh_max,
        avg(rh_avg) AS rh_avg,
        min(vpd_avg) AS vpd_min,
        max(vpd_avg) AS vpd_max,
        avg(vpd_avg) AS vpd_avg,
        avg(co2_ppm) AS co2_avg,
        max(dli_today) AS dli_final,
        min(outdoor_temp_f) AS outdoor_temp_min,
        max(outdoor_temp_f) AS outdoor_temp_max
    FROM climate
    GROUP BY (ts AT TIME ZONE 'America/Denver')::date
)
UPDATE daily_summary ds
SET temp_min = cd.temp_min,
    temp_max = cd.temp_max,
    temp_avg = cd.temp_avg,
    rh_min = cd.rh_min,
    rh_max = cd.rh_max,
    rh_avg = cd.rh_avg,
    vpd_min = cd.vpd_min,
    vpd_max = cd.vpd_max,
    vpd_avg = cd.vpd_avg,
    co2_avg = cd.co2_avg,
    dli_final = cd.dli_final,
    outdoor_temp_min = cd.outdoor_temp_min,
    outdoor_temp_max = cd.outdoor_temp_max,
    captured_at = COALESCE(ds.captured_at, now())
FROM climate_daily cd
WHERE ds.date = cd.date;

UPDATE daily_summary ds
SET min_dp_margin_f = dpr.min_margin_f,
    dp_risk_hours = dpr.risk_hours,
    captured_at = COALESCE(ds.captured_at, now())
FROM v_dew_point_risk dpr
WHERE ds.date = dpr.date;

UPDATE daily_summary ds
SET water_used_gal = wd.used_gal,
    captured_at = COALESCE(ds.captured_at, now())
FROM v_water_daily wd
WHERE ds.date = wd.day::date;

UPDATE daily_summary ds
SET kwh_total = ed.measured_kwh::double precision,
    peak_kw = round((ed.peak_watts / 1000.0)::numeric, 3)::double precision,
    cost_electric = round((ed.measured_kwh * 0.111)::numeric, 2)::double precision,
    cost_total = round(((ed.measured_kwh * 0.111)
        + COALESCE(ds.cost_gas, 0)
        + COALESCE(ds.cost_water, 0))::numeric, 2)::double precision,
    captured_at = COALESCE(ds.captured_at, now())
FROM v_energy_daily ed
WHERE ds.date = ed.date
  AND ed.measured_kwh IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 2. Water event ledger and irrigation repair
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS water_meter_events (
    id bigserial PRIMARY KEY,
    ts timestamptz NOT NULL,
    greenhouse_id text DEFAULT 'vallery' REFERENCES greenhouses(id),
    source text NOT NULL DEFAULT 'climate.water_total_gal',
    meter_id text NOT NULL DEFAULT 'main_pulse',
    event_type text NOT NULL CHECK (event_type IN ('initial', 'delta', 'reset', 'phantom_zero')),
    prior_total_gal double precision,
    total_gal double precision,
    delta_gal double precision NOT NULL DEFAULT 0,
    quality_flag text NOT NULL DEFAULT 'ok',
    raw jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (ts, source, meter_id, event_type)
);

CREATE INDEX IF NOT EXISTS idx_water_meter_events_ts ON water_meter_events (ts DESC);
CREATE INDEX IF NOT EXISTS idx_water_meter_events_day
    ON water_meter_events (((ts AT TIME ZONE 'America/Denver')::date), meter_id);

COMMENT ON TABLE water_meter_events IS
'Event ledger derived from cumulative water meter snapshots. Holds deltas, resets, and phantom-zero samples so daily totals are auditable.';

WITH ordered AS (
    SELECT
        ts,
        COALESCE(greenhouse_id, 'vallery') AS greenhouse_id,
        water_total_gal AS total_gal,
        lag(water_total_gal) OVER (
            PARTITION BY COALESCE(greenhouse_id, 'vallery')
            ORDER BY ts
        ) AS prior_total_gal
    FROM climate
    WHERE water_total_gal IS NOT NULL
),
events AS (
    SELECT
        ts,
        greenhouse_id,
        prior_total_gal,
        total_gal,
        CASE
            WHEN total_gal <= 0 THEN 'phantom_zero'
            WHEN prior_total_gal IS NULL THEN 'initial'
            WHEN total_gal < prior_total_gal THEN 'reset'
            ELSE 'delta'
        END AS event_type,
        CASE
            WHEN prior_total_gal IS NOT NULL
             AND prior_total_gal > 0
             AND total_gal > prior_total_gal THEN total_gal - prior_total_gal
            ELSE 0
        END AS delta_gal,
        CASE
            WHEN total_gal <= 0 THEN 'phantom_zero'
            WHEN prior_total_gal IS NOT NULL AND total_gal < prior_total_gal THEN 'counter_reset'
            WHEN prior_total_gal IS NOT NULL AND total_gal - prior_total_gal > 200 THEN 'high_delta'
            ELSE 'ok'
        END AS quality_flag
    FROM ordered
    WHERE prior_total_gal IS NULL
       OR total_gal <= 0
       OR total_gal < prior_total_gal
       OR total_gal > prior_total_gal
)
INSERT INTO water_meter_events (
    ts, greenhouse_id, prior_total_gal, total_gal, event_type, delta_gal, quality_flag, raw
)
SELECT
    DISTINCT ON (ts, event_type)
    ts,
    greenhouse_id,
    prior_total_gal,
    total_gal,
    event_type,
    delta_gal,
    quality_flag,
    jsonb_build_object('backfill', 'migration_102')
FROM events
ORDER BY ts, event_type, total_gal DESC NULLS LAST
ON CONFLICT (ts, source, meter_id, event_type) DO UPDATE
SET prior_total_gal = EXCLUDED.prior_total_gal,
    total_gal = EXCLUDED.total_gal,
    delta_gal = EXCLUDED.delta_gal,
    quality_flag = EXCLUDED.quality_flag,
    raw = water_meter_events.raw || EXCLUDED.raw;

CREATE OR REPLACE VIEW v_water_meter_daily AS
SELECT
    ((ts AT TIME ZONE 'America/Denver')::date::timestamp AT TIME ZONE 'America/Denver') AS day,
    greenhouse_id,
    meter_id,
    round(sum(delta_gal)::numeric, 3)::double precision AS used_gal,
    count(*) FILTER (WHERE event_type = 'delta') AS delta_events,
    count(*) FILTER (WHERE event_type = 'reset') AS reset_events,
    count(*) FILTER (WHERE event_type = 'phantom_zero') AS phantom_zero_events,
    count(*) FILTER (WHERE quality_flag <> 'ok') AS quality_events
FROM water_meter_events
WHERE event_type = 'delta'
GROUP BY 1, greenhouse_id, meter_id
ORDER BY day DESC;

COMMENT ON VIEW v_water_meter_daily IS
'Daily local-day water totals from water_meter_events. Includes event counts for auditability.';

CREATE OR REPLACE VIEW v_water_daily AS
SELECT
    day,
    round(sum(used_gal)::numeric, 3)::double precision AS used_gal
FROM v_water_meter_daily
GROUP BY day
ORDER BY day DESC;

COMMENT ON VIEW v_water_daily IS
'Canonical America/Denver daily water usage from water_meter_events positive deltas.';

ALTER TABLE irrigation_log ADD COLUMN IF NOT EXISTS weather_skip boolean;
ALTER TABLE irrigation_log ADD COLUMN IF NOT EXISTS fertigation boolean NOT NULL DEFAULT false;
ALTER TABLE irrigation_log ADD COLUMN IF NOT EXISTS metering_method text NOT NULL DEFAULT 'unknown';

WITH ordered AS (
    SELECT
        ts,
        equipment,
        state,
        lag(state) OVER (PARTITION BY equipment ORDER BY ts) AS prev_state
    FROM equipment_state
    WHERE equipment IN ('drip_wall', 'drip_center')
),
starts AS (
    SELECT ts AS actual_start, equipment
    FROM ordered
    WHERE state = true
      AND COALESCE(prev_state, false) = false
),
events AS (
    SELECT
        s.actual_start,
        off_event.ts AS actual_end,
        CASE s.equipment
            WHEN 'drip_wall' THEN 'south_wall'
            ELSE 'center'
        END AS zone,
        s.equipment,
        EXTRACT(epoch FROM (off_event.ts - s.actual_start)) AS duration_s,
        COALESCE(weather.state, false) AS weather_skip,
        EXISTS (
            SELECT 1
            FROM equipment_state fert
            WHERE fert.equipment = CASE s.equipment
                WHEN 'drip_wall' THEN 'drip_wall_fert'
                ELSE 'drip_center_fert'
            END
              AND fert.state = true
              AND fert.ts >= s.actual_start
              AND fert.ts <= COALESCE(off_event.ts, s.actual_start + interval '1 hour')
        ) AS fertigation
    FROM starts s
    LEFT JOIN LATERAL (
        SELECT ts
        FROM equipment_state e
        WHERE e.equipment = s.equipment
          AND e.state = false
          AND e.ts > s.actual_start
        ORDER BY ts
        LIMIT 1
    ) off_event ON true
    LEFT JOIN LATERAL (
        SELECT state
        FROM equipment_state e
        WHERE e.equipment = 'irrigation_weather_skip'
          AND e.ts <= s.actual_start
        ORDER BY ts DESC
        LIMIT 1
    ) weather ON true
)
INSERT INTO irrigation_log (
    ts, zone, schedule_id, scheduled_time, actual_start, actual_end,
    volume_gal, source, weather_skip, fertigation, metering_method, notes, greenhouse_id
)
SELECT
    e.actual_start,
    e.zone,
    sch.id,
    sch.start_time,
    e.actual_start,
    e.actual_end,
    round(((e.duration_s / 60.0) * 2.0)::numeric, 2) AS volume_gal,
    CASE WHEN sch.id IS NULL THEN 'override' ELSE 'scheduled' END AS source,
    e.weather_skip,
    e.fertigation,
    'runtime_estimate_2_gpm',
    'migration_102 replay from equipment_state ' || e.equipment,
    'vallery'
FROM events e
LEFT JOIN irrigation_schedule sch
  ON sch.zone = e.zone
 AND sch.enabled = true
WHERE e.actual_end IS NOT NULL
  AND e.duration_s BETWEEN 1 AND 3600
  AND NOT EXISTS (
      SELECT 1
      FROM irrigation_log il
      WHERE il.zone = e.zone
        AND abs(EXTRACT(epoch FROM (il.actual_start - e.actual_start))) < 30
  );

DROP VIEW IF EXISTS v_irrigation_log;

CREATE VIEW v_irrigation_log AS
SELECT *,
    CASE WHEN actual_end IS NOT NULL THEN
        EXTRACT(epoch FROM (actual_end - actual_start))::integer
    END AS duration_s
FROM irrigation_log;

COMMENT ON VIEW v_irrigation_log IS
'Irrigation log with computed duration and migration-102 weather/fertigation/metering fields.';

CREATE OR REPLACE VIEW v_irrigation_accountability AS
SELECT
    (actual_start AT TIME ZONE 'America/Denver')::date AS date,
    zone,
    count(*) AS events,
    round((sum(EXTRACT(epoch FROM (actual_end - actual_start))) / 60.0)::numeric, 1) AS runtime_min,
    round(sum(volume_gal)::numeric, 2) AS volume_gal,
    count(*) FILTER (WHERE volume_gal IS NULL) AS missing_volume_events,
    count(*) FILTER (WHERE weather_skip IS TRUE) AS weather_skip_events,
    count(*) FILTER (WHERE fertigation IS TRUE) AS fertigation_events,
    max(actual_start) AS latest_event
FROM irrigation_log
WHERE actual_end IS NOT NULL
GROUP BY 1, zone
ORDER BY date DESC, zone;

COMMENT ON VIEW v_irrigation_accountability IS
'Daily irrigation events by zone with estimated volume, weather-skip, and fertigation flags.';

-- ---------------------------------------------------------------------------
-- 3. Alert, sensor, forecast-action, and setpoint lifecycle cleanup
-- ---------------------------------------------------------------------------

UPDATE alert_log
SET disposition = 'resolved',
    updated_at = now(),
    resolution = COALESCE(resolution, 'migration_102 normalized resolved_at/disposition mismatch')
WHERE resolved_at IS NOT NULL
  AND disposition <> 'resolved';

WITH missing_required AS (
    SELECT DISTINCT
        cfg.target_table,
        cfg.target_column,
        cfg.entity_name,
        cfg.entity_type,
        cfg.unit,
        cfg.description
    FROM greenhouse_sensor_config cfg
    WHERE cfg.is_required = true
      AND cfg.target_table = 'climate'
)
UPDATE sensor_registry sr
SET active = true,
    updated_at = now(),
    notes = concat_ws('; ', NULLIF(sr.notes, ''), 'migration_102 required coverage repair')
FROM missing_required cfg
WHERE sr.source_table = cfg.target_table
  AND sr.source_column = cfg.target_column;

WITH missing_required AS (
    SELECT DISTINCT
        cfg.target_table,
        cfg.target_column,
        cfg.entity_name,
        cfg.entity_type,
        cfg.unit,
        cfg.description
    FROM greenhouse_sensor_config cfg
    WHERE cfg.is_required = true
      AND cfg.target_table = 'climate'
)
INSERT INTO sensor_registry (
    sensor_id, entity_id, type, source_table, source_column, unit,
    expected_interval_s, active, notes, description, installed_date
)
SELECT
    'climate.' || cfg.target_column,
    cfg.entity_name,
    cfg.entity_type,
    cfg.target_table,
    cfg.target_column,
    cfg.unit,
    CASE
        WHEN cfg.target_column LIKE 'hydro_%' THEN 300
        ELSE 60
    END,
    true,
    'migration_102 required coverage repair',
    cfg.description,
    CURRENT_DATE
FROM missing_required cfg
WHERE NOT EXISTS (
    SELECT 1
    FROM sensor_registry sr
    WHERE sr.source_table = cfg.target_table
      AND sr.source_column = cfg.target_column
);

CREATE OR REPLACE VIEW v_sensor_staleness AS
WITH last_readings AS (
    SELECT
        sr.sensor_id,
        sr.type,
        sr.zone,
        sr.expected_interval_s,
        sr.source_table,
        sr.source_column,
        CASE sr.source_table
            WHEN 'climate' THEN (
                SELECT max(c.ts)
                FROM climate c
                WHERE c.ts > now() - GREATEST(
                    interval '2 hours',
                    sr.expected_interval_s::double precision * interval '2 seconds'
                )
                  AND CASE sr.source_column
                    WHEN 'temp_avg' THEN c.temp_avg
                    WHEN 'temp_north' THEN c.temp_north
                    WHEN 'temp_south' THEN c.temp_south
                    WHEN 'temp_east' THEN c.temp_east
                    WHEN 'temp_west' THEN c.temp_west
                    WHEN 'temp_case' THEN c.temp_case
                    WHEN 'temp_control' THEN c.temp_control
                    WHEN 'temp_intake' THEN c.temp_intake
                    WHEN 'rh_avg' THEN c.rh_avg
                    WHEN 'rh_north' THEN c.rh_north
                    WHEN 'rh_south' THEN c.rh_south
                    WHEN 'rh_east' THEN c.rh_east
                    WHEN 'rh_west' THEN c.rh_west
                    WHEN 'rh_case' THEN c.rh_case
                    WHEN 'intake_rh' THEN c.intake_rh
                    WHEN 'vpd_avg' THEN c.vpd_avg
                    WHEN 'vpd_north' THEN c.vpd_north
                    WHEN 'vpd_south' THEN c.vpd_south
                    WHEN 'vpd_east' THEN c.vpd_east
                    WHEN 'vpd_west' THEN c.vpd_west
                    WHEN 'vpd_control' THEN c.vpd_control
                    WHEN 'intake_vpd' THEN c.intake_vpd
                    WHEN 'co2_ppm' THEN c.co2_ppm
                    WHEN 'lux' THEN c.lux
                    WHEN 'dli_today' THEN c.dli_today
                    WHEN 'ppfd' THEN c.ppfd
                    WHEN 'dli_par_today' THEN c.dli_par_today
                    WHEN 'dew_point' THEN c.dew_point
                    WHEN 'abs_humidity' THEN c.abs_humidity
                    WHEN 'enthalpy_delta' THEN c.enthalpy_delta
                    WHEN 'flow_gpm' THEN c.flow_gpm
                    WHEN 'water_total_gal' THEN c.water_total_gal
                    WHEN 'mister_water_today' THEN c.mister_water_today
                    WHEN 'outdoor_temp_f' THEN c.outdoor_temp_f
                    WHEN 'outdoor_rh_pct' THEN c.outdoor_rh_pct
                    WHEN 'wind_speed_mph' THEN c.wind_speed_mph
                    WHEN 'wind_direction_deg' THEN c.wind_direction_deg
                    WHEN 'wind_gust_mph' THEN c.wind_gust_mph
                    WHEN 'wind_lull_mph' THEN c.wind_lull_mph
                    WHEN 'wind_speed_avg_mph' THEN c.wind_speed_avg_mph
                    WHEN 'wind_direction_avg_deg' THEN c.wind_direction_avg_deg
                    WHEN 'outdoor_lux' THEN c.outdoor_lux
                    WHEN 'outdoor_illuminance' THEN c.outdoor_illuminance
                    WHEN 'solar_irradiance_w_m2' THEN c.solar_irradiance_w_m2
                    WHEN 'solar_altitude_deg' THEN c.solar_altitude_deg
                    WHEN 'solar_azimuth_deg' THEN c.solar_azimuth_deg
                    WHEN 'pressure_hpa' THEN c.pressure_hpa
                    WHEN 'uv_index' THEN c.uv_index
                    WHEN 'precip_in' THEN c.precip_in
                    WHEN 'precip_intensity_in_h' THEN c.precip_intensity_in_h
                    WHEN 'feels_like_f' THEN c.feels_like_f
                    WHEN 'wet_bulb_temp_f' THEN c.wet_bulb_temp_f
                    WHEN 'vapor_pressure_inhg' THEN c.vapor_pressure_inhg
                    WHEN 'air_density_kg_m3' THEN c.air_density_kg_m3
                    WHEN 'lightning_count' THEN c.lightning_count::double precision
                    WHEN 'lightning_avg_dist_mi' THEN c.lightning_avg_dist_mi
                    WHEN 'hydro_ec_us_cm' THEN c.hydro_ec_us_cm
                    WHEN 'hydro_ph' THEN c.hydro_ph
                    WHEN 'hydro_tds_ppm' THEN c.hydro_tds_ppm
                    WHEN 'hydro_water_temp_f' THEN c.hydro_water_temp_f
                    WHEN 'hydro_orp_mv' THEN c.hydro_orp_mv
                    WHEN 'hydro_battery_pct' THEN c.hydro_battery_pct
                    WHEN 'soil_moisture_south_1' THEN c.soil_moisture_south_1
                    WHEN 'soil_temp_south_1' THEN c.soil_temp_south_1
                    WHEN 'soil_ec_south_1' THEN c.soil_ec_south_1
                    WHEN 'soil_moisture_south_2' THEN c.soil_moisture_south_2
                    WHEN 'soil_temp_south_2' THEN c.soil_temp_south_2
                    WHEN 'soil_moisture_west' THEN c.soil_moisture_west
                    WHEN 'soil_temp_west' THEN c.soil_temp_west
                    WHEN 'ph_input' THEN c.ph_input
                    WHEN 'ec_input' THEN c.ec_input
                    WHEN 'ph_runoff_wall' THEN c.ph_runoff_wall
                    WHEN 'ec_runoff_wall' THEN c.ec_runoff_wall
                    WHEN 'ph_runoff_center' THEN c.ph_runoff_center
                    WHEN 'ec_runoff_center' THEN c.ec_runoff_center
                    WHEN 'leaf_temp_north' THEN c.leaf_temp_north
                    WHEN 'leaf_temp_south' THEN c.leaf_temp_south
                    WHEN 'leaf_wetness_north' THEN c.leaf_wetness_north
                    WHEN 'leaf_wetness_south' THEN c.leaf_wetness_south
                    ELSE NULL::double precision
                  END IS NOT NULL
            )
            WHEN 'equipment_state' THEN (
                SELECT max(es.ts)
                FROM equipment_state es
                WHERE es.equipment = sr.source_column
            )
            WHEN 'system_state' THEN (
                SELECT max(ss.ts)
                FROM system_state ss
                WHERE ss.entity = sr.source_column
            )
            WHEN 'diagnostics' THEN (
                SELECT max(d.ts)
                FROM diagnostics d
                WHERE d.ts > now() - interval '2 hours'
            )
            ELSE NULL::timestamptz
        END AS last_seen_at
    FROM sensor_registry sr
    WHERE sr.active = true
)
SELECT
    sensor_id,
    type,
    zone,
    expected_interval_s,
    last_seen_at,
    EXTRACT(epoch FROM (now() - last_seen_at))::integer AS seconds_since,
    CASE
        WHEN last_seen_at IS NULL THEN true
        WHEN EXTRACT(epoch FROM (now() - last_seen_at)) > expected_interval_s * 2 THEN true
        ELSE false
    END AS is_stale,
    CASE
        WHEN last_seen_at IS NULL THEN NULL::numeric
        ELSE round((EXTRACT(epoch FROM (now() - last_seen_at)) / NULLIF(expected_interval_s, 0))::numeric, 1)
    END AS staleness_ratio
FROM last_readings;

ALTER TABLE forecast_action_log ADD COLUMN IF NOT EXISTS outcome_evaluated_at timestamptz;
ALTER TABLE forecast_action_log ADD COLUMN IF NOT EXISTS outcome_metrics jsonb NOT NULL DEFAULT '{}'::jsonb;

WITH scored AS (
    SELECT
        fl.id,
        fl.action_taken,
        fl.triggered_at,
        before_window.stress_score AS before_stress_score,
        after_window.stress_score AS after_stress_score
    FROM forecast_action_log fl
    LEFT JOIN LATERAL (
        SELECT avg(
            (CASE WHEN temp_avg > 85 THEN 1 ELSE 0 END)
          + (CASE WHEN temp_avg < 45 THEN 1 ELSE 0 END)
          + (CASE WHEN vpd_avg > 1.4 THEN 1 ELSE 0 END)
          + (CASE WHEN vpd_avg < 0.35 THEN 1 ELSE 0 END)
        ) AS stress_score
        FROM climate
        WHERE ts >= fl.triggered_at - interval '3 hours'
          AND ts < fl.triggered_at
    ) before_window ON true
    LEFT JOIN LATERAL (
        SELECT avg(
            (CASE WHEN temp_avg > 85 THEN 1 ELSE 0 END)
          + (CASE WHEN temp_avg < 45 THEN 1 ELSE 0 END)
          + (CASE WHEN vpd_avg > 1.4 THEN 1 ELSE 0 END)
          + (CASE WHEN vpd_avg < 0.35 THEN 1 ELSE 0 END)
        ) AS stress_score
        FROM climate
        WHERE ts > fl.triggered_at
          AND ts <= fl.triggered_at + interval '6 hours'
    ) after_window ON true
    WHERE fl.outcome IS NULL
)
UPDATE forecast_action_log fl
SET outcome = CASE
        WHEN s.action_taken = 'evaluated_ok' THEN 'no_action_required'
        WHEN s.triggered_at > now() - interval '6 hours' THEN 'pending'
        WHEN s.after_stress_score IS NULL THEN 'insufficient_followup_data'
        WHEN COALESCE(s.after_stress_score, 0) <= COALESCE(s.before_stress_score, 0) THEN 'climate_recovered'
        ELSE 'no_clear_improvement'
    END,
    outcome_evaluated_at = CASE
        WHEN s.action_taken = 'evaluated_ok' OR s.triggered_at <= now() - interval '6 hours' THEN now()
        ELSE NULL
    END,
    outcome_metrics = jsonb_build_object(
        'before_stress_score', s.before_stress_score,
        'after_stress_score', s.after_stress_score,
        'window', '3h_before_6h_after',
        'backfill', 'migration_102'
    )
FROM scored s
WHERE fl.id = s.id;

CREATE OR REPLACE VIEW v_forecast_action_outcomes AS
SELECT
    fl.id,
    fl.rule_name,
    fl.triggered_at,
    fl.action_taken,
    fl.plan_id,
    fl.param,
    fl.old_value,
    fl.new_value,
    COALESCE(fl.outcome, 'pending') AS outcome,
    fl.outcome_evaluated_at,
    fl.outcome_metrics,
    ds.date AS outcome_date,
    ds.compliance_pct,
    ds.stress_hours_heat,
    ds.stress_hours_vpd_high,
    ds.water_used_gal,
    ds.cost_total
FROM forecast_action_log fl
LEFT JOIN daily_summary ds
  ON ds.date = (fl.triggered_at AT TIME ZONE 'America/Denver')::date;

COMMENT ON VIEW v_forecast_action_outcomes IS
'Forecast action log joined to later climate/day outcomes. Historical rows are backfilled with coarse stress-window outcomes.';

ALTER TABLE setpoint_changes ADD COLUMN IF NOT EXISTS delivery_status text;
ALTER TABLE setpoint_changes ADD COLUMN IF NOT EXISTS expired_at timestamptz;
ALTER TABLE setpoint_changes ADD COLUMN IF NOT EXISTS superseded_by_ts timestamptz;

UPDATE setpoint_changes
SET delivery_status = 'confirmed'
WHERE confirmed_at IS NOT NULL
  AND delivery_status IS DISTINCT FROM 'confirmed';

WITH superseded AS (
    SELECT
        sc.ctid AS row_id,
        min(newer.ts) AS newer_ts
    FROM setpoint_changes sc
    JOIN setpoint_changes newer
      ON newer.parameter = sc.parameter
     AND newer.ts > sc.ts
    WHERE sc.confirmed_at IS NULL
      AND sc.ts < now() - interval '24 hours'
    GROUP BY sc.ctid
)
UPDATE setpoint_changes sc
SET delivery_status = 'superseded',
    superseded_by_ts = s.newer_ts,
    expired_at = COALESCE(sc.expired_at, s.newer_ts)
FROM superseded s
WHERE sc.ctid = s.row_id
  AND sc.delivery_status IS DISTINCT FROM 'confirmed';

UPDATE setpoint_changes
SET delivery_status = 'expired',
    expired_at = COALESCE(expired_at, now())
WHERE confirmed_at IS NULL
  AND delivery_status IS NULL
  AND ts < now() - interval '24 hours';

UPDATE setpoint_changes
SET delivery_status = 'pending'
WHERE confirmed_at IS NULL
  AND delivery_status IS NULL;

UPDATE setpoint_plan
SET is_active = false
WHERE is_active = true
  AND ts <= now();

CREATE OR REPLACE VIEW v_setpoint_change_delivery AS
SELECT
    ts,
    parameter,
    value,
    source,
    greenhouse_id,
    confirmed_at,
    COALESCE(delivery_status,
        CASE WHEN confirmed_at IS NOT NULL THEN 'confirmed' ELSE 'pending' END
    ) AS delivery_status,
    expired_at,
    superseded_by_ts,
    round(EXTRACT(epoch FROM (confirmed_at - ts))::numeric, 1) AS confirm_latency_s
FROM setpoint_changes;

COMMENT ON VIEW v_setpoint_change_delivery IS
'Setpoint change confirmation lifecycle with explicit pending/superseded/expired/confirmed status.';

CREATE OR REPLACE VIEW v_alert_lifecycle_quality AS
SELECT
    severity,
    alert_type,
    count(*) AS alerts,
    count(*) FILTER (WHERE disposition = 'open') AS open_alerts,
    count(*) FILTER (WHERE disposition = 'acknowledged' AND resolved_at IS NULL) AS acknowledged_unresolved,
    count(*) FILTER (WHERE disposition = 'suppressed') AS suppressed_alerts,
    round((avg(EXTRACT(epoch FROM (resolved_at - ts)) / 60.0)
        FILTER (WHERE resolved_at IS NOT NULL))::numeric, 1) AS avg_mttr_min,
    max(ts) AS latest_ts
FROM alert_log
GROUP BY severity, alert_type
ORDER BY latest_ts DESC;

COMMENT ON VIEW v_alert_lifecycle_quality IS
'Alert lifecycle health: open/ack/suppressed counts and mean time to resolution by alert type.';

-- ---------------------------------------------------------------------------
-- 4. Crop outcome layer and instrumentation readiness
-- ---------------------------------------------------------------------------

ALTER TABLE observations ADD COLUMN IF NOT EXISTS plant_height_cm double precision;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS leaf_count integer;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS canopy_cover_pct double precision;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS flowering_count integer;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS fruit_count integer;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS root_condition text;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS mortality_count integer;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS stress_tags text[];

ALTER TABLE harvests ADD COLUMN IF NOT EXISTS salable_weight_kg double precision;
ALTER TABLE harvests ADD COLUMN IF NOT EXISTS cull_weight_kg double precision;
ALTER TABLE harvests ADD COLUMN IF NOT EXISTS cull_reason text;
ALTER TABLE harvests ADD COLUMN IF NOT EXISTS quality_reason text;
ALTER TABLE harvests ADD COLUMN IF NOT EXISTS labor_minutes integer;

ALTER TABLE treatments ADD COLUMN IF NOT EXISTS followup_due_at timestamptz;
ALTER TABLE treatments ADD COLUMN IF NOT EXISTS followup_completed_at timestamptz;
ALTER TABLE treatments ADD COLUMN IF NOT EXISTS outcome text;

ALTER TABLE lab_results ADD COLUMN IF NOT EXISTS recipe_id integer REFERENCES nutrient_recipes(id);
ALTER TABLE lab_results ADD COLUMN IF NOT EXISTS source_sample_id text;

UPDATE crop_catalog
SET cycle_days_min = v.cycle_min,
    cycle_days_max = v.cycle_max,
    base_temp_f = v.base_temp_f,
    default_target_dli = v.target_dli,
    default_target_vpd_low = v.vpd_low,
    default_target_vpd_high = v.vpd_high,
    default_ph_low = v.ph_low,
    default_ph_high = v.ph_high,
    default_ec_low = v.ec_low,
    default_ec_high = v.ec_high
FROM (
    VALUES
      ('basil', 30, 45, 50.0, 16.0, 0.8, 1.2, 5.8, 6.5, 1.0, 1.6),
      ('canna', 120, 180, 50.0, 18.0, 0.8, 1.2, 6.0, 6.8, 1.2, 2.0),
      ('cucumbers', 50, 70, 50.0, 22.0, 0.6, 1.1, 5.8, 6.3, 1.7, 2.5),
      ('herbs', 30, 60, 50.0, 14.0, 0.8, 1.2, 5.8, 6.5, 1.0, 1.8),
      ('lettuce', 45, 60, 40.0, 14.0, 0.6, 1.0, 5.8, 6.3, 0.8, 1.4),
      ('peppers', 90, 120, 50.0, 22.0, 0.8, 1.2, 5.8, 6.5, 1.8, 2.8),
      ('strawberries', 75, 120, 40.0, 16.0, 0.6, 1.0, 5.5, 6.5, 1.2, 2.0),
      ('tomatoes', 70, 90, 50.0, 24.0, 0.8, 1.2, 5.8, 6.5, 2.0, 3.5),
      ('orchid', 365, 540, 55.0, 14.0, 0.5, 0.9, 5.5, 6.2, 0.4, 0.9)
) AS v(slug, cycle_min, cycle_max, base_temp_f, target_dli, vpd_low, vpd_high, ph_low, ph_high, ec_low, ec_high)
WHERE crop_catalog.slug = v.slug;

UPDATE crops c
SET count = COALESCE(c.count, 1),
    expected_harvest = COALESCE(c.expected_harvest, c.planted_date + cc.cycle_days_max),
    base_temp_f = COALESCE(c.base_temp_f, cc.base_temp_f, 50.0),
    target_dli = COALESCE(c.target_dli, cc.default_target_dli),
    target_vpd_low = COALESCE(c.target_vpd_low, cc.default_target_vpd_low),
    target_vpd_high = COALESCE(c.target_vpd_high, cc.default_target_vpd_high),
    updated_at = now()
FROM crop_catalog cc
WHERE c.crop_catalog_id = cc.id
  AND c.is_active = true;

CREATE OR REPLACE VIEW v_crop_lifecycle_completeness AS
SELECT
    c.id AS crop_id,
    c.name,
    c.variety,
    c.zone,
    c.position,
    c.stage,
    c.is_active,
    c.count,
    c.expected_harvest,
    c.crop_catalog_id,
    c.target_dli,
    c.target_vpd_low,
    c.target_vpd_high,
    array_remove(ARRAY[
        CASE WHEN c.count IS NULL THEN 'count' END,
        CASE WHEN c.expected_harvest IS NULL THEN 'expected_harvest' END,
        CASE WHEN c.crop_catalog_id IS NULL THEN 'crop_catalog_id' END,
        CASE WHEN c.stage IS NULL THEN 'stage' END,
        CASE WHEN c.target_dli IS NULL THEN 'target_dli' END,
        CASE WHEN c.target_vpd_low IS NULL OR c.target_vpd_high IS NULL THEN 'target_vpd' END
    ], NULL) AS missing_fields,
    cardinality(array_remove(ARRAY[
        CASE WHEN c.count IS NULL THEN 'count' END,
        CASE WHEN c.expected_harvest IS NULL THEN 'expected_harvest' END,
        CASE WHEN c.crop_catalog_id IS NULL THEN 'crop_catalog_id' END,
        CASE WHEN c.stage IS NULL THEN 'stage' END,
        CASE WHEN c.target_dli IS NULL THEN 'target_dli' END,
        CASE WHEN c.target_vpd_low IS NULL OR c.target_vpd_high IS NULL THEN 'target_vpd' END
    ], NULL)) AS missing_count
FROM crops c;

COMMENT ON VIEW v_crop_lifecycle_completeness IS
'Crop rows with lifecycle/outcome fields required for agronomic analysis.';

CREATE OR REPLACE VIEW v_growth_observation_quality AS
SELECT
    (ts AT TIME ZONE 'America/Denver')::date AS date,
    crop_id,
    count(*) AS observations,
    count(*) FILTER (WHERE health_score IS NOT NULL) AS health_scores,
    count(*) FILTER (
        WHERE plant_height_cm IS NOT NULL
           OR leaf_count IS NOT NULL
           OR canopy_cover_pct IS NOT NULL
           OR flowering_count IS NOT NULL
           OR fruit_count IS NOT NULL
           OR root_condition IS NOT NULL
           OR mortality_count IS NOT NULL
           OR stress_tags IS NOT NULL
    ) AS structured_growth_observations,
    count(*) FILTER (WHERE severity IS NOT NULL OR affected_pct IS NOT NULL) AS structured_stress_observations,
    avg(health_score) AS avg_health_score
FROM observations
GROUP BY 1, crop_id
ORDER BY date DESC, crop_id;

COMMENT ON VIEW v_growth_observation_quality IS
'Daily observation structure coverage: health, phenology/growth, and stress evidence.';

CREATE OR REPLACE VIEW v_harvest_story AS
SELECT
    h.id,
    h.ts,
    (h.ts AT TIME ZONE 'America/Denver')::date AS date,
    h.greenhouse_id,
    h.crop_id,
    c.name AS crop_name,
    h.position_id,
    h.zone,
    COALESCE(h.salable_weight_kg, h.weight_kg) AS salable_weight_kg,
    h.cull_weight_kg,
    h.unit_count,
    h.quality_grade,
    h.quality_reason,
    h.destination,
    h.unit_price,
    COALESCE(h.revenue, h.unit_price * h.unit_count) AS revenue,
    ds.dli_final,
    ds.water_used_gal,
    ds.kwh_total,
    CASE WHEN ds.dli_final > 0 THEN COALESCE(h.salable_weight_kg, h.weight_kg) / ds.dli_final END AS kg_per_mol_dli,
    CASE WHEN ds.water_used_gal > 0 THEN COALESCE(h.salable_weight_kg, h.weight_kg) / ds.water_used_gal END AS kg_per_gal,
    CASE WHEN ds.kwh_total > 0 THEN COALESCE(h.salable_weight_kg, h.weight_kg) / ds.kwh_total END AS kg_per_kwh
FROM harvests h
LEFT JOIN crops c ON c.id = h.crop_id
LEFT JOIN daily_summary ds ON ds.date = (h.ts AT TIME ZONE 'America/Denver')::date;

COMMENT ON VIEW v_harvest_story IS
'Harvest outcome evidence normalized by DLI, gallons, and measured kWh when available.';

CREATE OR REPLACE VIEW v_nutrient_lab_status AS
WITH latest_hydro AS (
    SELECT DISTINCT ON (COALESCE(greenhouse_id, 'vallery'))
        COALESCE(greenhouse_id, 'vallery') AS greenhouse_id,
        ts,
        hydro_ph,
        hydro_ec_us_cm,
        hydro_tds_ppm,
        hydro_orp_mv,
        hydro_battery_pct
    FROM climate
    WHERE hydro_ph IS NOT NULL OR hydro_ec_us_cm IS NOT NULL
    ORDER BY COALESCE(greenhouse_id, 'vallery'), ts DESC
),
latest_lab AS (
    SELECT DISTINCT ON (greenhouse_id, sample_type, COALESCE(zone, ''))
        greenhouse_id,
        sample_type,
        zone,
        crop_id,
        sampled_at,
        ph,
        ec_ms_cm,
        recipe_id
    FROM lab_results
    ORDER BY greenhouse_id, sample_type, COALESCE(zone, ''), sampled_at DESC NULLS LAST, ts DESC NULLS LAST
)
SELECT
    h.greenhouse_id,
    h.ts AS hydro_ts,
    h.hydro_ph,
    h.hydro_ec_us_cm,
    h.hydro_tds_ppm,
    h.hydro_orp_mv,
    h.hydro_battery_pct,
    l.sample_type AS latest_lab_sample_type,
    l.zone AS latest_lab_zone,
    l.sampled_at AS latest_lab_sampled_at,
    l.ph AS latest_lab_ph,
    l.ec_ms_cm AS latest_lab_ec_ms_cm,
    nr.name AS recipe_name,
    nr.target_ph_low,
    nr.target_ph_high,
    nr.target_ec,
    CASE
        WHEN h.hydro_ph IS NULL THEN 'missing_hydro_ph'
        WHEN nr.target_ph_low IS NOT NULL AND h.hydro_ph < nr.target_ph_low THEN 'ph_low'
        WHEN nr.target_ph_high IS NOT NULL AND h.hydro_ph > nr.target_ph_high THEN 'ph_high'
        WHEN nr.target_ec IS NOT NULL AND h.hydro_ec_us_cm IS NOT NULL
             AND (h.hydro_ec_us_cm / 1000.0) > nr.target_ec * 1.25 THEN 'ec_high'
        WHEN nr.target_ec IS NOT NULL AND h.hydro_ec_us_cm IS NOT NULL
             AND (h.hydro_ec_us_cm / 1000.0) < nr.target_ec * 0.75 THEN 'ec_low'
        ELSE 'ok'
    END AS status
FROM latest_hydro h
LEFT JOIN latest_lab l ON l.greenhouse_id = h.greenhouse_id
LEFT JOIN nutrient_recipes nr ON nr.id = l.recipe_id OR (nr.is_active = true AND nr.crop_id = l.crop_id);

COMMENT ON VIEW v_nutrient_lab_status IS
'Latest hydro chemistry and lab evidence compared with the linked or active nutrient recipe.';

CREATE OR REPLACE VIEW v_succession_plan_readiness AS
SELECT
    p.greenhouse_id,
    z.slug AS zone,
    p.id AS position_id,
    p.label AS position,
    c.id AS active_crop_id,
    c.name AS active_crop_name,
    c.expected_harvest,
    sp.id AS succession_plan_id,
    sp.crop AS next_crop,
    sp.planned_sow,
    sp.planned_harvest,
    CASE
        WHEN c.id IS NULL AND sp.id IS NULL THEN 'empty_unplanned'
        WHEN c.id IS NOT NULL AND c.expected_harvest IS NULL THEN 'active_crop_missing_harvest'
        WHEN c.id IS NOT NULL AND sp.id IS NULL THEN 'active_no_successor'
        ELSE 'planned'
    END AS readiness_status
FROM positions p
JOIN shelves sh ON sh.id = p.shelf_id
JOIN zones z ON z.id = sh.zone_id
LEFT JOIN crops c ON c.position_id = p.id AND c.is_active = true
LEFT JOIN succession_plan sp
  ON sp.position = p.label
 AND sp.zone = z.slug
 AND sp.is_active = true
WHERE p.is_active = true;

COMMENT ON VIEW v_succession_plan_readiness IS
'Every active position with current crop and next planned crop readiness.';

CREATE TABLE IF NOT EXISTS instrumentation_requirements (
    requirement_id text PRIMARY KEY,
    category text NOT NULL,
    metric text NOT NULL,
    target_table text,
    target_column text,
    current_status text NOT NULL DEFAULT 'needed',
    blocks_story text NOT NULL,
    recommended_source text,
    priority integer NOT NULL DEFAULT 2,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO instrumentation_requirements (
    requirement_id, category, metric, target_table, target_column, current_status,
    blocks_story, recommended_source, priority
) VALUES
    ('par_ppfd', 'light', 'calibrated PAR/PPFD and PAR DLI', 'climate', 'ppfd', 'needed',
     'Calibrated DLI, yield per mol, light-use efficiency', 'Apogee SQ-class PAR sensor or equivalent', 1),
    ('leaf_wetness_temp', 'disease', 'leaf wetness plus leaf temperature', 'climate', 'leaf_wetness_north', 'needed',
     'Canopy condensation and disease-risk proof', 'Leaf wetness + IR leaf temperature sensors', 1),
    ('actuator_feedback', 'control', 'independent actuator state/current feedback', 'equipment_state', NULL, 'needed',
     'Relay stuck proof beyond commanded state', 'Current transformers or relay feedback contacts', 1),
    ('zone_flow_meters', 'water', 'per-zone flow and pressure instrumentation', 'irrigation_log', 'volume_gal', 'needed',
     'Water attribution by mister/drip/zone and leach fraction', 'Zone flow meters, reservoir level, pressure sensors', 1),
    ('energy_submetering', 'energy', 'load-specific electrical and heat energy', 'energy', 'watts_heat', 'partial',
     'Cost per heat/fog/fan/light action and measured-vs-estimated calibration', 'Submeter heat/fans/fog/lights plus gas telemetry', 2)
ON CONFLICT (requirement_id) DO UPDATE
SET category = EXCLUDED.category,
    metric = EXCLUDED.metric,
    target_table = EXCLUDED.target_table,
    target_column = EXCLUDED.target_column,
    current_status = EXCLUDED.current_status,
    blocks_story = EXCLUDED.blocks_story,
    recommended_source = EXCLUDED.recommended_source,
    priority = EXCLUDED.priority,
    updated_at = now();

CREATE OR REPLACE VIEW v_instrumentation_readiness AS
SELECT
    requirement_id,
    category,
    metric,
    current_status,
    blocks_story,
    recommended_source,
    priority,
    CASE
        WHEN current_status IN ('installed', 'complete') THEN 'ok'
        WHEN current_status = 'partial' THEN 'warn'
        ELSE 'blocked'
    END AS readiness_status
FROM instrumentation_requirements
ORDER BY priority, category, requirement_id;

COMMENT ON VIEW v_instrumentation_readiness IS
'Hardware/operator instrumentation requirements that block stronger data stories.';

-- ---------------------------------------------------------------------------
-- 5. Story marts and self-checking generated daily plan archive
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS daily_plan_archive_audit (
    date date PRIMARY KEY,
    generated_at timestamptz NOT NULL DEFAULT now(),
    page_path text NOT NULL,
    generated_plan_count integer NOT NULL DEFAULT 0,
    db_plan_count integer NOT NULL DEFAULT 0,
    generated_cost_total double precision,
    db_cost_total double precision,
    generated_water_gal double precision,
    db_water_gal double precision,
    content_checksum text,
    stale boolean NOT NULL DEFAULT false,
    notes text
);

COMMENT ON TABLE daily_plan_archive_audit IS
'Self-check rows written by generate-daily-plan.py: generated page counts and DB cost/water checksums.';

CREATE OR REPLACE VIEW v_daily_plan_archive_self_check AS
WITH db_counts AS (
    SELECT
        substring(plan_id from 'iris-(\d{8})')::date AS date,
        count(*) AS db_plan_count
    FROM plan_journal
    WHERE plan_id NOT LIKE 'iris-reactive%'
      AND plan_id NOT LIKE 'iris-fix%'
      AND substring(plan_id from 'iris-(\d{8})') IS NOT NULL
    GROUP BY 1
)
SELECT
    ds.date,
    a.generated_at,
    a.page_path,
    COALESCE(a.generated_plan_count, 0) AS generated_plan_count,
    COALESCE(a.db_plan_count, dbc.db_plan_count, 0) AS db_plan_count,
    a.generated_cost_total,
    ds.cost_total AS db_cost_total,
    a.generated_water_gal,
    ds.water_used_gal AS db_water_gal,
    a.content_checksum,
    CASE
        WHEN a.date IS NULL THEN true
        WHEN a.generated_plan_count <> COALESCE(dbc.db_plan_count, 0) THEN true
        WHEN abs(COALESCE(a.generated_cost_total, ds.cost_total, 0) - COALESCE(ds.cost_total, 0)) > 0.01 THEN true
        WHEN abs(COALESCE(a.generated_water_gal, ds.water_used_gal, 0) - COALESCE(ds.water_used_gal, 0)) > 0.1 THEN true
        WHEN ds.captured_at IS NOT NULL AND a.generated_at < ds.captured_at THEN true
        ELSE false
    END AS stale,
    CASE
        WHEN a.date IS NULL THEN 'missing_archive_audit'
        WHEN a.generated_plan_count <> COALESCE(dbc.db_plan_count, 0) THEN 'plan_count_mismatch'
        WHEN abs(COALESCE(a.generated_cost_total, ds.cost_total, 0) - COALESCE(ds.cost_total, 0)) > 0.01 THEN 'cost_mismatch'
        WHEN abs(COALESCE(a.generated_water_gal, ds.water_used_gal, 0) - COALESCE(ds.water_used_gal, 0)) > 0.1 THEN 'water_mismatch'
        WHEN ds.captured_at IS NOT NULL AND a.generated_at < ds.captured_at THEN 'archive_older_than_summary'
        ELSE 'ok'
    END AS status
FROM daily_summary ds
LEFT JOIN daily_plan_archive_audit a USING (date)
LEFT JOIN db_counts dbc USING (date)
WHERE ds.date >= DATE '2026-03-24';

COMMENT ON VIEW v_daily_plan_archive_self_check IS
'Generated daily plan page self-check against daily_summary and plan_journal.';

CREATE OR REPLACE VIEW v_forecast_plan_outcome_mart AS
WITH plan_days AS (
    SELECT
        pj.plan_id,
        (pj.created_at AT TIME ZONE 'America/Denver')::date AS date,
        pj.created_at,
        pj.hypothesis,
        pj.experiment,
        pj.expected_outcome,
        pj.actual_outcome,
        pj.outcome_score,
        pj.validated_at,
        pj.planner_instance,
        pj.trigger_id
    FROM plan_journal pj
    WHERE pj.plan_id NOT LIKE 'iris-reactive%'
),
forecast_day AS (
    SELECT
        date,
        avg(mae) FILTER (WHERE param = 'temp_f') AS temp_mae_f,
        avg(mae) FILTER (WHERE param = 'vpd_kpa') AS vpd_mae_kpa,
        avg(mae) FILTER (WHERE param = 'solar_w_m2') AS solar_mae_w
    FROM v_forecast_accuracy_lead_buckets
    GROUP BY date
),
plan_posture AS (
    SELECT
        plan_id,
        jsonb_object_agg(parameter, avg_value) AS avg_tunables
    FROM v_plan_tactical_outcome_daily
    GROUP BY plan_id
)
SELECT
    pd.plan_id,
    pd.date,
    pd.created_at,
    pd.planner_instance,
    pd.trigger_id,
    fd.temp_mae_f,
    fd.vpd_mae_kpa,
    fd.solar_mae_w,
    pp.avg_tunables,
    ds.compliance_pct,
    ds.temp_compliance_pct,
    ds.vpd_compliance_pct,
    ds.stress_hours_heat,
    ds.stress_hours_vpd_high,
    ds.stress_hours_cold,
    ds.stress_hours_vpd_low,
    ds.water_used_gal,
    ds.mister_water_gal,
    COALESCE(ds.kwh_total, ds.kwh_estimated) AS kwh,
    ds.therms_estimated,
    ds.cost_total,
    pd.hypothesis,
    pd.experiment,
    pd.expected_outcome,
    pd.actual_outcome,
    pd.outcome_score,
    pd.validated_at
FROM plan_days pd
LEFT JOIN daily_summary ds ON ds.date = pd.date
LEFT JOIN forecast_day fd ON fd.date = pd.date
LEFT JOIN plan_posture pp ON pp.plan_id = pd.plan_id;

COMMENT ON VIEW v_forecast_plan_outcome_mart IS
'Forecast regime, Iris tactical posture, measured climate/resource outcome, and plan evaluation in one story mart.';

CREATE OR REPLACE VIEW v_grower_economics_story AS
WITH harvest_daily AS (
    SELECT
        (ts AT TIME ZONE 'America/Denver')::date AS date,
        sum(COALESCE(salable_weight_kg, weight_kg, 0)) AS salable_kg,
        sum(COALESCE(cull_weight_kg, 0)) AS cull_kg,
        sum(COALESCE(revenue, unit_price * unit_count, 0)) AS revenue
    FROM harvests
    GROUP BY 1
)
SELECT
    ds.date,
    hd.salable_kg,
    hd.cull_kg,
    hd.revenue,
    ds.dli_final,
    ds.water_used_gal,
    COALESCE(ds.kwh_total, ds.kwh_estimated) AS kwh,
    ds.therms_estimated,
    ds.cost_total,
    ds.stress_hours_heat + ds.stress_hours_vpd_high + ds.stress_hours_cold + ds.stress_hours_vpd_low
        AS stress_hours,
    CASE WHEN ds.dli_final > 0 THEN hd.salable_kg / ds.dli_final END AS kg_per_mol_dli,
    CASE WHEN ds.water_used_gal > 0 THEN hd.salable_kg / ds.water_used_gal END AS kg_per_gal,
    CASE WHEN COALESCE(ds.kwh_total, ds.kwh_estimated) > 0 THEN hd.salable_kg / COALESCE(ds.kwh_total, ds.kwh_estimated) END AS kg_per_kwh,
    CASE WHEN ds.cost_total > 0 THEN hd.revenue / ds.cost_total END AS revenue_per_cost_dollar
FROM daily_summary ds
LEFT JOIN harvest_daily hd USING (date)
WHERE ds.date IS NOT NULL
ORDER BY ds.date DESC;

COMMENT ON VIEW v_grower_economics_story IS
'Yield, quality, revenue, DLI, water, energy, cost, and stress-hour economics by local day.';

-- Extend the trust ledger after the repair/backfill surfaces exist.
CREATE OR REPLACE VIEW v_data_trust_ledger AS
SELECT 'climate_freshness' AS check_name,
       CASE WHEN age_s <= 300 THEN 'ok' ELSE 'fail' END AS status,
       age_s::numeric AS metric_value,
       300::numeric AS threshold_value,
       source || ' age seconds' AS details
FROM v_data_pipeline_health
WHERE source = 'climate'
UNION ALL
SELECT 'forecast_freshness',
       CASE WHEN age_s <= 21600 THEN 'ok' ELSE 'fail' END,
       age_s::numeric,
       21600::numeric,
       'weather_forecast fetched_at age seconds'
FROM v_data_pipeline_health
WHERE source = 'forecast'
UNION ALL
SELECT 'required_sensor_coverage',
       CASE WHEN count(*) FILTER (WHERE coverage_status <> 'ok') = 0 THEN 'ok' ELSE 'warn' END,
       count(*) FILTER (WHERE coverage_status <> 'ok')::numeric,
       0::numeric,
       'required configured sensors not ok'
FROM v_required_sensor_coverage
UNION ALL
SELECT 'alert_lifecycle_mismatch',
       CASE WHEN count(*) = 0 THEN 'ok' ELSE 'warn' END,
       count(*)::numeric,
       0::numeric,
       'alerts with resolved_at set but disposition not resolved'
FROM alert_log
WHERE resolved_at IS NOT NULL
  AND disposition <> 'resolved'
UNION ALL
SELECT 'open_critical_or_high_alerts',
       CASE WHEN count(*) = 0 THEN 'ok' ELSE 'fail' END,
       count(*)::numeric,
       0::numeric,
       'open critical/high alerts'
FROM alert_log
WHERE disposition = 'open'
  AND severity IN ('critical', 'high')
UNION ALL
SELECT 'data_gap_hours_24h',
       CASE WHEN COALESCE(sum(duration_s), 0) = 0 THEN 'ok' ELSE 'warn' END,
       round((COALESCE(sum(duration_s), 0) / 3600.0)::numeric, 2),
       0::numeric,
       'telemetry gap hours ending in the last 24h'
FROM data_gaps
WHERE end_ts > now() - interval '24 hours'
UNION ALL
SELECT 'water_accounting_14d',
       CASE WHEN count(*) FILTER (WHERE quality_flag <> 'ok') = 0 THEN 'ok' ELSE 'warn' END,
       count(*) FILTER (WHERE quality_flag <> 'ok')::numeric,
       0::numeric,
       'water accountability rows flagged in last 14 local days'
FROM v_water_accountability
WHERE date >= (now() AT TIME ZONE 'America/Denver')::date - 14
UNION ALL
SELECT 'irrigation_logging_14d',
       CASE WHEN expected.starts_14d = 0 OR logged.logs_14d >= expected.starts_14d THEN 'ok' ELSE 'warn' END,
       GREATEST(expected.starts_14d - logged.logs_14d, 0)::numeric,
       0::numeric,
       'drip starts in equipment_state without irrigation_log rows in last 14 days'
FROM (
    WITH ordered AS (
        SELECT
            ts,
            equipment,
            state,
            lag(state) OVER (PARTITION BY equipment ORDER BY ts) AS prev_state
        FROM equipment_state
        WHERE equipment IN ('drip_wall', 'drip_center')
          AND ts >= now() - interval '14 days'
    )
    SELECT count(*) AS starts_14d
    FROM ordered
    WHERE state = true
      AND COALESCE(prev_state, false) = false
) expected
CROSS JOIN (
    SELECT count(*) AS logs_14d
    FROM irrigation_log
    WHERE actual_start >= now() - interval '14 days'
) logged
UNION ALL
SELECT 'energy_reconciliation_14d',
       CASE WHEN count(*) FILTER (WHERE quality_flag <> 'ok') = 0 THEN 'ok' ELSE 'warn' END,
       count(*) FILTER (WHERE quality_flag <> 'ok')::numeric,
       0::numeric,
       'estimated vs measured energy mismatches in last 14 local days'
FROM v_energy_estimate_reconciliation
WHERE date >= (now() AT TIME ZONE 'America/Denver')::date - 14
UNION ALL
SELECT 'forecast_action_outcomes_7d',
       CASE WHEN count(*) FILTER (WHERE outcome IS NULL OR outcome = 'pending') = 0 THEN 'ok' ELSE 'warn' END,
       count(*) FILTER (WHERE outcome IS NULL OR outcome = 'pending')::numeric,
       0::numeric,
       'forecast action rows past follow-up window without evaluated outcome in last 7 days'
FROM forecast_action_log
WHERE triggered_at > now() - interval '7 days'
  AND triggered_at <= now() - interval '6 hours'
UNION ALL
SELECT 'crop_lifecycle_completeness',
       CASE WHEN sum(missing_count) FILTER (WHERE is_active) = 0 THEN 'ok' ELSE 'warn' END,
       COALESCE(sum(missing_count) FILTER (WHERE is_active), 0)::numeric,
       0::numeric,
       'missing active crop lifecycle fields'
FROM v_crop_lifecycle_completeness
UNION ALL
SELECT 'daily_plan_archive_self_check',
       CASE WHEN count(*) FILTER (WHERE stale) = 0 THEN 'ok' ELSE 'warn' END,
       count(*) FILTER (WHERE stale)::numeric,
       0::numeric,
       'generated daily plan pages stale or unaudited'
FROM v_daily_plan_archive_self_check
WHERE date >= (now() AT TIME ZONE 'America/Denver')::date - 14
UNION ALL
SELECT 'instrumentation_readiness',
       CASE WHEN count(*) FILTER (WHERE readiness_status = 'blocked') = 0 THEN 'ok' ELSE 'warn' END,
       count(*) FILTER (WHERE readiness_status = 'blocked')::numeric,
       0::numeric,
       'hardware/operator instrumentation blockers'
FROM v_instrumentation_readiness;

COMMENT ON VIEW v_data_trust_ledger IS
'Owner-facing trust checks spanning freshness, coverage, gaps, water, energy, forecasts, crop completeness, generated archives, and instrumentation readiness.';
