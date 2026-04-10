#!/bin/bash
# gather-plan-context.sh — Collect ALL data for Iris setpoint planning
# Uses v_iris_planning_context (single DB-side view) + supplementary queries
# Covers: conditions, zones, setpoints, plan, forecast, stress, compliance,
#         equipment, DIF, irrigation, hydro, DLI, energy, disease, crops, occupancy
set -euo pipefail

# Greenhouse ID: from arg or default
GREENHOUSE_ID="${1:-vallery}"
if [ "$1" = "--greenhouse-id" ] && [ -n "${2:-}" ]; then
    GREENHOUSE_ID="$2"
fi

DB="docker exec verdify-timescaledb psql -U verdify -d verdify -t -A"
HA_TOKEN=$(cat /mnt/jason/agents/shared/credentials/ha_token.txt 2>/dev/null || echo "")
HA_URL="http://192.168.30.107:8123"

echo "=== GREENHOUSE PLANNING CONTEXT ==="
echo "Greenhouse: $GREENHOUSE_ID"
echo "Generated: $(date -u '+%Y-%m-%dT%H:%M:%SZ') ($(date '+%Y-%m-%d %H:%M %Z'))"
echo ""

# ── 1. CORE PLANNING VIEW (7 JSON columns in one query) ───────────
echo "--- IRIS PLANNING CONTEXT (DB view) ---"
# Core view — conditions, zones, setpoints, health, summary (exclude bloated active_plan)
$DB -c "
SELECT json_build_object(
  'conditions', (SELECT row_to_json(v)->'conditions' FROM v_iris_planning_context v),
  'zones', (SELECT row_to_json(v)->'zones' FROM v_iris_planning_context v),
  'setpoints', (SELECT row_to_json(v)->'setpoints' FROM v_iris_planning_context v),
  'system_health', (SELECT row_to_json(v)->'system_health' FROM v_iris_planning_context v),
  'daily_summary', (SELECT row_to_json(v)->'daily_summary' FROM v_iris_planning_context v)
);" 2>/dev/null
echo ""

# Active plan: compact transition summary (grouped by timestamp, Tier 1 only)
echo "--- ACTIVE PLAN (transitions) ---"
echo "ts_mdt|plan_id|engage_kpa|all_kpa|pulse_gap|vpd_weight|hysteresis|d_cool_s2|bias_heat|bias_cool"
$DB -c "
WITH deduped AS (
  SELECT DISTINCT ON (ts, parameter) ts, parameter, value, plan_id
  FROM setpoint_plan WHERE ts > now() AND parameter != 'plan_metadata'
  ORDER BY ts, parameter, created_at DESC
)
SELECT to_char(ts AT TIME ZONE 'America/Denver', 'Dy MM-DD HH:MI') AS ts_mdt,
  max(plan_id) AS plan_id,
  max(CASE WHEN parameter='mister_engage_kpa' THEN value END) AS engage,
  max(CASE WHEN parameter='mister_all_kpa' THEN value END) AS all_kpa,
  max(CASE WHEN parameter='mister_pulse_gap_s' THEN value END) AS gap,
  max(CASE WHEN parameter='mister_vpd_weight' THEN value END) AS weight,
  max(CASE WHEN parameter='vpd_hysteresis' THEN value END) AS hyst,
  max(CASE WHEN parameter='d_cool_stage_2' THEN value END) AS d_cool,
  max(CASE WHEN parameter='bias_heat_f' THEN value END) AS b_heat,
  max(CASE WHEN parameter='bias_cool_f' THEN value END) AS b_cool
FROM deduped
GROUP BY ts
ORDER BY ts;
" 2>/dev/null || echo "(no active plan)"
echo ""

