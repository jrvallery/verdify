-- 111-plan-execution-intervals.sql
-- =============================================================================
-- Causal evaluation foundation. (Iris loop overhaul — Phase 1.)
--
-- Today's plan_evaluate() can grade a plan written at 23:26 against the entire
-- preceding day's scorecard because gather-plan-context.sh picks the latest
-- plan with created_at::date <= yesterday. That is wrong on its face — the
-- plan didn't govern the morning that preceded it. Codex's 2026-05-10 audit
-- identified this as THE root measurement problem.
--
-- This migration adds:
--   1. v_plan_execution_intervals     — wall-clock window each plan governed
--   2. v_plan_window_scorecard        — time-weighted scorecard per interval
--   3. fn_plan_anchor_score(plan_id)  — deterministic 1-10 from the scorecard
--   4. plan_journal.anchor_score      — column storing the anchor at evaluate time
--
-- Together these let plan_evaluate() grade the right window and force Iris's
-- self-score to be anchored to a deterministic reference (not invented).
--
-- Note: v_plan_accuracy / v_plan_compliance / v_plan_accuracy_by_day are left
-- intact for Grafana dashboard back-compat. They are structurally obsolete for
-- modern band-aware plans (they evaluate band params that set_plan correctly
-- drops) but other consumers still read them.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1. Anchor-score column on plan_journal
-- -----------------------------------------------------------------------------
ALTER TABLE plan_journal
  ADD COLUMN IF NOT EXISTS anchor_score smallint;

COMMENT ON COLUMN plan_journal.anchor_score IS
  'Deterministic 1-10 grade computed by fn_plan_anchor_score() over the plan''s '
  'governed interval. Iris''s outcome_score is expected within +/-2 of this; '
  'deviation is a learning-quality metric.';

