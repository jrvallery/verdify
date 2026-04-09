-- Migration 042: Weekly and monthly summary views + arbitrary period function
-- Aggregates daily_summary into higher-level rollups for reporting and trending.

-- ============================================================
-- v_weekly_summary — ISO week aggregation
-- ============================================================

CREATE OR REPLACE VIEW v_weekly_summary AS
SELECT
  date_trunc('week', date)::date AS week_start,
  (date_trunc('week', date) + interval '6 days')::date AS week_end,
  count(*) AS days,

  -- Climate
  ROUND(AVG(temp_avg)::numeric, 1) AS temp_avg,
  ROUND(MIN(temp_min)::numeric, 1) AS temp_min,
  ROUND(MAX(temp_max)::numeric, 1) AS temp_max,
  ROUND(AVG(rh_avg)::numeric, 1) AS rh_avg,
  ROUND(MIN(rh_min)::numeric, 1) AS rh_min,
  ROUND(MAX(rh_max)::numeric, 1) AS rh_max,
  ROUND(AVG(vpd_avg)::numeric, 2) AS vpd_avg,
  ROUND(MIN(vpd_min)::numeric, 2) AS vpd_min,
  ROUND(MAX(vpd_max)::numeric, 2) AS vpd_max,
  ROUND(AVG(dli_final)::numeric, 1) AS dli_avg,
  ROUND(AVG(co2_avg)::numeric, 0) AS co2_avg,
  ROUND(MIN(outdoor_temp_min)::numeric, 1) AS outdoor_temp_min,
  ROUND(MAX(outdoor_temp_max)::numeric, 1) AS outdoor_temp_max,

  -- Stress (summed)
  ROUND(SUM(COALESCE(stress_hours_heat, 0))::numeric, 1) AS stress_hours_heat,
  ROUND(SUM(COALESCE(stress_hours_cold, 0))::numeric, 1) AS stress_hours_cold,
  ROUND(SUM(COALESCE(stress_hours_vpd_high, 0))::numeric, 1) AS stress_hours_vpd_high,
  ROUND(SUM(COALESCE(stress_hours_vpd_low, 0))::numeric, 1) AS stress_hours_vpd_low,

  -- Water
  ROUND(SUM(COALESCE(water_used_gal, 0))::numeric, 0) AS total_water_gal,
  ROUND(SUM(COALESCE(mister_water_gal, 0))::numeric, 0) AS mister_water_gal,

  -- Energy
  ROUND(SUM(COALESCE(kwh_estimated, 0))::numeric, 1) AS kwh_total,
  ROUND(SUM(COALESCE(therms_estimated, 0))::numeric, 2) AS therms_total,
  ROUND(MAX(COALESCE(peak_kw, 0))::numeric, 2) AS peak_kw,

  -- Cost
  ROUND(SUM(COALESCE(cost_electric, 0))::numeric, 2) AS cost_electric,
  ROUND(SUM(COALESCE(cost_gas, 0))::numeric, 2) AS cost_gas,
  ROUND(SUM(COALESCE(cost_water, 0))::numeric, 2) AS cost_water,
  ROUND(SUM(COALESCE(cost_total, 0))::numeric, 2) AS total_cost,

  -- Equipment runtimes (summed to hours)
  ROUND(SUM(COALESCE(runtime_heat1_min, 0))::numeric / 60, 1) AS runtime_heat1_h,
  ROUND(SUM(COALESCE(runtime_heat2_min, 0))::numeric / 60, 1) AS runtime_heat2_h,
  ROUND(SUM(COALESCE(runtime_fan1_min + runtime_fan2_min, 0))::numeric / 60, 1) AS runtime_fans_h,
  ROUND(SUM(COALESCE(runtime_fog_min, 0))::numeric / 60, 1) AS runtime_fog_h,
  ROUND(SUM(COALESCE(runtime_vent_min, 0))::numeric / 60, 1) AS runtime_vent_h,
  ROUND(SUM(COALESCE(runtime_grow_light_min, 0))::numeric / 60, 1) AS runtime_grow_light_h,
  ROUND(SUM(COALESCE(runtime_mister_south_h + runtime_mister_west_h + runtime_mister_center_h, 0))::numeric, 1) AS runtime_misters_h,

  -- Cycles (summed)
  SUM(COALESCE(cycles_heat1, 0) + COALESCE(cycles_heat2, 0)) AS cycles_heat,
  SUM(COALESCE(cycles_fan1, 0) + COALESCE(cycles_fan2, 0)) AS cycles_fans,
  SUM(COALESCE(cycles_fog, 0)) AS cycles_fog,
  SUM(COALESCE(cycles_vent, 0)) AS cycles_vent

