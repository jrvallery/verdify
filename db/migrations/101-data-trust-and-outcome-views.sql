-- Migration 101: data trust + outcome observability repair
--
-- Read-only surfaces for the 2026-05-01 data audit:
--   - fix duration/day-boundary bugs in condensation and water views
--   - make forecast accuracy use forecasts known before the observed hour
--   - keep Iris planning context from seeing inactive future waypoints
--   - expose active-band compliance and trust ledgers for story quality

-- Condensation risk: local greenhouse day and actual sample durations.
CREATE OR REPLACE VIEW v_dew_point_risk AS
WITH raw AS (
    SELECT
        ts,
        (ts AT TIME ZONE 'America/Denver')::date AS local_date,
        (temp_avg - dew_point) AS margin_f
    FROM climate
    WHERE temp_avg IS NOT NULL
      AND dew_point IS NOT NULL
),
samples AS (
    SELECT
        ts,
        local_date,
        margin_f,
        lead(ts) OVER (PARTITION BY local_date ORDER BY ts) AS next_ts
    FROM raw
),
durations AS (
    SELECT
        local_date AS date,
        margin_f,
        LEAST(
            GREATEST(
                EXTRACT(EPOCH FROM (
                    COALESCE(
                        next_ts,
                        LEAST(now(), ((local_date + 1)::timestamp AT TIME ZONE 'America/Denver'))
                    ) - ts
                )),
                0
            ),
            300
        ) / 3600.0 AS hours_observed
    FROM samples
)
SELECT
    date,
    round(min(margin_f)::numeric, 1) AS min_margin_f,
    round(avg(margin_f)::numeric, 1) AS avg_margin_f,
    round(COALESCE(sum(hours_observed) FILTER (WHERE margin_f < 5), 0)::numeric, 1) AS risk_hours,
    round(COALESCE(sum(hours_observed) FILTER (WHERE margin_f < 3), 0)::numeric, 1) AS critical_hours
FROM durations
GROUP BY date
ORDER BY date;

COMMENT ON VIEW v_dew_point_risk IS
'Indoor condensation risk by America/Denver day. Durations use observed sample intervals capped at 5 minutes, not a fixed sample cadence.';

-- Water use: local greenhouse day and positive meter deltas. Negative deltas
-- are treated as counter resets; zero readings are ignored as phantom samples.
CREATE OR REPLACE VIEW v_water_daily AS
WITH samples AS (
    SELECT
        ((ts AT TIME ZONE 'America/Denver')::date::timestamp AT TIME ZONE 'America/Denver') AS day,
        ts,
        water_total_gal,
        lag(water_total_gal) OVER (
            PARTITION BY (ts AT TIME ZONE 'America/Denver')::date
            ORDER BY ts
        ) AS prev_gal
    FROM climate
    WHERE water_total_gal IS NOT NULL
      AND water_total_gal > 0
),
deltas AS (
    SELECT
        day,
        CASE
            WHEN prev_gal IS NULL THEN 0::double precision
            WHEN water_total_gal < prev_gal THEN 0::double precision
            ELSE water_total_gal - prev_gal
        END AS delta_gal
    FROM samples
)
SELECT
    day,
    round(COALESCE(sum(delta_gal), 0)::numeric, 3)::double precision AS used_gal
FROM deltas
GROUP BY day
ORDER BY day DESC;

COMMENT ON VIEW v_water_daily IS
'Daily water usage from positive cumulative-meter deltas by America/Denver day. Ignores phantom zero readings and reset deltas.';

CREATE OR REPLACE VIEW v_water_accountability AS
SELECT
    date,
    total_gal,
    mister_gal,
    drip_gal,
    unaccounted_gal,
    gal_per_vpd_stress_hour,
    CASE
        WHEN total_gal IS NULL THEN 'missing_total'
        WHEN total_gal < 0 THEN 'negative_total'
        WHEN mister_gal > total_gal + 5 THEN 'mister_exceeds_total'
        WHEN unaccounted_gal < -5 THEN 'negative_unaccounted'
        WHEN unaccounted_gal > GREATEST(25, total_gal * 0.25) THEN 'high_unaccounted'
        ELSE 'ok'
    END AS quality_flag
FROM v_water_budget;

COMMENT ON VIEW v_water_accountability IS
'Water decomposition plus quality flag. Flags accounting rows that should not be used as proof without investigation.';

