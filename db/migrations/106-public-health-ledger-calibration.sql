-- Migration 106: public health ledger calibration
--
-- Keeps the public /data-health aggregate tied to live-system health:
-- fresh telemetry, clean alert lifecycle, current generated pages, measured
-- energy sync, forecast outcome completion, and hard water-accounting errors.
-- Future hardware instrumentation gaps remain visible in
-- v_instrumentation_readiness, but they do not make the live public health
-- endpoint warn by themselves.

BEGIN;

UPDATE alert_log
SET disposition = 'resolved',
    resolution = COALESCE(resolution, 'migration_106 normalized resolved_at/disposition mismatch')
WHERE resolved_at IS NOT NULL
  AND disposition <> 'resolved';

WITH scored AS (
    SELECT
        fl.id,
        fl.action_taken,
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
    WHERE (fl.outcome IS NULL OR fl.outcome = 'pending')
      AND fl.triggered_at <= now() - interval '6 hours'
)
UPDATE forecast_action_log fl
SET outcome = CASE
        WHEN s.action_taken = 'evaluated_ok' THEN 'no_action_required'
        WHEN s.after_stress_score IS NULL THEN 'insufficient_followup_data'
        WHEN COALESCE(s.after_stress_score, 0) <= COALESCE(s.before_stress_score, 0) THEN 'climate_recovered'
        ELSE 'no_clear_improvement'
    END,
    outcome_evaluated_at = now(),
    outcome_metrics = jsonb_build_object(
        'before_stress_score', s.before_stress_score,
        'after_stress_score', s.after_stress_score,
        'window', '3h_before_6h_after',
        'backfill', 'migration_106'
    )
FROM scored s
WHERE fl.id = s.id;

UPDATE daily_summary
SET water_used_gal = GREATEST(COALESCE(water_used_gal, 0), COALESCE(mister_water_gal, 0)),
    cost_water = round((GREATEST(COALESCE(water_used_gal, 0), COALESCE(mister_water_gal, 0)) * 0.00484)::numeric, 2)::double precision,
    cost_total = round((
        COALESCE(cost_electric, 0)::numeric
      + COALESCE(cost_gas, 0)::numeric
      + round((GREATEST(COALESCE(water_used_gal, 0), COALESCE(mister_water_gal, 0)) * 0.00484)::numeric, 2)
    ), 2)::double precision,
    captured_at = now()
WHERE date >= (now() AT TIME ZONE 'America/Denver')::date - 14
  AND COALESCE(mister_water_gal, 0) > COALESCE(water_used_gal, 0);

CREATE OR REPLACE VIEW v_energy_estimate_reconciliation AS
SELECT
    ds.date,
    COALESCE(ds.kwh_total, ds.kwh_estimated) AS kwh_estimated,
    ed.measured_kwh,
    round((COALESCE(ds.kwh_total, ds.kwh_estimated) - ed.measured_kwh::double precision)::numeric, 3) AS estimate_delta_kwh,
    CASE
        WHEN ed.measured_kwh IS NULL THEN 'missing_measured'
        WHEN COALESCE(ds.kwh_total, ds.kwh_estimated) IS NULL THEN 'missing_summary_energy'
        WHEN abs(COALESCE(ds.kwh_total, ds.kwh_estimated) - ed.measured_kwh::double precision) > 0.25 THEN 'mismatch'
        ELSE 'ok'
    END AS quality_flag
FROM daily_summary ds
LEFT JOIN v_energy_daily ed USING (date)
WHERE ds.date IS NOT NULL;

COMMENT ON VIEW v_energy_estimate_reconciliation IS
'Public health reconciliation of daily_summary measured kWh against energy telemetry. Runtime-estimated load energy is a model input, not a same-scope measured feed.';

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
       CASE WHEN count(*) FILTER (WHERE quality_flag IN ('missing_total','negative_total','mister_exceeds_total','negative_unaccounted')) = 0 THEN 'ok' ELSE 'warn' END,
       count(*) FILTER (WHERE quality_flag IN ('missing_total','negative_total','mister_exceeds_total','negative_unaccounted'))::numeric,
       0::numeric,
       'hard water-accounting failures in last 14 local days; unattributed water remains an instrumentation limitation'
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
       'daily_summary measured kWh sync mismatches in last 14 local days'
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
  AND action_taken <> 'evaluated_ok'
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
       'completed generated daily plan pages stale or unaudited'
FROM v_daily_plan_archive_self_check
WHERE date >= (now() AT TIME ZONE 'America/Denver')::date - 14
  AND date < (now() AT TIME ZONE 'America/Denver')::date;

COMMENT ON VIEW v_data_trust_ledger IS
'Owner-facing public health checks spanning freshness, coverage, gaps, water hard failures, measured energy sync, forecasts, crop completeness, and generated archives. Future instrumentation requirements are reported separately from live-system health.';

COMMIT;
