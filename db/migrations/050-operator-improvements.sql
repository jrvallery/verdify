-- Migration 050: Operator improvements (forecast correction, plan supersession, mister context)

-- ============================================================
-- 1. fn_forecast_correction — Rolling 7-day bias per parameter
-- ============================================================

CREATE OR REPLACE FUNCTION fn_forecast_correction(param TEXT, lead_hours_max NUMERIC DEFAULT 24)
RETURNS TABLE(parameter TEXT, avg_error NUMERIC, samples BIGINT) AS $$
  SELECT
    param AS parameter,
    CASE param
      WHEN 'temp_f' THEN ROUND(AVG(temp_error)::numeric, 1)
      WHEN 'solar_w_m2' THEN ROUND(AVG(solar_error)::numeric, 0)
    END AS avg_error,
    count(*) AS samples
  FROM v_forecast_vs_actual
  WHERE hour > now() - interval '7 days'
  AND actual_temp IS NOT NULL
  AND EXTRACT(EPOCH FROM now() - hour) / 3600 <= lead_hours_max;
$$ LANGUAGE sql STABLE;

COMMENT ON FUNCTION fn_forecast_correction(TEXT, NUMERIC) IS 'Rolling 7-day forecast bias. Usage: SELECT * FROM fn_forecast_correction(''temp_f'', 24) → avg temp error for ≤24h forecasts.';

-- ============================================================
-- 2. v_active_plan — Resolved plan (latest per parameter)
-- ============================================================

CREATE OR REPLACE VIEW v_active_plan AS
SELECT DISTINCT ON (parameter)
  parameter, value, ts, plan_id, reason, created_at
FROM setpoint_plan
WHERE ts <= now()
ORDER BY parameter, created_at DESC;

COMMENT ON VIEW v_active_plan IS 'Currently active plan value per parameter. Resolves supersession: latest created_at wins.';

-- ============================================================
-- 3. Update v_mister_effectiveness with outdoor VPD context
-- ============================================================

CREATE OR REPLACE VIEW v_mister_effectiveness AS
WITH mister_events AS (
  SELECT ts, equipment, state,
    LEAD(ts) OVER (PARTITION BY equipment ORDER BY ts) AS next_ts,
    LEAD(state) OVER (PARTITION BY equipment ORDER BY ts) AS next_state
  FROM equipment_state
  WHERE equipment IN ('mister_south', 'mister_west', 'mister_center')
  AND ts > now() - interval '14 days'
),
mister_cycles AS (
  SELECT ts AS on_ts, equipment, next_ts AS off_ts,
    EXTRACT(EPOCH FROM next_ts - ts)::int AS duration_s
  FROM mister_events
  WHERE state = true AND next_state = false
  AND next_ts - ts < interval '30 minutes'
  AND next_ts - ts > interval '5 seconds'
)
SELECT
  mc.on_ts, mc.equipment, mc.duration_s,
  ROUND(vpd_before.vpd::numeric, 2) AS vpd_before,
  ROUND(vpd_after.vpd::numeric, 2) AS vpd_after,
  ROUND((vpd_before.vpd - vpd_after.vpd)::numeric, 2) AS vpd_delta,
  ROUND(outdoor.outdoor_temp::numeric, 1) AS outdoor_temp_f,
  ROUND(outdoor.outdoor_rh::numeric, 0) AS outdoor_rh_pct
FROM mister_cycles mc
LEFT JOIN LATERAL (
  SELECT vpd_avg AS vpd FROM climate WHERE ts <= mc.on_ts AND vpd_avg IS NOT NULL ORDER BY ts DESC LIMIT 1
) vpd_before ON true
LEFT JOIN LATERAL (
  SELECT vpd_avg AS vpd FROM climate WHERE ts >= mc.off_ts AND vpd_avg IS NOT NULL ORDER BY ts LIMIT 1
) vpd_after ON true
LEFT JOIN LATERAL (
  SELECT outdoor_temp_f AS outdoor_temp, outdoor_rh_pct AS outdoor_rh
  FROM climate WHERE ts <= mc.on_ts AND outdoor_temp_f IS NOT NULL ORDER BY ts DESC LIMIT 1
) outdoor ON true
ORDER BY mc.on_ts DESC;

COMMENT ON VIEW v_mister_effectiveness IS 'VPD before/after each misting cycle with outdoor context. vpd_delta > 0 = improvement.';

-- ============================================================
-- 4. TimescaleDB compression policy (climate, energy)
-- ============================================================

-- Compress chunks older than 7 days (saves ~70% storage)
SELECT add_compression_policy('climate', INTERVAL '7 days');
SELECT add_compression_policy('energy', INTERVAL '7 days');
SELECT add_compression_policy('diagnostics', INTERVAL '7 days');

-- Retention: drop raw data older than 1 year (daily_summary is forever)
SELECT add_retention_policy('climate', INTERVAL '365 days');
SELECT add_retention_policy('energy', INTERVAL '365 days');
SELECT add_retention_policy('diagnostics', INTERVAL '180 days');
SELECT add_retention_policy('esp32_logs', INTERVAL '30 days');
