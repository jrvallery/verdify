#!/usr/bin/env bash
# validate-plan-coverage.sh — Verify all 24 Tier 1 params present at every transition
set -uo pipefail

DB="docker exec verdify-timescaledb psql -U verdify -d verdify -t -A -c"

# All 24 Tier 1 params the planner must emit at every transition
CORE="vpd_hysteresis,vpd_watch_dwell_s,mister_engage_kpa,mister_all_kpa,mister_pulse_on_s,mister_pulse_gap_s,mister_vpd_weight,mister_water_budget_gal,mist_vent_close_lead_s,mist_max_closed_vent_s,mist_vent_reopen_delay_s,mist_thermal_relief_s,enthalpy_open,enthalpy_close,min_vent_on_s,min_vent_off_s,min_fog_on_s,min_fog_off_s,fog_escalation_kpa,d_cool_stage_2,bias_heat,bias_cool,min_heat_on_s,min_heat_off_s"

# 1. Get latest plan_id
LATEST=$($DB "SELECT plan_id FROM setpoint_plan WHERE is_active = true ORDER BY created_at DESC LIMIT 1;" 2>/dev/null | tr -d ' ')

if [ -z "$LATEST" ]; then
    echo "WARN: No active plans found"
    exit 1
fi

# 2. For each distinct timestamp, check all 24 Tier 1 params exist
RESULT=$($DB "
WITH core(param) AS (
  VALUES ('vpd_hysteresis'),('vpd_watch_dwell_s'),('mister_engage_kpa'),('mister_all_kpa'),
         ('mister_pulse_on_s'),('mister_pulse_gap_s'),('mister_vpd_weight'),('mister_water_budget_gal'),
         ('mist_vent_close_lead_s'),('mist_max_closed_vent_s'),('mist_vent_reopen_delay_s'),('mist_thermal_relief_s'),
         ('enthalpy_open'),('enthalpy_close'),('min_vent_on_s'),('min_vent_off_s'),
         ('min_fog_on_s'),('min_fog_off_s'),('fog_escalation_kpa'),
         ('d_cool_stage_2'),('bias_heat'),('bias_cool'),('min_heat_on_s'),('min_heat_off_s')
),
plan_ts AS (
  SELECT DISTINCT ts FROM setpoint_plan WHERE plan_id = '$LATEST'
),
expected AS (
  SELECT pt.ts, c.param FROM plan_ts pt CROSS JOIN core c
),
actual AS (
  SELECT ts, parameter FROM setpoint_plan WHERE plan_id = '$LATEST'
),
missing AS (
  SELECT e.ts, e.param
  FROM expected e
  LEFT JOIN actual a ON e.ts = a.ts AND e.param = a.parameter
  WHERE a.parameter IS NULL
)
SELECT
  (SELECT count(DISTINCT ts) FROM plan_ts),
  (SELECT count(DISTINCT ts) FROM plan_ts) - (SELECT count(DISTINCT ts) FROM missing),
  coalesce((SELECT string_agg(param || ' @ ' || to_char(ts AT TIME ZONE 'America/Denver', 'MM-DD HH:MI AM'), '; ' ORDER BY ts, param) FROM missing), '');
" 2>/dev/null)

TRANSITIONS=$(echo "$RESULT" | cut -d'|' -f1 | tr -d ' ')
COMPLETE=$(echo "$RESULT" | cut -d'|' -f2 | tr -d ' ')
MISSING_LIST=$(echo "$RESULT" | cut -d'|' -f3)

echo "plan_id: $LATEST"
echo "transitions: ${TRANSITIONS:-0}"
echo "complete: ${COMPLETE:-0}"

if [ -n "$MISSING_LIST" ]; then
    echo "MISSING: $MISSING_LIST"
    exit 1
else
    echo "All transitions have full coverage of 10 core params."
    exit 0
fi
