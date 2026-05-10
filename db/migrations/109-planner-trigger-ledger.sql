-- Migration 109: planner expected-trigger ledger and health surface
--
-- plan_delivery_log records calls that were actually delivered to OpenClaw.
-- That still leaves a launch-critical blind spot: if a required trigger is
-- never delivered, there is no row to time out. This ledger materializes the
-- expected trigger schedule first, then links each expected trigger to the
-- delivery row and eventual plan outcome.

BEGIN;

CREATE TABLE IF NOT EXISTS planner_trigger_ledger (
    id                    BIGSERIAL PRIMARY KEY,
    greenhouse_id          TEXT NOT NULL DEFAULT 'vallery' REFERENCES greenhouses(id),
    event_type             TEXT NOT NULL,
    event_label            TEXT,
    instance               TEXT,
    expected_at            TIMESTAMPTZ NOT NULL,
    due_at                 TIMESTAMPTZ NOT NULL,
    delivered_at           TIMESTAMPTZ,
    resolved_at            TIMESTAMPTZ,
    status                 TEXT NOT NULL DEFAULT 'expected',
    expected_action        TEXT NOT NULL DEFAULT 'any',
    sla_seconds            INTEGER,
    catchup                BOOLEAN NOT NULL DEFAULT false,
    plan_delivery_log_id   INTEGER REFERENCES plan_delivery_log(id),
    trigger_id             UUID,
    resulting_plan_id      TEXT,
    notes                  TEXT,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT planner_trigger_ledger_status_check
        CHECK (status IN (
            'expected',
            'delivered',
            'acked',
            'plan_written',
            'delivery_failed',
            'timed_out',
            'missed'
        )),
    CONSTRAINT planner_trigger_ledger_expected_action_check
        CHECK (expected_action IN ('set_plan', 'set_tunable', 'acknowledge_trigger', 'any'))
);

CREATE UNIQUE INDEX IF NOT EXISTS planner_trigger_ledger_expected_key
    ON planner_trigger_ledger (greenhouse_id, event_type, expected_at);

CREATE INDEX IF NOT EXISTS planner_trigger_ledger_status_due_idx
    ON planner_trigger_ledger (status, due_at);

CREATE INDEX IF NOT EXISTS planner_trigger_ledger_expected_at_idx
    ON planner_trigger_ledger (expected_at DESC);

CREATE INDEX IF NOT EXISTS planner_trigger_ledger_trigger_id_idx
    ON planner_trigger_ledger (trigger_id);

CREATE INDEX IF NOT EXISTS planner_trigger_ledger_delivery_idx
    ON planner_trigger_ledger (plan_delivery_log_id);

COMMENT ON TABLE planner_trigger_ledger IS
    'Expected planner trigger ledger. Rows are written before delivery so missed '
    'SUNRISE/SUNSET/MIDNIGHT cycles are visible even when no OpenClaw delivery '
    'row exists.';

COMMENT ON COLUMN planner_trigger_ledger.status IS
    'Lifecycle: expected -> delivered -> plan_written/acked, or delivery_failed, '
    'timed_out, missed. missed means the expected trigger was never delivered by '
    'its due_at; timed_out means delivered but not resolved before SLA.';

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
)
SELECT
    now() AS generated_at,
    (SELECT count(*) FROM recent WHERE status = 'expected' AND due_at < now())::int
        AS missed_expected_count,
    (SELECT count(*) FROM recent WHERE status IN ('delivered') AND due_at < now())::int
        AS overdue_delivered_count,
    (SELECT count(*) FROM recent
      WHERE event_type IN ('SUNRISE', 'SUNSET', 'MIDNIGHT')
        AND status IN ('missed', 'timed_out', 'delivery_failed'))::int
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
    'Public/ops-safe summary of expected planner trigger health over the last 36h.';

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
         WHEN count(*) FILTER (
             WHERE event_type IN ('SUNRISE', 'SUNSET', 'MIDNIGHT')
               AND status IN ('missed', 'timed_out', 'delivery_failed')
         ) > 0 THEN 'fail'
         WHEN count(*) FILTER (
             WHERE due_at < now()
               AND status IN ('expected', 'delivered')
         ) > 0 THEN 'warn'
         ELSE 'ok'
       END,
       (
         count(*) FILTER (
             WHERE (
                    event_type IN ('SUNRISE', 'SUNSET', 'MIDNIGHT')
                    AND status IN ('missed', 'timed_out', 'delivery_failed')
                 )
                OR (
                    due_at < now()
                    AND status IN ('expected', 'delivered')
                 )
         )
       )::numeric,
       0::numeric,
       'required planner trigger failures or currently overdue expected/delivered triggers in last 36h'
FROM planner_trigger_ledger
WHERE expected_at >= now() - interval '36 hours'
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
'Owner-facing public health checks spanning freshness, coverage, gaps, planner trigger SLA, water hard failures, measured energy sync, forecasts, crop completeness, and generated archives. Future instrumentation requirements are reported separately from live-system health.';

COMMIT;