# ── 2. CURRENT ZONE-LEVEL CONDITIONS ──────────────────────────────
echo "--- ZONE CONDITIONS ---"
$DB -c "
SELECT json_build_object(
  'ts', ts,
  'temp_south', round(temp_south::numeric,1), 'temp_north', round(temp_north::numeric,1),
  'temp_east', round(temp_east::numeric,1), 'temp_west', round(temp_west::numeric,1),
  'vpd_south', round(vpd_south::numeric,2), 'vpd_north', round(vpd_north::numeric,2),
  'vpd_east', round(vpd_east::numeric,2), 'vpd_west', round(vpd_west::numeric,2),
  'rh_south', round(rh_south::numeric,1), 'rh_north', round(rh_north::numeric,1),
  'rh_east', round(rh_east::numeric,1), 'rh_west', round(rh_west::numeric,1),
  'outdoor_temp_f', round(outdoor_temp_f::numeric,1), 'outdoor_rh_pct', round(outdoor_rh_pct::numeric,1),
  'outdoor_lux', outdoor_lux, 'solar_irradiance_w_m2', round(solar_irradiance_w_m2::numeric,0),
  'enthalpy_delta', round(enthalpy_delta::numeric,2),
  'dew_point', round(dew_point::numeric,1), 'abs_humidity', round(abs_humidity::numeric,1),
  'flow_gpm', round(flow_gpm::numeric,2), 'water_total_gal', round(water_total_gal::numeric,0)
) FROM climate ORDER BY ts DESC LIMIT 1;
"
# Dynamic zone ranking with context
$DB -c "SELECT 'ZONE VPD (current): ' || string_agg(z || '=' || v, ', ' ORDER BY v DESC)
FROM (SELECT unnest(ARRAY['north','south','east','west']) AS z,
      unnest(ARRAY[round(vpd_north::numeric,2), round(vpd_south::numeric,2),
                    round(vpd_east::numeric,2), round(vpd_west::numeric,2)]) AS v
      FROM climate ORDER BY ts DESC LIMIT 1) ranked;" 2>/dev/null
echo "NOTE: North reads driest overnight (equipment zone). Daytime misting priority: south first (6 heads, 0.23 kPa/pulse), west second (3 heads, 0.15 kPa/pulse)."
echo ""

# ── 3. GREENHOUSE STATE + SWITCHES (from HA or DB) ──────────────
ESP_STATE=$($DB -c "SELECT value FROM system_state WHERE entity = 'greenhouse_state' ORDER BY ts DESC LIMIT 1;" 2>/dev/null | tr -d ' ')
if [ -n "$ESP_STATE" ] && [ "$ESP_STATE" != "" ]; then
  echo "--- ESP32 STATE ---"
  echo "state: $ESP_STATE"
  echo ""
fi

# ── 4. 24H HOURLY CLIMATE PATTERN ─────────────────────────────────
echo "--- 24H HOURLY PATTERN ---"
echo "hour|temp_f|rh_pct|vpd_kpa|co2_ppm|peak_lux"
$DB -c "
SELECT to_char(date_trunc('hour', ts) AT TIME ZONE 'America/Denver', 'HH:MI AM') as hour,
  round(avg(temp_avg)::numeric,1) as temp_f, round(avg(rh_avg)::numeric,1) as rh,
  round(avg(vpd_avg)::numeric,2) as vpd, round(avg(co2_ppm)::numeric,0) as co2,
  round(max(lux)::numeric,0) as peak_lux
FROM climate WHERE ts > now() - interval '24 hours'
GROUP BY 1, date_trunc('hour', ts)
ORDER BY date_trunc('hour', ts);
"
echo ""

# ── 5. STRESS LAST 7 DAYS ─────────────────────────────────────────
echo "--- STRESS LAST 7 DAYS ---"
echo "date|cold_stress_hrs|heat_stress_hrs|vpd_high_hrs|vpd_low_hrs"
$DB -c "
SELECT date, cold_stress_hours, heat_stress_hours, vpd_stress_hours, vpd_low_hours
FROM v_stress_hours_today WHERE date >= CURRENT_DATE - 6 ORDER BY date DESC;
"
echo ""

# ── 6. COMPLIANCE (24h by zone) ───────────────────────────────────
echo "--- COMPLIANCE (24h by zone) ---"
echo "zone|in_band_pct|above_pct|below_pct|na_pct"
$DB -c "SELECT * FROM fn_compliance_pct('24 hours'::interval);"
echo ""

# ── 7. DIF (day/night temperature differential, 7 days) ──────────
echo "--- DIF (7 days) ---"
echo "day|day_avg_f|night_avg_f|dif_f"
$DB -c "
SELECT to_char(date, 'MM-DD') as day, round(day_avg_temp::numeric,1) as day_f,
  round(night_avg_temp::numeric,1) as night_f, round(dif::numeric,1) as dif_f
FROM v_dif WHERE date >= CURRENT_DATE - 6 ORDER BY date DESC;
"
echo ""