-- Forecast accuracy: choose the latest forecast that existed before the
-- observed forecast hour. This avoids backcast accuracy from later fetches.
CREATE OR REPLACE VIEW v_forecast_accuracy AS
WITH forecast_deduped AS (
    SELECT DISTINCT ON (f.ts)
        f.ts,
        f.fetched_at,
        f.temp_f,
        f.vpd_kpa,
        f.solar_w_m2
    FROM weather_forecast f
    WHERE f.ts < now()
      AND f.fetched_at <= f.ts
    ORDER BY f.ts, f.fetched_at DESC
)
SELECT
    f.ts AS forecast_hour,
    f.fetched_at,
    round(EXTRACT(epoch FROM (f.ts - f.fetched_at)) / 3600.0, 1) AS lead_hours,
    f.temp_f AS forecast_temp,
    m.outdoor_temp_f AS actual_temp,
    round((f.temp_f - m.outdoor_temp_f)::numeric, 1) AS temp_error_f,
    f.vpd_kpa AS forecast_vpd,
    m.vpd_avg AS actual_vpd,
    round((f.vpd_kpa - m.vpd_avg)::numeric, 2) AS vpd_error_kpa,
    f.solar_w_m2 AS forecast_solar,
    m.solar_w_m2 AS actual_solar,
    round((f.solar_w_m2 - m.solar_w_m2)::numeric, 1) AS solar_error_w
FROM forecast_deduped f
JOIN v_climate_merged m
  ON time_bucket('1 hour', m.bucket) = f.ts;

COMMENT ON VIEW v_forecast_accuracy IS
'Forecast vs observed comparison using the latest forecast fetched before the observed hour. lead_hours is non-negative planning lead time.';

CREATE OR REPLACE VIEW v_forecast_accuracy_daily AS
WITH forecast_deduped AS (
    SELECT DISTINCT ON (f.ts)
        f.ts,
        f.fetched_at,
        f.temp_f,
        f.rh_pct,
        f.cloud_cover_pct
    FROM weather_forecast f
    WHERE f.ts >= now() - interval '14 days'
      AND f.ts <= now()
      AND f.fetched_at <= f.ts
    ORDER BY f.ts, f.fetched_at DESC
),
forecast_daily AS (
    SELECT
        (ts AT TIME ZONE 'America/Denver')::date AS date,
        avg(temp_f) AS fc_temp_avg,
        avg(rh_pct) AS fc_rh_avg,
        avg(cloud_cover_pct) AS fc_cloud_avg,
        avg(EXTRACT(epoch FROM (ts - fetched_at)) / 3600.0) AS horizon_hours
    FROM forecast_deduped
    GROUP BY (ts AT TIME ZONE 'America/Denver')::date
),
observed_daily AS (
    SELECT
        (ts AT TIME ZONE 'America/Denver')::date AS date,
        avg(outdoor_temp_f) AS obs_temp_avg,
        avg(outdoor_rh_pct) AS obs_rh_avg
    FROM climate
    WHERE ts >= now() - interval '14 days'
      AND ts <= now()
    GROUP BY (ts AT TIME ZONE 'America/Denver')::date
)
SELECT
    f.date,
    p.param,
    CASE p.param
        WHEN 'temp_f' THEN f.fc_temp_avg
        WHEN 'rh_pct' THEN f.fc_rh_avg
        WHEN 'cloud_cover_pct' THEN f.fc_cloud_avg
    END AS forecast_avg,
    CASE p.param
        WHEN 'temp_f' THEN o.obs_temp_avg
        WHEN 'rh_pct' THEN o.obs_rh_avg
        WHEN 'cloud_cover_pct' THEN NULL::double precision
    END AS observed_avg,
    CASE p.param
        WHEN 'temp_f' THEN f.fc_temp_avg - o.obs_temp_avg
        WHEN 'rh_pct' THEN f.fc_rh_avg - o.obs_rh_avg
        WHEN 'cloud_cover_pct' THEN NULL::double precision
    END AS bias,
    CASE p.param
        WHEN 'temp_f' THEN abs(f.fc_temp_avg - o.obs_temp_avg)
        WHEN 'rh_pct' THEN abs(f.fc_rh_avg - o.obs_rh_avg)
        WHEN 'cloud_cover_pct' THEN NULL::double precision
    END AS abs_error,
    round(f.horizon_hours, 1) AS horizon_hours
FROM forecast_daily f
JOIN observed_daily o USING (date)
CROSS JOIN (VALUES ('temp_f'), ('rh_pct'), ('cloud_cover_pct')) AS p(param)
ORDER BY f.date DESC, p.param;

COMMENT ON VIEW v_forecast_accuracy_daily IS
'Daily forecast-vs-observed bias/MAE using only forecasts fetched before the observed hour.';

