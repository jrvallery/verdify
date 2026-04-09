-- Migration 041: Planning Architecture — predictive views for Iris
-- Addresses Iris's 10-point critique (2026-03-24):
--   #1  Plan-based compliance (not static schedule)
--   #2  Zone-aware extremes in planning context
--   #4  DLI forecast from Open-Meteo radiation data
--   #5  Water budget decomposition
--   #6  Cost rate constants in planning context
--   #8  Economiser status in planning context
--   #10 Plan accuracy feedback loop

-- ============================================================
-- 1. v_plan_compliance — Did the plan achieve its intent?
-- ============================================================

CREATE OR REPLACE VIEW v_plan_compliance AS
WITH plan_params AS (
  -- Map setpoint parameters to the climate column they affect
  SELECT ts AS planned_ts, parameter, value AS planned_value, plan_id, reason,
    CASE parameter
      WHEN 'temp_low' THEN 'temp_floor'
      WHEN 'temp_high' THEN 'temp_ceiling'
      WHEN 'vpd_low' THEN 'vpd_floor'
      WHEN 'vpd_high' THEN 'vpd_ceiling'
      WHEN 'mister_engage_kpa' THEN 'mister_threshold'
      WHEN 'mister_all_kpa' THEN 'mister_all_threshold'
      ELSE NULL
    END AS target_type
  FROM setpoint_plan
  WHERE parameter IN ('temp_low', 'temp_high', 'vpd_low', 'vpd_high', 'mister_engage_kpa', 'mister_all_kpa')
  AND ts < now()
),
climate_at_plan AS (
  SELECT
    pp.*,
    CASE pp.target_type
      WHEN 'temp_ceiling' THEN (SELECT MAX(temp_avg) FROM climate WHERE ts BETWEEN pp.planned_ts AND pp.planned_ts + interval '1 hour' AND temp_avg IS NOT NULL)
      WHEN 'temp_floor' THEN (SELECT MIN(temp_avg) FROM climate WHERE ts BETWEEN pp.planned_ts AND pp.planned_ts + interval '1 hour' AND temp_avg IS NOT NULL)
      WHEN 'vpd_ceiling' THEN (SELECT MAX(vpd_avg) FROM climate WHERE ts BETWEEN pp.planned_ts AND pp.planned_ts + interval '1 hour' AND vpd_avg IS NOT NULL)
      WHEN 'vpd_floor' THEN (SELECT MIN(vpd_avg) FROM climate WHERE ts BETWEEN pp.planned_ts AND pp.planned_ts + interval '1 hour' AND vpd_avg IS NOT NULL)
    END AS actual_extreme
  FROM plan_params pp
  WHERE pp.target_type IS NOT NULL
)
SELECT
  planned_ts,
  parameter,
  planned_value,
  target_type,
  ROUND(actual_extreme::numeric, 1) AS actual_extreme,
  CASE target_type
    WHEN 'temp_ceiling' THEN actual_extreme <= planned_value
    WHEN 'temp_floor' THEN actual_extreme >= planned_value
    WHEN 'vpd_ceiling' THEN actual_extreme <= planned_value
    WHEN 'vpd_floor' THEN actual_extreme >= planned_value
    ELSE NULL
  END AS plan_achieved,
  ROUND((actual_extreme - planned_value)::numeric, 2) AS overshoot,
  plan_id,
  reason
FROM climate_at_plan
WHERE actual_extreme IS NOT NULL;

COMMENT ON VIEW v_plan_compliance IS 'Compares Iris plan waypoints against actual climate extremes. plan_achieved=true means the plan intent held. overshoot shows by how much it missed.';

-- ============================================================
-- 2. v_plan_accuracy — Aggregate accuracy metrics per plan
-- ============================================================

