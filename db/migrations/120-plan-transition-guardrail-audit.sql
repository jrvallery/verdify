-- Migration 120: plan transition guardrail audit
--
-- Makes the planner -> dispatcher -> ESP32 transition path auditable even when
-- a guardrail intentionally holds an unchanged applied value and no
-- setpoint_changes row is emitted.

BEGIN;

ALTER TABLE setpoint_clamps
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'clamped',
    ADD COLUMN IF NOT EXISTS plan_id TEXT,
    ADD COLUMN IF NOT EXISTS plan_ts TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS trigger_id UUID,
    ADD COLUMN IF NOT EXISTS planner_instance TEXT;

CREATE INDEX IF NOT EXISTS idx_setpoint_clamps_plan
    ON setpoint_clamps (plan_id, plan_ts DESC)
    WHERE plan_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_setpoint_clamps_status_ts
    ON setpoint_clamps (status, ts DESC);

COMMENT ON COLUMN setpoint_clamps.status IS
  'clamped = legacy/default; guardrailed = adjusted value was dispatched; held_by_guardrail = requested transition was intentionally held and no setpoint_changes row was emitted; rejected = registry/schema rejected the value.';
COMMENT ON COLUMN setpoint_clamps.plan_id IS
  'Planner plan_id associated with the requested value, copied from v_active_plan when available.';
COMMENT ON COLUMN setpoint_clamps.plan_ts IS
  'Setpoint_plan transition timestamp associated with the requested value, copied from v_active_plan when available.';

CREATE OR REPLACE VIEW v_plan_guardrail_scorecard AS
SELECT
    pei.plan_id,
    count(sc.*)::int AS guardrail_events,
    count(*) FILTER (WHERE sc.status = 'held_by_guardrail')::int AS held_guardrail_events,
    count(*) FILTER (WHERE sc.status = 'guardrailed')::int AS dispatched_guardrail_events,
    count(*) FILTER (WHERE sc.reason = 'vpd_high_moisture_guardrail')::int AS vpd_high_guardrail_events,
    CASE
      WHEN count(sc.*) >= 20 OR count(*) FILTER (WHERE sc.status = 'held_by_guardrail') >= 10 THEN 3
      WHEN count(sc.*) >= 8  OR count(*) FILTER (WHERE sc.status = 'held_by_guardrail') >= 3  THEN 2
      WHEN count(sc.*) >= 3  OR count(*) FILTER (WHERE sc.status = 'held_by_guardrail') >= 1  THEN 1
      ELSE 0
    END::smallint AS guardrail_penalty
FROM v_plan_execution_intervals pei
LEFT JOIN setpoint_clamps sc
  ON sc.greenhouse_id = pei.greenhouse_id
 AND sc.ts >= pei.interval_start
 AND sc.ts < pei.interval_end
GROUP BY pei.plan_id;

COMMENT ON VIEW v_plan_guardrail_scorecard IS
  'Per-plan guardrail dependence counts and deterministic penalty. Used by fn_plan_anchor_score so plans that repeatedly require dispatcher clamps/holds lose score.';

CREATE OR REPLACE FUNCTION fn_plan_transition_audit(
    p_plan_id text DEFAULT NULL,
    p_lookback interval DEFAULT '36 hours',
    p_window interval DEFAULT '10 minutes'
)
RETURNS TABLE (
    plan_id text,
    plan_created_at timestamptz,
    transition_ts timestamptz,
    parameter text,
    planned_value double precision,
    prior_value double precision,
    applied_value double precision,
    readback_value double precision,
    status text,
    guardrail_reason text,
    push_ts timestamptz,
    push_latency_s integer,
    confirmed_at timestamptz,
    confirm_latency_s integer,
    matching_push_ts timestamptz,
    readback_ts timestamptz,
    trigger_id uuid,
    planner_instance text
)
LANGUAGE sql
STABLE
AS $$
WITH scoped AS (
    SELECT sp.*,
           lag(sp.value) OVER (PARTITION BY sp.plan_id, sp.parameter ORDER BY sp.ts) AS prev_plan_value
      FROM setpoint_plan sp
     WHERE sp.is_active IS TRUE
       AND sp.parameter NOT IN ('temp_low', 'temp_high', 'vpd_low', 'vpd_high')
       AND (
            (p_plan_id IS NOT NULL AND sp.plan_id = p_plan_id)
         OR (p_plan_id IS NULL AND sp.created_at >= now() - p_lookback)
       )
), transitions AS (
    SELECT *
      FROM scoped
     WHERE ts <= now()
       AND (prev_plan_value IS NULL OR abs(value - prev_plan_value) > 0.0001)
)
SELECT
    t.plan_id,
    t.created_at AS plan_created_at,
    t.ts AS transition_ts,
    t.parameter,
    t.value AS planned_value,
    prior.value AS prior_value,
    COALESCE(first_push.value, guardrail.applied, prior.value) AS applied_value,
    readback.value AS readback_value,
    CASE
      WHEN prior.value IS NOT NULL AND abs(prior.value - t.value) <= 0.0001
        THEN 'already_at_value'
      WHEN first_push.ts IS NOT NULL AND abs(first_push.value - t.value) <= 0.0001
        THEN 'matched'
      WHEN guardrail.ts IS NOT NULL AND first_push.ts IS NOT NULL
        THEN 'guardrailed'
      WHEN guardrail.ts IS NOT NULL
        THEN 'held_by_guardrail'
      WHEN first_push.ts IS NULL
        THEN 'missed'
      ELSE 'mismatch'
    END AS status,
    guardrail.reason AS guardrail_reason,
    first_push.ts AS push_ts,
    CASE WHEN first_push.ts IS NULL THEN NULL
         ELSE extract(epoch FROM first_push.ts - t.ts)::int
    END AS push_latency_s,
    first_push.confirmed_at,
    CASE WHEN first_push.confirmed_at IS NULL OR first_push.ts IS NULL THEN NULL
         ELSE extract(epoch FROM first_push.confirmed_at - first_push.ts)::int
    END AS confirm_latency_s,
    matching_push.ts AS matching_push_ts,
    readback.ts AS readback_ts,
    t.trigger_id,
    t.planner_instance