# ── 8. HYDROPONIC SYSTEM ──────────────────────────────────────────
echo "--- HYDROPONIC SYSTEM (East Zone) ---"
echo "ph|ec_us_cm|tds_ppm|water_temp_f|orp_mv|battery_pct"
$DB -c "
SELECT round(hydro_ph::numeric,2) as ph, round(hydro_ec_us_cm::numeric,0) as ec_us,
  round(hydro_tds_ppm::numeric,0) as tds, round(hydro_water_temp_f::numeric,1) as water_f,
  round(hydro_orp_mv::numeric,0) as orp, hydro_battery_pct as batt
FROM climate WHERE hydro_ph IS NOT NULL ORDER BY ts DESC LIMIT 1;
"
echo ""

# ── 9. EQUIPMENT RUNTIME 24H ──────────────────────────────────────
echo "--- EQUIPMENT RUNTIME 24H ---"
echo "equipment|on_hours|transitions"
$DB -c "
SELECT equipment,
  round(sum(CASE WHEN state NOT IN ('f','off','false') THEN extract(epoch from coalesce(lead_ts - ts, interval '0')) END)::numeric/3600, 2) as on_hours,
  count(*) as transitions
FROM (SELECT *, lead(ts) OVER (PARTITION BY equipment ORDER BY ts) as lead_ts
      FROM equipment_state WHERE ts > now() - interval '24 hours') sub
WHERE equipment IN ('vent','fan1','fan2','fog','mister_south','mister_west','mister_center',
  'heat1','heat2','drip_wall','grow_light_main','grow_light_grow','water_flowing')
GROUP BY equipment
HAVING count(*) > 1
ORDER BY on_hours DESC NULLS LAST;
"
echo ""

# ── 10. ENERGY CONSUMPTION 24H ────────────────────────────────────
echo "--- ENERGY 24H ---"
echo "kwh_today|avg_watts|peak_watts|avg_heat_watts"
$DB -c "
SELECT round(max(kwh_today)::numeric, 1) as kwh_today,
  round(avg(watts_total)::numeric, 0) as avg_watts,
  round(max(watts_total)::numeric, 0) as peak_watts,
  round(avg(watts_heat)::numeric, 0) as avg_heat_watts
FROM energy WHERE ts > now() - interval '24 hours';
"
echo ""

# ── 11. IRRIGATION ────────────────────────────────────────────────
echo "--- IRRIGATION SCHEDULE ---"
$DB -c "SELECT zone, start_time, duration_s, days_of_week, enabled FROM irrigation_schedule ORDER BY zone;"
echo ""
echo "--- IRRIGATION HISTORY (7 days) ---"
$DB -c "
SELECT to_char(ts AT TIME ZONE 'America/Denver', 'MM-DD HH:MI') as mdt, zone, source
FROM irrigation_log WHERE ts > now() - interval '7 days' ORDER BY ts DESC LIMIT 10;
" 2>/dev/null || echo "(none)"
echo ""

# ── 12. DLI + GROW LIGHTS ─────────────────────────────────────────
echo "--- DLI + GROW LIGHTS ---"
$DB -c "
SELECT round(dli_today::numeric,1) as dli_mol, round(lux::numeric,0) as lux_now
FROM climate ORDER BY ts DESC LIMIT 1;
"
echo "DLI last 7 days:"
$DB -c "
SELECT to_char(date_trunc('day', ts)::date, 'MM-DD') as day, round(max(dli_today)::numeric,1) as peak_dli
FROM climate WHERE ts > now() - interval '7 days' GROUP BY 1 ORDER BY 1;
"
echo ""
echo "DLI CORRECTION (estimated actual plant DLI):"
SENSOR_DLI=$($DB -c "SELECT round(COALESCE(max(dli_today), 0)::numeric, 1) FROM climate WHERE ts >= date_trunc('day', now() AT TIME ZONE 'America/Denver');" 2>/dev/null)
GL_HOURS=$($DB -c "SELECT round(COALESCE(runtime_grow_light_min, 0)::numeric / 60, 1) FROM daily_summary ORDER BY date DESC LIMIT 1;" 2>/dev/null)
SENSOR_DLI=${SENSOR_DLI:-0}
GL_HOURS=${GL_HOURS:-0}
python3 -c "s=${SENSOR_DLI};g=${GL_HOURS};print(f'sensor_dli={s} | estimated_actual_dli={s*3.5:.1f} | gl_hours={g} | estimated_total_plant_dli={s*3.5+g*0.8:.1f}')" 2>/dev/null || echo "sensor_dli=${SENSOR_DLI} | gl_hours=${GL_HOURS}"
echo "SENSOR LIMITATION: The lux sensor reads 25-40% of actual plant-available light."
echo "Sensor DLI of 5-7 mol corresponds to actual plant DLI of 17-27 mol."
echo "Do NOT react to low sensor DLI as if plants are light-starved."
echo "Grow light automation (gl_auto_mode) works by accident -- the 3000 lux threshold"
echo "correlates with tree shadow clearing, not actual light adequacy."
echo ""