CREATE OR REPLACE VIEW v_plan_accuracy AS
SELECT
  plan_id,
  COUNT(*) AS waypoints,
  COUNT(*) FILTER (WHERE plan_achieved) AS achieved,
  ROUND(100.0 * COUNT(*) FILTER (WHERE plan_achieved) / NULLIF(COUNT(*), 0), 1) AS accuracy_pct,
  ROUND(AVG(ABS(overshoot))::numeric, 2) AS mean_abs_error,
  MAX(overshoot) FILTER (WHERE target_type LIKE '%ceiling') AS worst_ceiling_overshoot,
  MIN(overshoot) FILTER (WHERE target_type LIKE '%floor') AS worst_floor_undershoot,
  MIN(planned_ts) AS plan_start,
  MAX(planned_ts) AS plan_end
FROM v_plan_compliance
GROUP BY plan_id;

COMMENT ON VIEW v_plan_accuracy IS 'Per-plan accuracy summary. accuracy_pct = % of waypoints where the plan intent was achieved.';

-- ============================================================
-- 3. v_water_budget — Daily water decomposition
-- ============================================================

CREATE OR REPLACE VIEW v_water_budget AS
SELECT
  ds.date,
  ds.water_used_gal AS total_gal,
  ds.mister_water_gal AS mister_gal,
  -- Drip estimated from equipment_state durations
  COALESCE(drip.wall_gal, 0) + COALESCE(drip.center_gal, 0) AS drip_gal,
  -- Unaccounted = total - misters - drip
  ds.water_used_gal
    - COALESCE(ds.mister_water_gal, 0)
    - COALESCE(drip.wall_gal, 0)
    - COALESCE(drip.center_gal, 0) AS unaccounted_gal,
  -- Efficiency: gallons per VPD stress hour avoided
  CASE WHEN ds.stress_hours_vpd_high > 0
    THEN ROUND((COALESCE(ds.mister_water_gal, 0) / ds.stress_hours_vpd_high)::numeric, 1)
  END AS gal_per_vpd_stress_hour
FROM daily_summary ds
LEFT JOIN LATERAL (
  -- Estimate drip water from runtime (assume 2 GPM flow rate for drip)
  SELECT
    ds.runtime_drip_wall_h * 60 * 2.0 AS wall_gal,
    ds.runtime_drip_center_h * 60 * 2.0 AS center_gal
) drip ON true
WHERE ds.water_used_gal IS NOT NULL AND ds.water_used_gal > 0;

COMMENT ON VIEW v_water_budget IS 'Daily water decomposition: mister vs drip vs unaccounted. Includes efficiency metric (gal/VPD stress hour).';

-- ============================================================
-- 4. fn_forecast_dli — Predict natural DLI from forecast
-- ============================================================

CREATE OR REPLACE FUNCTION fn_forecast_dli(target_date date DEFAULT CURRENT_DATE + 1)
RETURNS TABLE(
  predicted_dli numeric,
  gl_hours_needed numeric,
  recommended_gl_start int,
  recommended_gl_end int
) AS $$
DECLARE
  POLY_DIRECT_TRANSMISSION CONSTANT float := 0.20;   -- frosted polycarbonate direct
  POLY_DIFFUSE_TRANSMISSION CONSTANT float := 0.25;   -- frosted polycarbonate diffuse
  UMOL_PER_W CONSTANT float := 2.02;                  -- PAR conversion (W/m² → µmol/m²/s)
  ACHIEVABLE_DLI_TARGET CONSTANT float := 10.0;       -- realistic target (not 14)
  GL_DLI_PER_HOUR CONSTANT float := 1.15;             -- grow light contribution (mol/m²/d per hour)
  -- Shadow window: house blocks before 11 AM local, trees block after 4 PM local
  SHADOW_START CONSTANT int := 11;  -- hour (local) house shadow clears
  SHADOW_END CONSTANT int := 16;    -- hour (local) tree shadow starts