FROM daily_summary
WHERE temp_avg IS NOT NULL
GROUP BY date_trunc('week', date)
ORDER BY week_start;

COMMENT ON VIEW v_weekly_summary IS 'ISO week aggregation of daily_summary. Climate averages, stress/water/energy/cost sums, equipment runtime totals.';

-- ============================================================
-- v_monthly_summary — Calendar month aggregation
-- ============================================================

CREATE OR REPLACE VIEW v_monthly_summary AS
SELECT
  date_trunc('month', date)::date AS month_start,
  count(*) AS days,

  ROUND(AVG(temp_avg)::numeric, 1) AS temp_avg,
  ROUND(MIN(temp_min)::numeric, 1) AS temp_min,
  ROUND(MAX(temp_max)::numeric, 1) AS temp_max,
  ROUND(AVG(rh_avg)::numeric, 1) AS rh_avg,
  ROUND(MIN(rh_min)::numeric, 1) AS rh_min,
  ROUND(MAX(rh_max)::numeric, 1) AS rh_max,
  ROUND(AVG(vpd_avg)::numeric, 2) AS vpd_avg,
  ROUND(MIN(vpd_min)::numeric, 2) AS vpd_min,
  ROUND(MAX(vpd_max)::numeric, 2) AS vpd_max,
  ROUND(AVG(dli_final)::numeric, 1) AS dli_avg,
  ROUND(AVG(co2_avg)::numeric, 0) AS co2_avg,
  ROUND(MIN(outdoor_temp_min)::numeric, 1) AS outdoor_temp_min,
  ROUND(MAX(outdoor_temp_max)::numeric, 1) AS outdoor_temp_max,

  ROUND(SUM(COALESCE(stress_hours_heat, 0))::numeric, 1) AS stress_hours_heat,
  ROUND(SUM(COALESCE(stress_hours_cold, 0))::numeric, 1) AS stress_hours_cold,
  ROUND(SUM(COALESCE(stress_hours_vpd_high, 0))::numeric, 1) AS stress_hours_vpd_high,
  ROUND(SUM(COALESCE(stress_hours_vpd_low, 0))::numeric, 1) AS stress_hours_vpd_low,

  ROUND(SUM(COALESCE(water_used_gal, 0))::numeric, 0) AS total_water_gal,
  ROUND(SUM(COALESCE(mister_water_gal, 0))::numeric, 0) AS mister_water_gal,

  ROUND(SUM(COALESCE(kwh_estimated, 0))::numeric, 1) AS kwh_total,
  ROUND(SUM(COALESCE(therms_estimated, 0))::numeric, 2) AS therms_total,

  ROUND(SUM(COALESCE(cost_electric, 0))::numeric, 2) AS cost_electric,
  ROUND(SUM(COALESCE(cost_gas, 0))::numeric, 2) AS cost_gas,
  ROUND(SUM(COALESCE(cost_water, 0))::numeric, 2) AS cost_water,
  ROUND(SUM(COALESCE(cost_total, 0))::numeric, 2) AS total_cost,

  ROUND(SUM(COALESCE(runtime_heat1_min, 0))::numeric / 60, 1) AS runtime_heat1_h,
  ROUND(SUM(COALESCE(runtime_heat2_min, 0))::numeric / 60, 1) AS runtime_heat2_h,
  ROUND(SUM(COALESCE(runtime_fan1_min + runtime_fan2_min, 0))::numeric / 60, 1) AS runtime_fans_h,
  ROUND(SUM(COALESCE(runtime_fog_min, 0))::numeric / 60, 1) AS runtime_fog_h,
  ROUND(SUM(COALESCE(runtime_vent_min, 0))::numeric / 60, 1) AS runtime_vent_h,
  ROUND(SUM(COALESCE(runtime_grow_light_min, 0))::numeric / 60, 1) AS runtime_grow_light_h,
  ROUND(SUM(COALESCE(runtime_mister_south_h + runtime_mister_west_h + runtime_mister_center_h, 0))::numeric, 1) AS runtime_misters_h,

  SUM(COALESCE(cycles_heat1, 0) + COALESCE(cycles_heat2, 0)) AS cycles_heat,
  SUM(COALESCE(cycles_fan1, 0) + COALESCE(cycles_fan2, 0)) AS cycles_fans,
  SUM(COALESCE(cycles_fog, 0)) AS cycles_fog,
  SUM(COALESCE(cycles_vent, 0)) AS cycles_vent