CREATE OR REPLACE VIEW v_forecast_accuracy_lead_buckets AS
WITH paired AS (
    SELECT
        (f.ts AT TIME ZONE 'America/Denver')::date AS date,
        CASE
            WHEN EXTRACT(epoch FROM (f.ts - f.fetched_at)) / 3600.0 < 6 THEN '00-06h'
            WHEN EXTRACT(epoch FROM (f.ts - f.fetched_at)) / 3600.0 < 24 THEN '06-24h'
            WHEN EXTRACT(epoch FROM (f.ts - f.fetched_at)) / 3600.0 < 48 THEN '24-48h'
            ELSE '48h+'
        END AS lead_bucket,
        f.temp_f - m.outdoor_temp_f AS temp_error_f,
        f.vpd_kpa - m.vpd_avg AS vpd_error_kpa,
        f.solar_w_m2 - m.solar_w_m2 AS solar_error_w
    FROM weather_forecast f
    JOIN v_climate_merged m
      ON time_bucket('1 hour', m.bucket) = f.ts
    WHERE f.ts < now()
      AND f.ts >= now() - interval '30 days'
      AND f.fetched_at <= f.ts
)
SELECT date, lead_bucket, 'temp_f' AS param,
       count(temp_error_f) AS samples,
       round(avg(temp_error_f)::numeric, 2) AS bias,
       round(avg(abs(temp_error_f))::numeric, 2) AS mae
FROM paired
WHERE temp_error_f IS NOT NULL
GROUP BY date, lead_bucket
UNION ALL
SELECT date, lead_bucket, 'vpd_kpa' AS param,
       count(vpd_error_kpa) AS samples,
       round(avg(vpd_error_kpa)::numeric, 3) AS bias,
       round(avg(abs(vpd_error_kpa))::numeric, 3) AS mae
FROM paired
WHERE vpd_error_kpa IS NOT NULL
GROUP BY date, lead_bucket
UNION ALL
SELECT date, lead_bucket, 'solar_w_m2' AS param,
       count(solar_error_w) AS samples,
       round(avg(solar_error_w)::numeric, 1) AS bias,
       round(avg(abs(solar_error_w))::numeric, 1) AS mae
FROM paired
WHERE solar_error_w IS NOT NULL
GROUP BY date, lead_bucket;

COMMENT ON VIEW v_forecast_accuracy_lead_buckets IS
'Forecast accuracy by local day and fixed lead-time bucket. Uses all forecasts fetched before each observed hour.';

-- Iris context must not include inactive future rows from superseded plans.
CREATE OR REPLACE VIEW v_iris_planning_context AS
SELECT
    now() AS query_ts,
    (
        SELECT json_build_object(
            'temp_avg', round(avg(temp_avg)::numeric, 1),
            'vpd_avg', round(avg(vpd_avg)::numeric, 2),
            'rh_avg', round(avg(rh_avg)::numeric, 1),
            'outdoor_temp_f', round(avg(outdoor_temp_f)::numeric, 1),
            'dli_today', round(max(dli_today)::numeric, 2),
            'co2_ppm', round(avg(co2_ppm)::numeric, 0)
        )
        FROM climate
        WHERE ts >= now() - interval '1 hour'
          AND temp_avg IS NOT NULL
    ) AS current_conditions,
    (
        SELECT json_build_object(
            'north', round(avg(temp_north)::numeric, 1),
            'south', round(avg(temp_south)::numeric, 1),
            'east', round(avg(temp_east)::numeric, 1),
            'west', round(avg(temp_west)::numeric, 1)
        )
        FROM climate
        WHERE ts >= now() - interval '1 hour'
          AND temp_avg IS NOT NULL
    ) AS zone_context,
    (
        SELECT json_build_object(
            'date', date,
            'cost_total', cost_total,
            'dli_final', dli_final,
            'stress_hours_vpd_high', stress_hours_vpd_high,
            'water_used_gal', water_used_gal
        )
        FROM daily_summary
        ORDER BY date DESC
        LIMIT 1
    ) AS yesterday_summary,
    (
        SELECT json_build_object('predicted_dli', predicted_dli, 'gl_hours_needed', gl_hours_needed)
        FROM fn_forecast_dli(CURRENT_DATE + 1)
    ) AS dli_forecast,
    (
        SELECT json_object_agg(parameter, value)
        FROM (
            SELECT DISTINCT ON (parameter) parameter, value
            FROM setpoint_changes
            ORDER BY parameter, ts DESC
        ) sub
    ) AS current_setpoints,
    (
        SELECT json_agg(row_to_json(sub.*) ORDER BY ts)
        FROM (
            SELECT ts, parameter, value, reason
            FROM setpoint_plan
            WHERE ts > now()
              AND is_active = true
              AND parameter <> 'plan_metadata'
            ORDER BY ts
        ) sub
    ) AS active_plan,
    (
        SELECT json_build_object(
            'composite_score', fn_system_health(),
            'components', (
                SELECT json_agg(json_build_object('component', component, 'score', score_pct))
                FROM v_system_health_score
            )
        )
    ) AS system_health,
    (SELECT json_build_object('electric_per_kwh', 0.111, 'gas_per_therm', 1.20, 'water_per_gal', 0.00484)) AS cost_rates;