BEGIN
  RETURN QUERY
  WITH hourly AS (
    SELECT DISTINCT ON (f.ts)
      EXTRACT(HOUR FROM f.ts AT TIME ZONE 'America/Denver')::int AS local_hour,
      f.direct_radiation_w_m2,
      f.diffuse_radiation_w_m2,
      f.sunshine_duration_s,
      -- Shadow factor: 0 if blocked, 1 if clear, partial for transition hours
      CASE
        WHEN EXTRACT(HOUR FROM f.ts AT TIME ZONE 'America/Denver') < SHADOW_START THEN 0.1  -- house shadow
        WHEN EXTRACT(HOUR FROM f.ts AT TIME ZONE 'America/Denver') >= SHADOW_END THEN 0.1   -- tree shadow
        ELSE 1.0  -- clear window
      END AS shadow_factor
    FROM weather_forecast f
    WHERE f.ts::date = target_date
    AND f.direct_radiation_w_m2 IS NOT NULL
    ORDER BY f.ts, f.fetched_at DESC
  ),
  dli_calc AS (
    SELECT SUM(
      (
        COALESCE(direct_radiation_w_m2, 0) * POLY_DIRECT_TRANSMISSION * shadow_factor
        + COALESCE(diffuse_radiation_w_m2, 0) * POLY_DIFFUSE_TRANSMISSION
      ) * UMOL_PER_W  -- µmol/m²/s indoor
      * COALESCE(sunshine_duration_s, 3600) / 1e6  -- convert to mol for this hour
    ) AS natural_dli
    FROM hourly
    WHERE direct_radiation_w_m2 > 0 OR diffuse_radiation_w_m2 > 0
  )
  SELECT
    ROUND(dc.natural_dli::numeric, 1) AS predicted_dli,
    ROUND(GREATEST(0, (ACHIEVABLE_DLI_TARGET - dc.natural_dli) / GL_DLI_PER_HOUR)::numeric, 1) AS gl_hours_needed,
    -- Recommend grow lights before shadow clears (morning fill) and after shadow falls (evening extend)
    7 AS recommended_gl_start,  -- 7 AM (before 11 AM shadow clear)
    19 AS recommended_gl_end    -- 7 PM (after 4 PM shadow fall)
  FROM dli_calc dc;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION fn_forecast_dli(date) IS 'Predict natural DLI from Open-Meteo forecast. Accounts for polycarbonate transmission (20% direct, 25% diffuse) and house/tree shadow window (11AM-4PM clear). Returns predicted DLI + grow light hours needed to reach 10 mol/m²/d.';

-- ============================================================
-- 5. Rebuild v_iris_planning_context with new fields
-- ============================================================

DROP VIEW IF EXISTS v_iris_planning_context CASCADE;