# ── 13. DISEASE RISK ──────────────────────────────────────────────
echo "--- DISEASE RISK (last 6h) ---"
$DB -c "SELECT * FROM v_disease_risk ORDER BY hour DESC LIMIT 6;" 2>/dev/null || echo "(n/a)"
echo ""

# ── 14. ACTIVE CROPS ──────────────────────────────────────────────
echo "--- ACTIVE CROPS ---"
$DB -c "
SELECT name, variety, position, zone, stage, planted_date
FROM crops WHERE is_active ORDER BY zone, position;
" 2>/dev/null || echo "(none)"
echo ""

# ── 15. PREVIOUS PLAN REVIEW (hypothesis → outcome validation) ────
echo "--- PREVIOUS PLAN REVIEW ---"
$DB -c "
SELECT pj.plan_id,
  to_char(pj.created_at AT TIME ZONE 'America/Denver', 'MM-DD HH:MI AM') AS planned_at,
  pj.hypothesis,
  pj.experiment,
  pj.expected_outcome,
  pj.actual_outcome,
  pj.outcome_score,
  pj.lesson_extracted,
  CASE WHEN pj.validated_at IS NULL THEN '⚠ NEEDS VALIDATION' ELSE 'validated' END AS status
FROM plan_journal pj
WHERE pj.plan_id NOT LIKE 'iris-reactive%'
ORDER BY pj.created_at DESC LIMIT 1;
" 2>/dev/null
# Show accuracy for last 3 plans
echo "Plan accuracy (last 3):"
$DB -c "SELECT plan_id, waypoints, achieved, accuracy_pct, mean_abs_error FROM v_plan_accuracy WHERE plan_id NOT LIKE 'iris-reactive%' ORDER BY plan_start DESC LIMIT 3;" 2>/dev/null
# Flag unvalidated plans
UNVALIDATED=$($DB -c "SELECT COUNT(*) FROM plan_journal WHERE validated_at IS NULL AND plan_id NOT LIKE 'iris-reactive%' AND created_at < now() - interval '6 hours';" 2>/dev/null | tr -d ' ')
if [ "${UNVALIDATED:-0}" -gt 0 ]; then
  echo "ACTION REQUIRED: $UNVALIDATED unvalidated plan(s). Score the previous plan before writing a new one."
fi
# Structured actuals for previous plan period (stress, water, cost, equipment)
echo "Previous plan actuals (measured outcomes since yesterday):"
echo "metric|value"
$DB -c "
SELECT 'heat_stress_hrs' AS metric, round(COALESCE(sum(heat_stress_hours),0)::numeric, 1) AS val
FROM v_stress_hours_today WHERE date >= CURRENT_DATE - 1
UNION ALL SELECT 'vpd_stress_hrs', round(COALESCE(sum(vpd_stress_hours),0)::numeric, 1)
FROM v_stress_hours_today WHERE date >= CURRENT_DATE - 1
UNION ALL SELECT 'water_used_gal', round(COALESCE(sum(water_used_gal),0)::numeric, 1)
FROM daily_summary WHERE date >= CURRENT_DATE - 1
UNION ALL SELECT 'cost_total', round(COALESCE(sum(cost_total),0)::numeric, 2)
FROM daily_summary WHERE date >= CURRENT_DATE - 1
UNION ALL SELECT 'peak_temp_f', round(COALESCE(max(temp_max),0)::numeric, 1)
FROM daily_summary WHERE date >= CURRENT_DATE - 1
UNION ALL SELECT 'peak_vpd_kpa', round(COALESCE(max(vpd_max),0)::numeric, 2)
FROM daily_summary WHERE date >= CURRENT_DATE - 1;
" 2>/dev/null || echo "(unavailable)"
# Recent setpoint changes (what the dispatcher actually pushed)
echo "Recent dispatched changes (24h):"
echo "time_mdt|parameter|value|source"
$DB -c "
SELECT to_char(ts AT TIME ZONE 'America/Denver', 'MM-DD HH:MI AM') as mdt,
  parameter, round(value::numeric,2), source
