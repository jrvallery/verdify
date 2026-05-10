-- Migration 110: planner health recovery calibration
--
-- Required planner triggers should fail public health while the required
-- planning loop is unrecovered. Once a later required plan writes successfully,
-- the historical failure remains visible in recent_triggers but no longer keeps
-- the current public health surface in fail.

BEGIN;

CREATE OR REPLACE VIEW v_planner_trigger_health AS
WITH recent AS (
    SELECT *
      FROM planner_trigger_ledger
     WHERE expected_at >= now() - interval '36 hours'
),
latest_required AS (
    SELECT DISTINCT ON (event_type)
           event_type,
           event_label,
           instance,
           expected_at,
           due_at,
           delivered_at,
           resolved_at,
           status,
           resulting_plan_id,
           trigger_id
      FROM recent
     WHERE event_type IN ('SUNRISE', 'SUNSET', 'MIDNIGHT')
     ORDER BY event_type, expected_at DESC
),
last_required_recovery AS (
    SELECT max(expected_at) AS expected_at
      FROM recent
     WHERE event_type IN ('SUNRISE', 'SUNSET', 'MIDNIGHT')
       AND status = 'plan_written'
),
unrecovered_required_failures AS (
    SELECT r.*
      FROM recent r
      CROSS JOIN last_required_recovery lrr
     WHERE r.event_type IN ('SUNRISE', 'SUNSET', 'MIDNIGHT')
       AND r.status IN ('missed', 'timed_out', 'delivery_failed')
       AND (lrr.expected_at IS NULL OR r.expected_at > lrr.expected_at)
)
SELECT
    now() AS generated_at,
    (SELECT count(*) FROM recent WHERE status = 'expected' AND due_at < now())::int
        AS missed_expected_count,
    (SELECT count(*) FROM recent WHERE status IN ('delivered') AND due_at < now())::int
        AS overdue_delivered_count,
    (SELECT count(*) FROM unrecovered_required_failures)::int
        AS required_failure_count,
    (SELECT count(*) FROM recent WHERE status IN ('plan_written', 'acked'))::int
        AS resolved_count,
    (SELECT count(*) FROM recent)::int AS recent_expected_count,
    COALESCE(
        (SELECT jsonb_agg(to_jsonb(latest_required) ORDER BY latest_required.expected_at DESC)
           FROM latest_required),
        '[]'::jsonb
    ) AS latest_required;

COMMENT ON VIEW v_planner_trigger_health IS
    'Public/ops-safe summary of expected planner trigger health over the last 36h. Historical required failures recover after a later required plan writes successfully.';

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
SELECT 'planner_trigger_sla_36h',
       CASE
         WHEN required_failure_count > 0 THEN 'fail'
         WHEN missed_expected_count > 0 OR overdue_delivered_count > 0 THEN 'warn'
         ELSE 'ok'
       END,
       (required_failure_count + missed_expected_count + overdue_delivered_count)::numeric,
       0::numeric,
       'unrecovered required planner trigger failures or currently overdue expected/delivered triggers in last 36h'
FROM v_planner_trigger_health
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
'Owner-facing public health checks spanning freshness, coverage, gaps, recovered planner trigger SLA, water hard failures, measured energy sync, forecasts, crop completeness, and generated archives. Future instrumentation requirements are reported separately from live-system health.';

COMMIT;