COMMENT ON VIEW v_iris_planning_context IS
'Single-query planning context for Iris. v4 filters active_plan to is_active=true so superseded future rows are invisible.';

-- Active-band compliance. The legacy name is kept for dashboard compatibility,
-- but it now compares readings to the live temp/VPD band timeline. RH has no
-- authoritative active band, so rh columns are NULL.
CREATE OR REPLACE VIEW v_setpoint_compliance AS
WITH zone_readings AS (
    SELECT ts, 'south'::text AS zone, temp_south AS actual_temp, rh_south AS actual_rh, vpd_south AS actual_vpd
    FROM climate WHERE temp_south IS NOT NULL
    UNION ALL
    SELECT ts, 'north', temp_north, rh_north, vpd_north
    FROM climate WHERE temp_north IS NOT NULL
    UNION ALL
    SELECT ts, 'east', temp_east, rh_east, vpd_east
    FROM climate WHERE temp_east IS NOT NULL
    UNION ALL
    SELECT ts, 'west', temp_west, rh_west, vpd_west
    FROM climate WHERE temp_west IS NOT NULL
    UNION ALL
    SELECT ts, 'greenhouse', temp_avg, rh_avg, vpd_avg
    FROM climate WHERE temp_avg IS NOT NULL
),
banded AS (
    SELECT
        zr.*,
        tl.value AS temp_low,
        th.value AS temp_high,
        vl.value AS vpd_low,
        vh.value AS vpd_high
    FROM zone_readings zr
    LEFT JOIN LATERAL (
        SELECT value FROM setpoint_changes
        WHERE parameter = 'temp_low' AND ts <= zr.ts AND value BETWEEN 30 AND 120
        ORDER BY ts DESC LIMIT 1
    ) tl ON true
    LEFT JOIN LATERAL (
        SELECT value FROM setpoint_changes
        WHERE parameter = 'temp_high' AND ts <= zr.ts AND value BETWEEN 30 AND 120
        ORDER BY ts DESC LIMIT 1
    ) th ON true
    LEFT JOIN LATERAL (
        SELECT value FROM setpoint_changes
        WHERE parameter = 'vpd_low' AND ts <= zr.ts AND value BETWEEN 0.1 AND 5.0
        ORDER BY ts DESC LIMIT 1
    ) vl ON true
    LEFT JOIN LATERAL (
        SELECT value FROM setpoint_changes
        WHERE parameter = 'vpd_high' AND ts <= zr.ts AND value BETWEEN 0.1 AND 5.0
        ORDER BY ts DESC LIMIT 1
    ) vh ON true
)
SELECT
    ts,
    zone,
    round(actual_temp::numeric, 1) AS actual_temp,
    round(((temp_low + temp_high) / 2.0)::numeric, 1) AS target_temp,
    actual_temp BETWEEN temp_low AND temp_high AS temp_in_range,
    round(actual_rh::numeric, 1) AS actual_rh,
    NULL::numeric AS target_rh,
    NULL::boolean AS rh_in_range,
    round(actual_vpd::numeric, 2) AS actual_vpd,
    round(((vpd_low + vpd_high) / 2.0)::numeric, 2) AS target_vpd,
    actual_vpd BETWEEN vpd_low AND vpd_high AS vpd_in_range,
    (actual_temp BETWEEN temp_low AND temp_high)
      AND (actual_vpd BETWEEN vpd_low AND vpd_high) AS overall_compliant
FROM banded
WHERE temp_low IS NOT NULL
  AND temp_high IS NOT NULL
  AND vpd_low IS NOT NULL
  AND vpd_high IS NOT NULL;

COMMENT ON VIEW v_setpoint_compliance IS
'Climate readings vs active temp/VPD band timeline from setpoint_changes. RH is NULL because no active RH band exists.';

CREATE OR REPLACE FUNCTION fn_compliance_pct(lookback interval)
RETURNS TABLE(zone text, temp_pct numeric, rh_pct numeric, vpd_pct numeric, overall_pct numeric)
LANGUAGE sql STABLE AS $$
  SELECT
    v.zone,
    ROUND(100.0 * COUNT(*) FILTER (WHERE temp_in_range) / NULLIF(COUNT(*), 0), 1) AS temp_pct,
    CASE
      WHEN COUNT(*) FILTER (WHERE rh_in_range IS NOT NULL) > 0 THEN
        ROUND(100.0 * COUNT(*) FILTER (WHERE rh_in_range) / NULLIF(COUNT(*) FILTER (WHERE rh_in_range IS NOT NULL), 0), 1)
      ELSE NULL
    END AS rh_pct,
    ROUND(100.0 * COUNT(*) FILTER (WHERE vpd_in_range) / NULLIF(COUNT(*), 0), 1) AS vpd_pct,
    ROUND(100.0 * COUNT(*) FILTER (WHERE overall_compliant) / NULLIF(COUNT(*), 0), 1) AS overall_pct
  FROM v_setpoint_compliance v
  WHERE v.ts > now() - lookback
  GROUP BY v.zone
  ORDER BY v.zone;