FROM transitions t
LEFT JOIN LATERAL (
    SELECT sc.ts, sc.value
      FROM setpoint_changes sc
     WHERE sc.greenhouse_id = t.greenhouse_id
       AND sc.parameter = t.parameter
       AND sc.ts < t.ts
     ORDER BY sc.ts DESC
     LIMIT 1
) prior ON TRUE
LEFT JOIN LATERAL (
    SELECT sc.ts, sc.value, sc.confirmed_at
      FROM setpoint_changes sc
     WHERE sc.greenhouse_id = t.greenhouse_id
       AND sc.parameter = t.parameter
       AND sc.ts >= t.ts
       AND sc.ts < t.ts + p_window
       AND sc.source = 'plan'
     ORDER BY sc.ts ASC
     LIMIT 1
) first_push ON TRUE
LEFT JOIN LATERAL (
    SELECT sc.ts, sc.value
      FROM setpoint_changes sc
     WHERE sc.greenhouse_id = t.greenhouse_id
       AND sc.parameter = t.parameter
       AND sc.ts >= t.ts
       AND sc.ts < t.ts + interval '2 hours'
       AND sc.source = 'plan'
       AND abs(sc.value - t.value) <= 0.0001
     ORDER BY sc.ts ASC
     LIMIT 1
) matching_push ON TRUE
LEFT JOIN LATERAL (
    SELECT c.ts, c.applied, c.reason, c.status
      FROM setpoint_clamps c
     WHERE c.greenhouse_id = t.greenhouse_id
       AND c.parameter = t.parameter
       AND (
            (c.plan_id = t.plan_id AND c.plan_ts = t.ts)
         OR (c.plan_id IS NULL AND c.ts >= t.ts - interval '30 seconds' AND c.ts < t.ts + p_window)
       )
     ORDER BY c.ts ASC
     LIMIT 1
) guardrail ON TRUE
LEFT JOIN LATERAL (
    SELECT ss.ts, ss.value
      FROM setpoint_snapshot ss
     WHERE ss.greenhouse_id = t.greenhouse_id
       AND ss.parameter = t.parameter
       AND ss.ts >= t.ts
       AND ss.ts < t.ts + p_window
     ORDER BY ss.ts ASC
     LIMIT 1
) readback ON TRUE
ORDER BY t.created_at DESC, t.ts ASC, t.parameter ASC;
$$;

COMMENT ON FUNCTION fn_plan_transition_audit(text, interval, interval) IS
  'Guardrail-aware transition audit for planner-owned params. Statuses: already_at_value, matched, guardrailed, held_by_guardrail, missed, mismatch.';

CREATE OR REPLACE VIEW v_plan_transition_audit_36h AS
SELECT * FROM fn_plan_transition_audit(NULL, '36 hours'::interval, '10 minutes'::interval);

COMMENT ON VIEW v_plan_transition_audit_36h IS
  'Last-36h guardrail-aware planner transition audit for operator/planner context.';

CREATE OR REPLACE FUNCTION fn_plan_anchor_score(p_plan_id text)
RETURNS smallint
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_comp numeric;
  v_str  numeric;
  v_frac numeric;
  v_anchor smallint;
  v_penalty smallint := 0;
BEGIN
  SELECT compliance_pct, total_stress_h, governed_day_fraction
    INTO v_comp, v_str, v_frac
    FROM v_plan_window_scorecard
   WHERE plan_id = p_plan_id;

  IF NOT FOUND OR v_frac IS NULL OR v_frac < 0.05 THEN
    RETURN NULL;
  END IF;

  IF v_comp IS NULL OR v_str IS NULL THEN
    RETURN NULL;
  END IF;

  IF v_comp >= 90 AND v_str <  2 THEN v_anchor := 10;
  ELSIF v_comp >= 85 AND v_str <  3 THEN v_anchor :=  9;
  ELSIF v_comp >= 75 AND v_str <  5 THEN v_anchor :=  8;
  ELSIF v_comp >= 70 AND v_str <  7 THEN v_anchor :=  7;
  ELSIF v_comp >= 60 AND v_str < 10 THEN v_anchor :=  6;
  ELSIF v_comp >= 50 AND v_str < 14 THEN v_anchor :=  5;
  ELSIF v_comp >= 40 AND v_str < 20 THEN v_anchor :=  4;
  ELSIF v_comp >= 25 AND v_str < 28 THEN v_anchor :=  3;
  ELSIF v_comp >= 10                THEN v_anchor :=  2;
  ELSE v_anchor := 1;
  END IF;

  SELECT COALESCE(guardrail_penalty, 0)
    INTO v_penalty
    FROM v_plan_guardrail_scorecard
   WHERE plan_id = p_plan_id;

  RETURN GREATEST(1, v_anchor - COALESCE(v_penalty, 0));
END;
$$;

COMMENT ON FUNCTION fn_plan_anchor_score(text) IS
  'Deterministic 1-10 anchor score for a plan, computed from time-weighted compliance + stress hours over its governed interval, minus guardrail-dependence penalty from v_plan_guardrail_scorecard.';

COMMIT;