CREATE OR REPLACE VIEW v_iris_planning_context AS
SELECT
  now() AS query_ts,

  -- Current conditions (last hour average)
  (SELECT json_build_object(
    'temp_avg', ROUND(AVG(temp_avg)::numeric, 1),
    'vpd_avg', ROUND(AVG(vpd_avg)::numeric, 2),
    'rh_avg', ROUND(AVG(rh_avg)::numeric, 1),
    'outdoor_temp_f', ROUND(AVG(outdoor_temp_f)::numeric, 1),
    'dli_today', ROUND(MAX(dli_today)::numeric, 2),
    'indoor_lux', ROUND(AVG(lux)::numeric, 0),
    'co2_ppm', ROUND(AVG(co2_ppm)::numeric, 0)
  ) FROM climate WHERE ts >= now() - interval '1 hour' AND temp_avg IS NOT NULL
  ) AS current_conditions,

  -- Zone extremes (last hour)
  (SELECT json_build_object(
    'north', ROUND(AVG(temp_north)::numeric, 1),
    'south', ROUND(AVG(temp_south)::numeric, 1),
    'east', ROUND(AVG(temp_east)::numeric, 1),
    'west', ROUND(AVG(temp_west)::numeric, 1),
    'hottest', GREATEST(AVG(temp_north), AVG(temp_south), AVG(temp_east), AVG(temp_west)),
    'coldest', LEAST(AVG(temp_north), AVG(temp_south), AVG(temp_east), AVG(temp_west)),
    'spread', ROUND((GREATEST(AVG(temp_north), AVG(temp_south), AVG(temp_east), AVG(temp_west))
              - LEAST(AVG(temp_north), AVG(temp_south), AVG(temp_east), AVG(temp_west)))::numeric, 1)
  ) FROM climate WHERE ts >= now() - interval '1 hour' AND temp_avg IS NOT NULL
  ) AS zone_context,

  -- Yesterday's summary
  (SELECT json_build_object(
    'date', date, 'cost_total', cost_total, 'dli_final', dli_final,
    'stress_hours_heat', stress_hours_heat, 'stress_hours_vpd_high', stress_hours_vpd_high,
    'water_used_gal', water_used_gal, 'kwh_estimated', kwh_estimated
  ) FROM daily_summary ORDER BY date DESC LIMIT 1
  ) AS yesterday_summary,

  -- 48h forecast (latest per hour, key params)
  (SELECT json_agg(row_to_json(sub) ORDER BY sub.ts)
   FROM (
     SELECT DISTINCT ON (ts) ts, temp_f, rh_pct, vpd_kpa, solar_w_m2,
       direct_radiation_w_m2, diffuse_radiation_w_m2, cloud_cover_pct,
       precip_prob_pct, wind_gust_mph, weather_code, sunshine_duration_s, et0_mm,
       dew_point_f, soil_temp_f, uv_index
     FROM weather_forecast
     WHERE ts BETWEEN now() AND now() + interval '48 hours'
     ORDER BY ts, fetched_at DESC
   ) sub
  ) AS forecast_48h,

  -- DLI forecast for tomorrow
  (SELECT json_build_object(
    'predicted_dli', predicted_dli,
    'gl_hours_needed', gl_hours_needed,
    'gl_start', recommended_gl_start,
    'gl_end', recommended_gl_end
  ) FROM fn_forecast_dli(CURRENT_DATE + 1)
  ) AS dli_forecast,

  -- Current setpoints
  (SELECT json_object_agg(parameter, value)
   FROM (SELECT DISTINCT ON (parameter) parameter, value FROM setpoint_changes ORDER BY parameter, ts DESC) sub
  ) AS current_setpoints,

  -- Active plan
  (SELECT json_agg(row_to_json(sub) ORDER BY sub.ts)
   FROM (
     SELECT ts, parameter, value, reason
     FROM setpoint_plan WHERE ts > now() AND parameter != 'plan_metadata'
     ORDER BY ts
   ) sub
  ) AS active_plan,

  -- Last plan accuracy
  (SELECT json_build_object(
    'plan_id', plan_id,
    'waypoints', waypoints,
    'achieved', achieved,
    'accuracy_pct', accuracy_pct,
    'mean_abs_error', mean_abs_error
  ) FROM v_plan_accuracy ORDER BY plan_start DESC LIMIT 1
  ) AS last_plan_accuracy,

  -- System health
  (SELECT json_build_object(
    'composite_score', fn_system_health(),
    'components', (SELECT json_agg(json_build_object('component', component, 'score', score_pct)) FROM v_system_health_score)
  )) AS system_health,

  -- Cost rates (simple constants — upgrade to TOU later)
  (SELECT json_build_object(
    'electric_per_kwh', 0.105,
    'gas_per_therm', 1.20,
    'water_per_gal', 0.007
  )) AS cost_rates,

  -- 7-day cost trend
  (SELECT json_agg(row_to_json(sub) ORDER BY sub.date)
   FROM (
     SELECT date, cost_total, kwh_estimated, water_used_gal,
       stress_hours_vpd_high, dli_final
     FROM daily_summary WHERE date >= CURRENT_DATE - 7 ORDER BY date
   ) sub
  ) AS cost_trend_7d;

COMMENT ON VIEW v_iris_planning_context IS 'Single-query planning context for Iris. v3: adds zone_context, dli_forecast, last_plan_accuracy, cost_rates.';