FROM setpoint_changes
WHERE source = 'plan' AND ts > now() - interval '24 hours'
ORDER BY ts DESC LIMIT 10;
" 2>/dev/null || echo "(none)"
echo ""

# ── 16. WATER USAGE TREND ─────────────────────────────────────────
echo "--- WATER (7 days) ---"
$DB -c "
SELECT to_char(day, 'MM-DD') as day, used_gal FROM v_water_daily
WHERE day >= CURRENT_DATE - 6 ORDER BY day;
"
echo "NOTE: Water meter measures total downstream usage (greenhouse + sink + hose). Misting-only water is tracked separately via mister_water_today on ESP32."
echo ""

# ── 17. OCCUPANCY ─────────────────────────────────────────────────
echo "--- OCCUPANCY ---"
$DB -c "
SELECT to_char(ts AT TIME ZONE 'America/Denver', 'HH:MI AM') as time, value as state
FROM system_state WHERE entity = 'occupancy' AND ts > now() - interval '12 hours'
ORDER BY ts DESC LIMIT 5;
" 2>/dev/null || echo "(n/a)"
echo ""

# ── 18. ESP32 FIRMWARE MIN/MAX CONSTRAINTS ────────────────────────
echo "--- TUNABLE CONSTRAINTS (min/max/step) ---"
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
key_params = ['set_temp_low_degf','set_temp_high_degf','set_vpd_low_kpa','set_vpd_high_kpa',
  'vpd_mister_engage_kpa','vpd_mister_all_kpa','mister_water_budget_gal',
  'gl_dli_target_mol','gl_lux_threshold','irrig_wall_duration_min']