FROM daily_summary
WHERE temp_avg IS NOT NULL
GROUP BY date_trunc('month', date)
ORDER BY month_start;

COMMENT ON VIEW v_monthly_summary IS 'Calendar month aggregation of daily_summary.';

-- ============================================================
-- fn_period_summary — Arbitrary date range
-- ============================================================

CREATE OR REPLACE FUNCTION fn_period_summary(start_date date, end_date date)
RETURNS TABLE(
  days bigint,
  temp_avg numeric, temp_min numeric, temp_max numeric,
  rh_avg numeric, vpd_avg numeric, vpd_min numeric, vpd_max numeric,
  dli_avg numeric, co2_avg numeric,
  outdoor_temp_min numeric, outdoor_temp_max numeric,
  stress_hours_heat numeric, stress_hours_cold numeric,
  stress_hours_vpd_high numeric, stress_hours_vpd_low numeric,
  total_water_gal numeric, mister_water_gal numeric,
  kwh_total numeric, therms_total numeric,
  cost_electric numeric, cost_gas numeric, cost_water numeric, total_cost numeric,
  runtime_heat1_h numeric, runtime_heat2_h numeric, runtime_fans_h numeric,
  runtime_fog_h numeric, runtime_vent_h numeric, runtime_grow_light_h numeric,
  runtime_misters_h numeric
) AS $$
  SELECT
    count(*)::bigint,
    ROUND(AVG(ds.temp_avg)::numeric, 1),
    ROUND(MIN(ds.temp_min)::numeric, 1),
    ROUND(MAX(ds.temp_max)::numeric, 1),
    ROUND(AVG(ds.rh_avg)::numeric, 1),
    ROUND(AVG(ds.vpd_avg)::numeric, 2),
    ROUND(MIN(ds.vpd_min)::numeric, 2),
    ROUND(MAX(ds.vpd_max)::numeric, 2),
    ROUND(AVG(ds.dli_final)::numeric, 1),
    ROUND(AVG(ds.co2_avg)::numeric, 0),
    ROUND(MIN(ds.outdoor_temp_min)::numeric, 1),
    ROUND(MAX(ds.outdoor_temp_max)::numeric, 1),
    ROUND(SUM(COALESCE(ds.stress_hours_heat, 0))::numeric, 1),
    ROUND(SUM(COALESCE(ds.stress_hours_cold, 0))::numeric, 1),
    ROUND(SUM(COALESCE(ds.stress_hours_vpd_high, 0))::numeric, 1),
    ROUND(SUM(COALESCE(ds.stress_hours_vpd_low, 0))::numeric, 1),
    ROUND(SUM(COALESCE(ds.water_used_gal, 0))::numeric, 0),
    ROUND(SUM(COALESCE(ds.mister_water_gal, 0))::numeric, 0),
    ROUND(SUM(COALESCE(ds.kwh_estimated, 0))::numeric, 1),
    ROUND(SUM(COALESCE(ds.therms_estimated, 0))::numeric, 2),
    ROUND(SUM(COALESCE(ds.cost_electric, 0))::numeric, 2),
    ROUND(SUM(COALESCE(ds.cost_gas, 0))::numeric, 2),
    ROUND(SUM(COALESCE(ds.cost_water, 0))::numeric, 2),
    ROUND(SUM(COALESCE(ds.cost_total, 0))::numeric, 2),
    ROUND(SUM(COALESCE(ds.runtime_heat1_min, 0))::numeric / 60, 1),
    ROUND(SUM(COALESCE(ds.runtime_heat2_min, 0))::numeric / 60, 1),
    ROUND(SUM(COALESCE(ds.runtime_fan1_min + ds.runtime_fan2_min, 0))::numeric / 60, 1),
    ROUND(SUM(COALESCE(ds.runtime_fog_min, 0))::numeric / 60, 1),
    ROUND(SUM(COALESCE(ds.runtime_vent_min, 0))::numeric / 60, 1),
    ROUND(SUM(COALESCE(ds.runtime_grow_light_min, 0))::numeric / 60, 1),
    ROUND(SUM(COALESCE(ds.runtime_mister_south_h + ds.runtime_mister_west_h + ds.runtime_mister_center_h, 0))::numeric, 1)
  FROM daily_summary ds
  WHERE ds.date >= start_date AND ds.date <= end_date
  AND ds.temp_avg IS NOT NULL;
$$ LANGUAGE sql STABLE;

COMMENT ON FUNCTION fn_period_summary(date, date) IS 'Arbitrary date range summary from daily_summary. Returns climate avgs/extremes, stress sums, cost totals, equipment runtimes.';