$$;

COMMENT ON FUNCTION fn_compliance_pct(interval) IS
'Returns active-band temp/VPD compliance percentage per zone over the given interval. RH is NULL until an active RH band exists.';

-- Real 6-hour soil trend. The old definition used LIMIT 6, which was about
-- six minutes at the current sampling cadence.
CREATE OR REPLACE VIEW v_soil_status AS
WITH latest AS (
    SELECT
        ts,
        soil_moisture_south_1,
        soil_temp_south_1,
        soil_ec_south_1,
        soil_moisture_south_2,
        soil_temp_south_2,
        soil_moisture_west,
        soil_temp_west
    FROM climate
    WHERE soil_moisture_south_1 IS NOT NULL
       OR soil_moisture_west IS NOT NULL
    ORDER BY ts DESC
    LIMIT 1
),
trend AS (
    SELECT
        (array_agg(soil_moisture_south_1 ORDER BY ts DESC) FILTER (WHERE soil_moisture_south_1 IS NOT NULL))[1] AS last_s1,
        (array_agg(soil_moisture_south_1 ORDER BY ts) FILTER (WHERE soil_moisture_south_1 IS NOT NULL))[1] AS first_s1,
        (array_agg(soil_moisture_south_2 ORDER BY ts DESC) FILTER (WHERE soil_moisture_south_2 IS NOT NULL))[1] AS last_s2,
        (array_agg(soil_moisture_south_2 ORDER BY ts) FILTER (WHERE soil_moisture_south_2 IS NOT NULL))[1] AS first_s2,
        (array_agg(soil_moisture_west ORDER BY ts DESC) FILTER (WHERE soil_moisture_west IS NOT NULL))[1] AS last_w,
        (array_agg(soil_moisture_west ORDER BY ts) FILTER (WHERE soil_moisture_west IS NOT NULL))[1] AS first_w
    FROM climate
    WHERE ts > now() - interval '6 hours'
      AND (soil_moisture_south_1 IS NOT NULL OR soil_moisture_west IS NOT NULL)
),
unpivoted AS (
    SELECT 'south_1'::text AS zone, l.soil_moisture_south_1 AS moisture,
           l.soil_temp_south_1 AS temp, l.soil_ec_south_1 AS ec,
           EXTRACT(epoch FROM (now() - l.ts))::integer AS age_s,
           CASE
             WHEN t.last_s1 - t.first_s1 > 2 THEN 'rising'
             WHEN t.first_s1 - t.last_s1 > 2 THEN 'falling'
             ELSE 'stable'
           END AS trend
    FROM latest l, trend t
    UNION ALL
    SELECT 'south_2', l.soil_moisture_south_2, l.soil_temp_south_2, NULL::double precision,
           EXTRACT(epoch FROM (now() - l.ts))::integer,
           CASE
             WHEN t.last_s2 - t.first_s2 > 2 THEN 'rising'
             WHEN t.first_s2 - t.last_s2 > 2 THEN 'falling'
             ELSE 'stable'
           END
    FROM latest l, trend t
    UNION ALL
    SELECT 'west', l.soil_moisture_west, l.soil_temp_west, NULL::double precision,
           EXTRACT(epoch FROM (now() - l.ts))::integer,
           CASE
             WHEN t.last_w - t.first_w > 2 THEN 'rising'
             WHEN t.first_w - t.last_w > 2 THEN 'falling'
             ELSE 'stable'
           END
    FROM latest l, trend t
)
SELECT
    u.zone,
    u.moisture,
    u.temp,
    u.ec,
    u.age_s,
    u.trend,
    t.min_pct,
    t.max_pct,
    t.crop,
    CASE
        WHEN u.moisture IS NULL THEN 'offline'
        WHEN u.moisture < t.wilt_pct THEN 'critical_dry'
        WHEN u.moisture < t.min_pct THEN 'dry'
        WHEN u.moisture > t.saturation_pct THEN 'saturated'
        WHEN u.moisture > t.max_pct THEN 'wet'
        ELSE 'ok'
    END AS status
FROM unpivoted u
LEFT JOIN soil_moisture_targets t ON u.zone = t.zone;

COMMENT ON VIEW v_soil_status IS
'Latest soil readings with target comparison and true 6-hour moisture trend.';