for e in data:
    eid = e['entity_id']
    if eid.startswith('number.greenhouse_'):
        name = eid.replace('number.greenhouse_','')
        if name in key_params:
            a = e.get('attributes',{})
            print(f\"{name}: val={e['state']} min={a.get('min')} max={a.get('max')} step={a.get('step')}\")
" 2>/dev/null
echo ""

# ── 19. FORECAST BIAS (7-day rolling correction) ──────────────────
BIAS=$($DB -c "SELECT * FROM fn_forecast_correction('temp_f', 24);" 2>/dev/null)
if [ -n "$BIAS" ] && [ "$BIAS" != "" ]; then
  echo "--- FORECAST BIAS ---"
  echo "param|bias_f|window_hours"
  echo "$BIAS"
  echo ""
fi

# ── 20. ACTIVE LESSONS (accumulated planner knowledge) ────────────
echo "--- ACTIVE LESSONS ---"
$DB -c "
SELECT category, condition, lesson, confidence, times_validated
FROM planner_lessons
WHERE is_active = true AND superseded_by IS NULL
ORDER BY
  CASE confidence WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
  times_validated DESC;
" 2>/dev/null
echo "When making decisions, reference applicable lessons above. If a lesson contradicts"
echo "your plan, either follow the lesson or explain why conditions differ enough to override."
echo ""

# ── 20b. CURRENT ACTIVE SETPOINTS (for mandatory waypoint emission) ─
echo "--- CURRENT ACTIVE SETPOINTS ---"
$DB -c "
SELECT parameter, value
FROM (SELECT DISTINCT ON (parameter) parameter, value FROM setpoint_changes ORDER BY parameter, ts DESC) sub
WHERE parameter IN ('temp_high','temp_low','vpd_high','vpd_low','vpd_hysteresis','mister_engage_kpa','mister_all_kpa','mister_pulse_on_s','mister_pulse_gap_s','gl_dli_target','gl_sunrise_hour','gl_sunset_hour')
ORDER BY parameter;
" 2>/dev/null
echo "These are the current active values. Band-driven params (temp_high, temp_low, vpd_high, vpd_low)"
echo "are computed from crop profiles every 5 min — do not set these in your plan."
echo ""

# ── 21. PLANNING GUIDANCE ──────────────────────────────────────────
echo "--- PLANNING GUIDANCE ---"
echo "VPD RAMP PATTERN: Historical data shows VPD increases ~60% between 9 AM and 1 PM on clear days."
echo "The mister_engage_kpa threshold (currently from plan) determines when misting starts."
echo "On days with forecast outdoor RH < 25% and clear skies, consider lowering mister_engage_kpa"
echo "to 1.3 in the morning plan (6 AM waypoint) and raising it back to 1.6 in the evening plan"
echo "(6 PM waypoint). This pre-conditions humidity before the steep VPD ramp."
echo ""

# ── 22. FORECAST ALERTS (proactive warnings for next 24-48h) ─────
echo "--- FORECAST ALERTS ---"
$DB -c "
WITH latest AS (
  SELECT ts, temp_f, rh_pct, cloud_cover_pct, precip_prob_pct,
         ROW_NUMBER() OVER (PARTITION BY ts ORDER BY fetched_at DESC) AS rn
  FROM weather_forecast
  WHERE ts > now() AND ts < now() + interval '48 hours'
),
fc AS (SELECT * FROM latest WHERE rn = 1),
today_high AS (
  SELECT MAX(temp_f) AS hi FROM fc WHERE ts < now() + interval '24 hours'
),
tomorrow_high AS (
  SELECT MAX(temp_f) AS hi FROM fc WHERE ts >= now() + interval '24 hours'
),
alerts AS (
  -- HEAT WARNING
  SELECT 1 AS ord, 'HEAT WARNING: forecast high ' || round(max_t::numeric,0) || '°F at '
    || to_char(peak_ts AT TIME ZONE 'America/Denver', 'HH:MI AM')
    || '. Consider lowering temp_high or extending mister window.' AS alert
  FROM (SELECT max(temp_f) AS max_t, (array_agg(ts ORDER BY temp_f DESC))[1] AS peak_ts FROM fc WHERE temp_f > 90) h
  WHERE h.max_t IS NOT NULL
  UNION ALL
  -- VPD WARNING (dry + hot)
  SELECT 2, 'VPD WARNING: dry conditions forecast (RH ' || round(min(rh_pct)::numeric,0) || '%, '
    || round(max(temp_f)::numeric,0) || '°F). Consider lowering mister_engage_kpa to 1.3.'
  FROM fc WHERE rh_pct < 20 AND temp_f > 75
  HAVING count(*) > 0
  UNION ALL
  -- FROST RISK
  SELECT 3, 'FROST RISK: forecast low ' || round(min_t::numeric,0) || '°F at '
    || to_char(low_ts AT TIME ZONE 'America/Denver', 'HH:MI AM')
    || '. Verify heaters operational, consider raising temp_low.'
  FROM (SELECT min(temp_f) AS min_t, (array_agg(ts ORDER BY temp_f ASC))[1] AS low_ts FROM fc WHERE temp_f < 35) c
  WHERE c.min_t IS NOT NULL
  UNION ALL
  -- OVERCAST / RAIN
  SELECT 4, 'OVERCAST/RAIN: avg cloud cover ' || round(avg(cloud_cover_pct)::numeric,0)
    || '%, precip prob ' || round(max(precip_prob_pct)::numeric,0)
    || '% tomorrow. DLI may be low (lighting handled by gl_auto_mode, not this planner).'
  FROM fc
  WHERE ts::date = (CURRENT_DATE + 1)
  HAVING avg(cloud_cover_pct) > 80 OR max(precip_prob_pct) > 60
  UNION ALL
  -- COLD FRONT
  SELECT 5, 'COLD FRONT: today high ' || round(th.hi::numeric,0) || '°F → tomorrow '
    || round(tmh.hi::numeric,0) || '°F (-' || round((th.hi - tmh.hi)::numeric,0)
    || '°F). Heaters will cycle heavily tonight.'
  FROM today_high th, tomorrow_high tmh
  WHERE th.hi - tmh.hi > 15
)
SELECT alert FROM alerts ORDER BY ord;
"
# If query returned nothing, show nominal
if [ $? -ne 0 ] || ! $DB -c "
WITH latest AS (
  SELECT ts, temp_f, rh_pct,
         ROW_NUMBER() OVER (PARTITION BY ts ORDER BY fetched_at DESC) AS rn
  FROM weather_forecast WHERE ts > now() AND ts < now() + interval '48 hours'
),
fc AS (SELECT * FROM latest WHERE rn = 1)
SELECT 1 FROM fc WHERE temp_f > 90 OR temp_f < 35 OR (rh_pct < 20 AND temp_f > 75) LIMIT 1;
" 2>/dev/null | grep -q 1; then
  echo "No forecast alerts — conditions nominal for next 48h."
fi
echo ""

# ── 23. EXPERIMENT TRACKER (recent hypotheses + outcomes) ─────────
echo "--- EXPERIMENT TRACKER ---"
echo "Latest pending:"
$DB -c "
SELECT plan_id, to_char(created_at AT TIME ZONE 'America/Denver', 'MM-DD HH:MI') AS date,
  COALESCE(experiment, '(none)') AS experiment
FROM plan_journal WHERE validated_at IS NULL AND plan_id NOT LIKE 'iris-reactive%'
ORDER BY created_at DESC LIMIT 1;
" 2>/dev/null || echo "(none pending)"
echo "Last completed:"
$DB -c "
SELECT plan_id, outcome_score, COALESCE(lesson_extracted, '(no lesson)') AS lesson
FROM plan_journal WHERE validated_at IS NOT NULL AND plan_id NOT LIKE 'iris-reactive%'
ORDER BY validated_at DESC LIMIT 1;
" 2>/dev/null || echo "(none completed)"
echo ""

# ── 22b. (moved to section 27) ───────────────────────────────────

# ── 23. REPLAN TRIGGER ───────────────────────────────────────────
echo "--- REPLAN TRIGGER ---"
if [ -f /srv/verdify/state/replan-needed.json ]; then
  echo "⚠️ DEVIATION-TRIGGERED REPLAN"
  cat /srv/verdify/state/replan-needed.json
  echo ""
  echo "The forecast was significantly wrong. Re-evaluate all waypoints against ACTUAL conditions."
else
  echo "Scheduled cycle — no deviation trigger."
fi
echo ""

# ── 23b. TRANSITION MILESTONES (computed from forecast + astronomy) ──
echo "--- TRANSITION MILESTONES (next 3 days) ---"
echo "date|sunrise|sunset|peak_solar|peak_temp|driest_hour|peak_vpd|cloud_shift|stress_hrs"
$DB -c "
WITH fc AS (
  SELECT DISTINCT ON (ts) ts,
    ts AT TIME ZONE 'America/Denver' AS mdt,
    (ts AT TIME ZONE 'America/Denver')::date AS day,
    extract(hour FROM ts AT TIME ZONE 'America/Denver') AS hr,
    temp_f, rh_pct, cloud_cover_pct, vpd_kpa,
    COALESCE(direct_radiation_w_m2, 0) AS solar_w
  FROM weather_forecast
  WHERE ts > now() AND ts < now() + interval '72 hours'
  ORDER BY ts, fetched_at DESC
),
daily AS (
  SELECT day,
    to_char(min(CASE WHEN solar_w > 10 THEN mdt END), 'HH24:MI') AS sunrise,
    to_char(max(CASE WHEN solar_w > 10 THEN mdt END), 'HH24:MI') AS sunset,
    to_char((array_agg(mdt ORDER BY solar_w DESC))[1], 'HH24:MI') AS peak_solar,
    to_char((array_agg(mdt ORDER BY temp_f DESC))[1], 'HH24:MI') AS peak_temp,
    to_char((array_agg(mdt ORDER BY rh_pct ASC))[1], 'HH24:MI') AS driest,
    to_char((array_agg(mdt ORDER BY vpd_kpa DESC))[1], 'HH24:MI') AS peak_vpd,
    count(*) FILTER (WHERE vpd_kpa > 1.5) || 'h' AS stress_hrs
  FROM fc GROUP BY day
)
SELECT to_char(day, 'Dy MM-DD'), sunrise, sunset, peak_solar, peak_temp, driest, peak_vpd,
  COALESCE((
    SELECT to_char(mdt, 'HH24:MI') || CASE
      WHEN cloud_cover_pct > lag_c THEN ' →cloud' ELSE ' →clear' END
    FROM (SELECT mdt, cloud_cover_pct, lag(cloud_cover_pct) OVER (ORDER BY ts) AS lag_c
          FROM fc f2 WHERE f2.day = d.day) cc
    WHERE abs(cloud_cover_pct - COALESCE(lag_c, cloud_cover_pct)) > 30
    ORDER BY mdt LIMIT 1
  ), 'none') AS cloud_shift,
  stress_hrs
FROM daily d ORDER BY day;
" 2>/dev/null || echo "(unavailable)"
echo "Anchor your transitions to these milestones — not fixed clock times."
echo ""

# ── 24. 72-HOUR HOURLY FORECAST ──────────────────────────────────
echo "--- 72H HOURLY FORECAST ---"
echo "hour_mdt|temp_f|rh_pct|cloud_pct|wind_mph|vpd_kpa|solar_w_m2|et0_mm|precip_prob_pct|weather_code"
$DB -c "
SELECT to_char(ts AT TIME ZONE 'America/Denver', 'Dy MM-DD HH24:00') as hour_mdt,
  round(temp_f::numeric,0) as temp_f,
  round(rh_pct::numeric,0) as rh,
  round(cloud_cover_pct::numeric,0) as cloud,
  round(wind_speed_mph::numeric,0) as wind,
  round(vpd_kpa::numeric,2) as vpd,
  round(COALESCE(direct_radiation_w_m2,0)::numeric,0) as solar_w,
  round(COALESCE(et0_mm,0)::numeric,1) as et0,
  round(COALESCE(precip_prob_pct,0)::numeric,0) as precip_pct,
  weather_code
FROM (
  SELECT DISTINCT ON (ts) * FROM weather_forecast
  WHERE ts > now() AND ts < now() + interval '72 hours'
  ORDER BY ts, fetched_at DESC
) fc
ORDER BY ts;
"
echo ""

# ── 25. DAYS 4-7 DAILY OUTLOOK ──────────────────────────────────
echo "--- DAYS 4-7 DAILY OUTLOOK ---"
$DB -c "
SELECT to_char(date_trunc('day', ts) AT TIME ZONE 'America/Denver', 'Dy MM-DD') as day,
  round(min(temp_f)::numeric,0) as low_f,
  round(max(temp_f)::numeric,0) as high_f,
  round(min(rh_pct)::numeric,0) as min_rh,
  round(avg(cloud_cover_pct)::numeric,0) as avg_cloud,
  round(max(precip_prob_pct)::numeric,0) as max_precip,
  round(avg(vpd_kpa)::numeric,2) as avg_vpd,
  round(sum(COALESCE(et0_mm,0))::numeric,1) as total_et0
FROM (
  SELECT DISTINCT ON (ts) * FROM weather_forecast
  WHERE ts >= now() + interval '72 hours' AND ts < now() + interval '7 days'
  ORDER BY ts, fetched_at DESC
) fc
GROUP BY date_trunc('day', ts)
ORDER BY date_trunc('day', ts);
"
echo "Use this coarse forecast for day-level planning posture (conservative defaults)."
echo ""

# ── 27. PLAN COVERAGE VALIDATION ─────────────────────────────────
echo "--- PLAN COVERAGE VALIDATION ---"
bash /srv/verdify/scripts/validate-plan-coverage.sh 2>/dev/null
echo ""

# ── 28. FORECAST ACCURACY ─────────────────────────────────────────
echo "--- FORECAST ACCURACY (7 days) ---"
$DB -c "SELECT * FROM v_forecast_accuracy_daily WHERE date >= CURRENT_DATE - 7 ORDER BY date DESC, param;"
echo "Use this to calibrate your trust in the forecast. If 48h accuracy is consistently worse than 24h, weight near-term forecasts more heavily."
echo ""

# ── 29. PLAN COMPARISON ───────────────────────────────────────────
echo "--- PLAN COMPARISON (vs previous) ---"
echo "parameter|current_avg|previous_avg|delta"
$DB -c "
SELECT parameter, round(cur_avg::numeric,2), round(prev_avg::numeric,2), round(delta_avg::numeric,2)
FROM v_plan_comparison
ORDER BY plan_created DESC, abs(delta_avg) DESC
LIMIT 10;
" 2>/dev/null || echo "(not available)"
echo ""

# ── 30. CROP HEALTH (Gemini Vision observations) ────────────────
echo "--- CROP HEALTH (latest visual observations) ---"
$DB -c "
SELECT to_char(ts AT TIME ZONE 'America/Denver', 'MM-DD HH:MI') AS observed,
  camera, zone, confidence,
  crops_observed::text
FROM image_observations
WHERE ts > now() - interval '48 hours'
ORDER BY ts DESC LIMIT 4;
" 2>/dev/null
echo ""
$DB -c "
SELECT to_char(ts AT TIME ZONE 'America/Denver', 'MM-DD HH:MI') AS observed,
  array_to_string(recommended_actions, '; ') AS actions
FROM image_observations
WHERE ts > now() - interval '24 hours'
ORDER BY ts DESC LIMIT 2;
" 2>/dev/null
echo "Use these visual observations to inform crop-specific decisions. If health scores are declining, investigate and adjust."
echo ""

echo "=== END PLANNING CONTEXT ==="