-- -----------------------------------------------------------------------------
-- 2. v_plan_execution_intervals — wall-clock window each plan governed
--
-- A plan governs from its created_at until the next plan supersedes it (the
-- one with the smallest created_at strictly greater than this plan's), bounded
-- by now() for the most recent plan. Filters out 'codex-*' / synthetic plans
-- that are not real Iris plans.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_plan_execution_intervals AS
WITH iris_plans AS (
  SELECT plan_id, created_at, trigger_id, planner_instance, greenhouse_id
    FROM plan_journal
   WHERE plan_id LIKE 'iris-%'
),
ordered AS (
  SELECT plan_id, created_at, trigger_id, planner_instance, greenhouse_id,
         LEAD(created_at) OVER (PARTITION BY greenhouse_id ORDER BY created_at)
           AS superseded_at
    FROM iris_plans
)
SELECT plan_id,
       greenhouse_id,
       created_at                              AS interval_start,
       COALESCE(superseded_at, now())          AS interval_end,
       trigger_id,
       planner_instance,
       EXTRACT(EPOCH FROM (COALESCE(superseded_at, now()) - created_at))/3600.0
                                               AS governed_hours,
       (COALESCE(superseded_at, now()) - created_at) AS governed_duration
  FROM ordered;

COMMENT ON VIEW v_plan_execution_intervals IS
  'Per-plan wall-clock interval during which the plan was the active "current" '
  'plan (until the next plan superseded it). Use this — not created_at::date — '
  'when attributing daily scorecards back to plans.';

-- -----------------------------------------------------------------------------
-- 3. v_plan_window_scorecard — time-weighted scorecard per plan interval
--
-- Computes per-plan stress hours and compliance by time-weighting daily totals
-- against the fraction of each day the plan governed. Compliance is averaged
-- across overlapping days weighted by overlap fraction (approximate but good
-- enough for anchor-scoring; native-interval compliance would require sampling
-- climate × setpoint_snapshot, which is a follow-up tick).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_plan_window_scorecard AS
WITH plan_days AS (
  -- For each plan, enumerate the date(s) its interval overlaps and the
  -- fraction-of-day weight (0..1) the plan governed on each date.
  SELECT pei.plan_id,
         d::date AS day,
         GREATEST(
           EXTRACT(EPOCH FROM (
             LEAST(pei.interval_end,   (d + interval '1 day')::timestamptz)
             - GREATEST(pei.interval_start, d::timestamptz)
           )) / 86400.0,
           0
         ) AS day_weight
    FROM v_plan_execution_intervals pei
   CROSS JOIN LATERAL generate_series(
              pei.interval_start::date,
              LEAST(pei.interval_end::date, current_date),
              interval '1 day'
           ) AS d
)
SELECT pd.plan_id,
       SUM(pd.day_weight)                           AS governed_day_fraction,
       SUM(pd.day_weight * COALESCE(vpp.heat_stress_h, 0))     AS heat_stress_h,
       SUM(pd.day_weight * COALESCE(vpp.cold_stress_h, 0))     AS cold_stress_h,
       SUM(pd.day_weight * COALESCE(vpp.vpd_high_stress_h, 0)) AS vpd_high_stress_h,
       SUM(pd.day_weight * COALESCE(vpp.vpd_low_stress_h, 0))  AS vpd_low_stress_h,
       SUM(pd.day_weight * COALESCE(vpp.total_stress_h, 0))    AS total_stress_h,
       CASE WHEN SUM(pd.day_weight) > 0
            THEN SUM(pd.day_weight * COALESCE(vpp.compliance_pct, 0))
                 / SUM(pd.day_weight)
            ELSE NULL END                                       AS compliance_pct,
       CASE WHEN SUM(pd.day_weight) > 0
            THEN SUM(pd.day_weight * COALESCE(vpp.temp_compliance_pct, 0))
                 / SUM(pd.day_weight)
            ELSE NULL END                                       AS temp_compliance_pct,
       CASE WHEN SUM(pd.day_weight) > 0
            THEN SUM(pd.day_weight * COALESCE(vpp.vpd_compliance_pct, 0))
                 / SUM(pd.day_weight)
            ELSE NULL END                                       AS vpd_compliance_pct,
       SUM(pd.day_weight * COALESCE(vpp.cost_total, 0))         AS cost_total,
       CASE WHEN SUM(pd.day_weight) > 0
            THEN SUM(pd.day_weight * COALESCE(vpp.planner_score, 0))
                 / SUM(pd.day_weight)
            ELSE NULL END                                       AS planner_score
  FROM plan_days pd
  LEFT JOIN v_planner_performance vpp ON vpp.date = pd.day
 GROUP BY pd.plan_id;

COMMENT ON VIEW v_plan_window_scorecard IS
  'Per-plan scorecard time-weighted against the fraction of each overlapping '
  'day the plan governed. Compliance is fractional-day-weighted average — '
  'approximate but suitable for fn_plan_anchor_score.';

-- -----------------------------------------------------------------------------
-- 4. fn_plan_anchor_score — deterministic 1-10 grade
--
-- Mapping (compliance × stress matters more than cost):
--   compliance >= 90 AND stress_h <  2  -> 10
--   compliance >= 85 AND stress_h <  3  ->  9
--   compliance >= 75 AND stress_h <  5  ->  8
--   compliance >= 70 AND stress_h <  7  ->  7
--   compliance >= 60 AND stress_h < 10  ->  6
--   compliance >= 50 AND stress_h < 14  ->  5
--   compliance >= 40 AND stress_h < 20  ->  4
--   compliance >= 25 AND stress_h < 28  ->  3
--   compliance >= 10                    ->  2
--   else                                ->  1
-- Returns NULL if the plan has not yet governed any time (interval not closed
-- and not enough scorecard data).
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_plan_anchor_score(p_plan_id text)
RETURNS smallint
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_comp numeric;
  v_str  numeric;
  v_frac numeric;
BEGIN
  SELECT compliance_pct, total_stress_h, governed_day_fraction
    INTO v_comp, v_str, v_frac
    FROM v_plan_window_scorecard
   WHERE plan_id = p_plan_id;

  IF NOT FOUND OR v_frac IS NULL OR v_frac < 0.05 THEN
    -- Plan governed less than ~1.2 hours of any covered day; not enough
    -- signal to anchor on.
    RETURN NULL;
  END IF;

  IF v_comp IS NULL OR v_str IS NULL THEN
    RETURN NULL;
  END IF;

  IF v_comp >= 90 AND v_str <  2 THEN RETURN 10; END IF;
  IF v_comp >= 85 AND v_str <  3 THEN RETURN  9; END IF;
  IF v_comp >= 75 AND v_str <  5 THEN RETURN  8; END IF;
  IF v_comp >= 70 AND v_str <  7 THEN RETURN  7; END IF;
  IF v_comp >= 60 AND v_str < 10 THEN RETURN  6; END IF;
  IF v_comp >= 50 AND v_str < 14 THEN RETURN  5; END IF;
  IF v_comp >= 40 AND v_str < 20 THEN RETURN  4; END IF;
  IF v_comp >= 25 AND v_str < 28 THEN RETURN  3; END IF;
  IF v_comp >= 10                THEN RETURN  2; END IF;
  RETURN 1;
END;
$$;

COMMENT ON FUNCTION fn_plan_anchor_score(text) IS
  'Deterministic 1-10 anchor score for a plan, computed from its '
  'time-weighted compliance + stress hours over its governed interval. '
  'Iris''s plan_evaluate(outcome_score=) is expected within +/-2 of this.';

-- -----------------------------------------------------------------------------
-- 5. Backfill anchor_score for evaluated historical plans
-- -----------------------------------------------------------------------------
UPDATE plan_journal pj
   SET anchor_score = fn_plan_anchor_score(pj.plan_id)
 WHERE pj.plan_id LIKE 'iris-%'
   AND pj.created_at >= '2026-04-10'
   AND pj.created_at < (now() - interval '24 hours')
   AND pj.anchor_score IS NULL;

COMMIT;