-- More complete freshness/null telemetry while preserving the old columns.
CREATE OR REPLACE VIEW v_data_pipeline_health AS
SELECT 'climate'::text AS source,
       count(*) FILTER (WHERE ts > now() - interval '1 hour') AS rows_1h,
       count(*) FILTER (WHERE ts > now() - interval '24 hours') AS rows_24h,
       GREATEST(EXTRACT(epoch FROM (now() - max(ts)))::integer, 0) AS age_s,
       100.0 * (
         count(*) FILTER (
           WHERE ts > now() - interval '1 hour'
             AND (temp_avg IS NULL OR rh_avg IS NULL OR vpd_avg IS NULL OR dew_point IS NULL)
         )::double precision
         / NULLIF(count(*) FILTER (WHERE ts > now() - interval '1 hour'), 0)
       ) AS null_pct_1h
FROM climate
UNION ALL
SELECT 'hydro'::text AS source,
       count(*) FILTER (WHERE ts > now() - interval '1 hour' AND (hydro_ph IS NOT NULL OR hydro_ec_us_cm IS NOT NULL)) AS rows_1h,
       count(*) FILTER (WHERE ts > now() - interval '24 hours' AND (hydro_ph IS NOT NULL OR hydro_ec_us_cm IS NOT NULL)) AS rows_24h,
       GREATEST(EXTRACT(epoch FROM (now() - max(ts) FILTER (WHERE hydro_ph IS NOT NULL OR hydro_ec_us_cm IS NOT NULL)))::integer, 0) AS age_s,
       100.0 * (
         count(*) FILTER (
           WHERE ts > now() - interval '1 hour'
             AND (hydro_ph IS NULL OR hydro_ec_us_cm IS NULL)
             AND (hydro_ph IS NOT NULL OR hydro_ec_us_cm IS NOT NULL)
         )::double precision
         / NULLIF(count(*) FILTER (
             WHERE ts > now() - interval '1 hour'
               AND (hydro_ph IS NOT NULL OR hydro_ec_us_cm IS NOT NULL)
           ), 0)
       ) AS null_pct_1h
FROM climate
UNION ALL
SELECT 'equipment'::text AS source,
       count(*) FILTER (WHERE ts > now() - interval '1 hour') AS rows_1h,
       count(*) FILTER (WHERE ts > now() - interval '24 hours') AS rows_24h,
       GREATEST(EXTRACT(epoch FROM (now() - max(ts)))::integer, 0) AS age_s,
       NULL::double precision AS null_pct_1h
FROM equipment_state
UNION ALL
SELECT 'diagnostics'::text AS source,
       count(*) FILTER (WHERE ts > now() - interval '1 hour') AS rows_1h,
       count(*) FILTER (WHERE ts > now() - interval '24 hours') AS rows_24h,
       GREATEST(EXTRACT(epoch FROM (now() - max(ts)))::integer, 0) AS age_s,
       100.0 * (
         count(*) FILTER (
           WHERE ts > now() - interval '1 hour'
             AND (wifi_rssi IS NULL OR heap_bytes IS NULL OR uptime_s IS NULL OR active_probe_count IS NULL)
         )::double precision
         / NULLIF(count(*) FILTER (WHERE ts > now() - interval '1 hour'), 0)
       ) AS null_pct_1h
FROM diagnostics
UNION ALL
SELECT 'energy'::text AS source,
       count(*) FILTER (WHERE ts > now() - interval '1 hour') AS rows_1h,
       count(*) FILTER (WHERE ts > now() - interval '24 hours') AS rows_24h,
       GREATEST(EXTRACT(epoch FROM (now() - max(ts)))::integer, 0) AS age_s,
       NULL::double precision AS null_pct_1h
FROM energy
UNION ALL
SELECT 'setpoints'::text AS source,
       count(*) FILTER (WHERE ts > now() - interval '1 hour') AS rows_1h,
       count(*) FILTER (WHERE ts > now() - interval '24 hours') AS rows_24h,
       GREATEST(EXTRACT(epoch FROM (now() - max(ts)))::integer, 0) AS age_s,
       NULL::double precision AS null_pct_1h
FROM setpoint_changes
UNION ALL
SELECT 'forecast'::text AS source,
       count(*) FILTER (WHERE fetched_at > now() - interval '1 hour') AS rows_1h,
       count(*) FILTER (WHERE fetched_at > now() - interval '24 hours') AS rows_24h,
       GREATEST(EXTRACT(epoch FROM (now() - max(fetched_at)))::integer, 0) AS age_s,
       100.0 * (
         count(*) FILTER (
           WHERE fetched_at = (SELECT max(fetched_at) FROM weather_forecast)
             AND (temp_f IS NULL OR rh_pct IS NULL OR solar_w_m2 IS NULL)
         )::double precision
         / NULLIF(count(*) FILTER (WHERE fetched_at = (SELECT max(fetched_at) FROM weather_forecast)), 0)
       ) AS null_pct_1h
