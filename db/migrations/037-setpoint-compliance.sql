-- Migration 037: v_setpoint_compliance view + fn_compliance_pct function
--
-- Joins climate readings against setpoint_schedule targets to show
-- how well actual conditions track planned setpoints per zone per hour.

-- Determine current season based on month
CREATE OR REPLACE FUNCTION fn_current_season() RETURNS TEXT AS $$
BEGIN
  RETURN CASE EXTRACT(MONTH FROM now())
    WHEN 3 THEN 'spring' WHEN 4 THEN 'spring' WHEN 5 THEN 'spring'
    WHEN 6 THEN 'summer' WHEN 7 THEN 'summer' WHEN 8 THEN 'summer'
    WHEN 9 THEN 'fall' WHEN 10 THEN 'fall' WHEN 11 THEN 'fall'
    ELSE 'winter'
  END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE VIEW v_setpoint_compliance AS
WITH zone_readings AS (
  -- Unpivot climate zones into rows
  SELECT ts,
    'south' AS zone, temp_south AS actual_temp, rh_south AS actual_rh, vpd_south AS actual_vpd
  FROM climate WHERE temp_south IS NOT NULL
  UNION ALL
  SELECT ts,
    'north', temp_north, rh_north, vpd_north
  FROM climate WHERE temp_north IS NOT NULL
  UNION ALL
  SELECT ts,
    'east', temp_east, rh_east, vpd_east
  FROM climate WHERE temp_east IS NOT NULL
  UNION ALL
  SELECT ts,
    'west', temp_west, rh_west, vpd_west
  FROM climate WHERE temp_west IS NOT NULL
  UNION ALL
  SELECT ts,
    'greenhouse' AS zone, temp_avg, rh_avg, vpd_avg
  FROM climate WHERE temp_avg IS NOT NULL
)
SELECT
  zr.ts,
  zr.zone,
  ROUND(zr.actual_temp::numeric, 1) AS actual_temp,
  ss.temp_target_f::numeric AS target_temp,
  (zr.actual_temp BETWEEN ss.temp_target_f - 2.0 AND ss.temp_target_f + 2.0) AS temp_in_range,
  ROUND(zr.actual_rh::numeric, 1) AS actual_rh,
  ss.humidity_target_pct::numeric AS target_rh,
  (zr.actual_rh BETWEEN ss.humidity_target_pct - 5.0 AND ss.humidity_target_pct + 5.0) AS rh_in_range,
  ROUND(zr.actual_vpd::numeric, 2) AS actual_vpd,
  ss.vpd_target_kpa::numeric AS target_vpd,
  (zr.actual_vpd BETWEEN ss.vpd_target_kpa - 0.15 AND ss.vpd_target_kpa + 0.15) AS vpd_in_range,
  (zr.actual_temp BETWEEN ss.temp_target_f - 2.0 AND ss.temp_target_f + 2.0)
    AND (zr.actual_rh BETWEEN ss.humidity_target_pct - 5.0 AND ss.humidity_target_pct + 5.0)
    AND (zr.actual_vpd BETWEEN ss.vpd_target_kpa - 0.15 AND ss.vpd_target_kpa + 0.15)
  AS overall_compliant
FROM zone_readings zr
JOIN setpoint_schedule ss
  ON ss.zone = (CASE WHEN zr.zone = 'greenhouse' THEN 'south' ELSE zr.zone END)
  AND ss.hour_of_day = EXTRACT(HOUR FROM zr.ts AT TIME ZONE 'America/Denver')::int
  AND ss.season = fn_current_season();

COMMENT ON VIEW v_setpoint_compliance IS 'Climate readings vs setpoint_schedule targets. Tolerance: ±2°F temp, ±5% RH, ±0.15 kPa VPD. Greenhouse-wide uses south zone targets.';

-- Convenience function: compliance percentage over a given interval
CREATE OR REPLACE FUNCTION fn_compliance_pct(lookback INTERVAL)
RETURNS TABLE(zone TEXT, temp_pct NUMERIC, rh_pct NUMERIC, vpd_pct NUMERIC, overall_pct NUMERIC) AS $$
  SELECT
    v.zone,
    ROUND(100.0 * COUNT(*) FILTER (WHERE temp_in_range) / NULLIF(COUNT(*), 0), 1) AS temp_pct,
    ROUND(100.0 * COUNT(*) FILTER (WHERE rh_in_range) / NULLIF(COUNT(*), 0), 1) AS rh_pct,
    ROUND(100.0 * COUNT(*) FILTER (WHERE vpd_in_range) / NULLIF(COUNT(*), 0), 1) AS vpd_pct,
    ROUND(100.0 * COUNT(*) FILTER (WHERE overall_compliant) / NULLIF(COUNT(*), 0), 1) AS overall_pct
  FROM v_setpoint_compliance v
  WHERE v.ts > now() - lookback
  GROUP BY v.zone
  ORDER BY v.zone;
$$ LANGUAGE sql STABLE;

COMMENT ON FUNCTION fn_compliance_pct(INTERVAL) IS 'Returns compliance percentage per zone over the given interval. Example: SELECT * FROM fn_compliance_pct(interval ''24 hours'')';