FROM weather_forecast
UNION ALL
SELECT 'daily_summary'::text AS source,
       count(*) FILTER (WHERE captured_at > now() - interval '1 hour') AS rows_1h,
       count(*) FILTER (WHERE captured_at > now() - interval '24 hours') AS rows_24h,
       GREATEST(EXTRACT(epoch FROM (now() - max(captured_at)))::integer, 0) AS age_s,
       100.0 * (
         count(*) FILTER (
           WHERE date >= (now() AT TIME ZONE 'America/Denver')::date - 1
             AND (temp_avg IS NULL OR rh_avg IS NULL OR vpd_avg IS NULL OR compliance_pct IS NULL)
         )::double precision
         / NULLIF(count(*) FILTER (WHERE date >= (now() AT TIME ZONE 'America/Denver')::date - 1), 0)
       ) AS null_pct_1h
FROM daily_summary;

CREATE OR REPLACE VIEW v_required_sensor_coverage AS
SELECT
    cfg.greenhouse_id,
    cfg.target_table,
    cfg.target_column,
    cfg.entity_name,
    cfg.entity_type,
    cfg.is_required,
    sr.sensor_id,
    COALESCE(sr.active, false) AS registry_active,
    vs.last_seen_at,
    vs.seconds_since,
    COALESCE(vs.is_stale, true) AS is_stale,
    CASE
        WHEN sr.sensor_id IS NULL THEN 'missing_registry'
        WHEN sr.active IS NOT TRUE THEN 'inactive_registry'
        WHEN vs.is_stale THEN 'stale'
        ELSE 'ok'
    END AS coverage_status
FROM greenhouse_sensor_config cfg
LEFT JOIN sensor_registry sr
  ON sr.source_table = cfg.target_table
 AND sr.source_column = cfg.target_column
LEFT JOIN v_sensor_staleness vs
  ON vs.sensor_id = sr.sensor_id
WHERE cfg.is_required = true;

COMMENT ON VIEW v_required_sensor_coverage IS
'Required configured sensors joined to registry and live staleness status.';

CREATE OR REPLACE VIEW v_energy_daily AS
WITH samples AS (
    SELECT
        ((ts AT TIME ZONE 'America/Denver')::date::timestamp AT TIME ZONE 'America/Denver') AS day,
        ts,
        watts_total,
        lead(ts) OVER (PARTITION BY (ts AT TIME ZONE 'America/Denver')::date ORDER BY ts) AS next_ts
    FROM energy
    WHERE watts_total IS NOT NULL
),
durations AS (
    SELECT
        day,
        watts_total,
        LEAST(
            GREATEST(EXTRACT(epoch FROM (COALESCE(next_ts, ts) - ts)), 0),
            900
        ) / 3600.0 AS hours_observed
    FROM samples
)
SELECT
    day::date AS date,
    round(sum(watts_total * hours_observed / 1000.0)::numeric, 3) AS measured_kwh,
    round(avg(watts_total)::numeric, 1) AS avg_watts,
    round(max(watts_total)::numeric, 1) AS peak_watts
FROM durations
GROUP BY day::date
ORDER BY day::date;

CREATE OR REPLACE VIEW v_energy_estimate_reconciliation AS
SELECT
    ds.date,
    ds.kwh_estimated,
    ed.measured_kwh,
    round((ds.kwh_estimated - ed.measured_kwh)::numeric, 3) AS estimate_delta_kwh,
    CASE
        WHEN ed.measured_kwh IS NULL THEN 'missing_measured'
        WHEN ds.kwh_estimated IS NULL THEN 'missing_estimate'
        WHEN abs(ds.kwh_estimated - ed.measured_kwh) > GREATEST(5, ed.measured_kwh * 0.5) THEN 'mismatch'
        ELSE 'ok'
    END AS quality_flag
FROM daily_summary ds
LEFT JOIN v_energy_daily ed USING (date)
WHERE ds.date IS NOT NULL;

COMMENT ON VIEW v_energy_estimate_reconciliation IS
'Compares runtime-estimated kWh in daily_summary against watt-time integration from energy telemetry.';

CREATE OR REPLACE VIEW v_setpoint_delivery_latency AS
SELECT
    parameter,
    source,
    count(*) AS changes,
    count(*) FILTER (WHERE confirmed_at IS NOT NULL) AS confirmed,
    round(100.0 * count(*) FILTER (WHERE confirmed_at IS NOT NULL) / NULLIF(count(*), 0), 1) AS confirmed_pct,
    percentile_disc(0.50) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM (confirmed_at - ts)))
        FILTER (WHERE confirmed_at IS NOT NULL) AS p50_confirm_s,
    percentile_disc(0.95) WITHIN GROUP (ORDER BY EXTRACT(epoch FROM (confirmed_at - ts)))
        FILTER (WHERE confirmed_at IS NOT NULL) AS p95_confirm_s,
    max(ts) AS latest_change
FROM setpoint_changes
WHERE ts > now() - interval '7 days'
GROUP BY parameter, source;

COMMENT ON VIEW v_setpoint_delivery_latency IS
'Seven-day setpoint push/readback confirmation coverage and latency.';

CREATE OR REPLACE VIEW v_mister_zone_effectiveness AS
WITH starts AS (
    SELECT
        ts AS on_ts,
        equipment,
        CASE equipment
            WHEN 'mister_south' THEN 'south'
            WHEN 'mister_west' THEN 'west'
            WHEN 'mister_center' THEN 'center'
        END AS zone,
        lead(ts) OVER (PARTITION BY equipment ORDER BY ts) AS off_ts
    FROM equipment_state
    WHERE equipment IN ('mister_south', 'mister_west', 'mister_center')
      AND state = true
      AND ts > now() - interval '30 days'
)
SELECT
    s.on_ts,
    s.equipment,
    s.zone,
    EXTRACT(epoch FROM (s.off_ts - s.on_ts))::integer AS duration_s,
    before_vpd.vpd AS zone_vpd_before,
    after_vpd.vpd AS zone_vpd_after,
    round((before_vpd.vpd - after_vpd.vpd)::numeric, 3) AS zone_vpd_delta
FROM starts s
LEFT JOIN LATERAL (
    SELECT CASE s.zone
        WHEN 'south' THEN vpd_south
        WHEN 'west' THEN vpd_west
        ELSE vpd_avg
    END AS vpd
    FROM climate
    WHERE ts <= s.on_ts
    ORDER BY ts DESC
    LIMIT 1
) before_vpd ON true
LEFT JOIN LATERAL (
    SELECT CASE s.zone
        WHEN 'south' THEN vpd_south
        WHEN 'west' THEN vpd_west
        ELSE vpd_avg
    END AS vpd
    FROM climate
    WHERE ts >= COALESCE(s.off_ts, s.on_ts) + interval '5 minutes'
    ORDER BY ts ASC
    LIMIT 1
) after_vpd ON true
WHERE s.off_ts IS NOT NULL;

COMMENT ON VIEW v_mister_zone_effectiveness IS
'Mister on-events with zone-local VPD before and after the pulse. Center uses greenhouse average until a center VPD sensor exists.';

CREATE OR REPLACE VIEW v_plan_tactical_outcome_daily AS
SELECT
    sp.plan_id,
    (min(sp.created_at) AT TIME ZONE 'America/Denver')::date AS plan_date,
    sp.parameter,
    count(*) AS waypoints,
    round(avg(sp.value)::numeric, 3) AS avg_value,
    round(min(sp.value)::numeric, 3) AS min_value,
    round(max(sp.value)::numeric, 3) AS max_value,
    ds.compliance_pct,
    ds.temp_compliance_pct,
    ds.vpd_compliance_pct,
    ds.stress_hours_heat,
    ds.stress_hours_vpd_high,
    ds.stress_hours_cold,
    ds.stress_hours_vpd_low,
    ds.water_used_gal,
    ds.mister_water_gal,
    ds.cost_total
FROM setpoint_plan sp
LEFT JOIN daily_summary ds
  ON ds.date = (sp.ts AT TIME ZONE 'America/Denver')::date
WHERE sp.parameter IN (
    'mister_engage_kpa', 'mister_all_kpa', 'mister_pulse_on_s',
    'mister_pulse_gap_s', 'mister_vpd_weight', 'bias_heat', 'bias_cool',
    'd_cool_stage_2', 'd_heat_stage_2', 'vpd_hysteresis',
    'fog_escalation_kpa', 'mist_backoff_s'
)
GROUP BY sp.plan_id, sp.parameter, ds.date, ds.compliance_pct, ds.temp_compliance_pct,
         ds.vpd_compliance_pct, ds.stress_hours_heat, ds.stress_hours_vpd_high,
         ds.stress_hours_cold, ds.stress_hours_vpd_low, ds.water_used_gal,
         ds.mister_water_gal, ds.cost_total;

COMMENT ON VIEW v_plan_tactical_outcome_daily IS
'Planner tactical parameter posture joined to same-day compliance, stress, water, and cost outcomes. Directional, not causal.';

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
SELECT 'energy_reconciliation_14d',
       CASE WHEN count(*) FILTER (WHERE quality_flag <> 'ok') = 0 THEN 'ok' ELSE 'warn' END,
       count(*) FILTER (WHERE quality_flag <> 'ok')::numeric,
       0::numeric,
       'estimated vs measured energy mismatches in last 14 local days'
FROM v_energy_estimate_reconciliation
WHERE date >= (now() AT TIME ZONE 'America/Denver')::date - 14;

COMMENT ON VIEW v_data_trust_ledger IS
'Owner-facing data trust checks for freshness, coverage, lifecycle consistency, gaps, water, and energy reconciliation.';
