-- 078-unified-greenhouse-state.sql
-- Unified time series view: one row per climate reading with equipment state,
-- setpoints, forecast, and compliance flags joined.
-- Canonical data structure for planner, simulation, dashboards, website.

-- Efficient approach: use time_bucket + last() for event-driven tables
-- rather than per-row correlated subqueries.

DROP MATERIALIZED VIEW IF EXISTS v_greenhouse_state CASCADE;

-- Helper: latest setpoint value as of a given time
CREATE OR REPLACE FUNCTION fn_setpoint_at(p_param text, p_ts timestamptz)
RETURNS double precision LANGUAGE sql STABLE AS $$
    SELECT value FROM setpoint_changes
    WHERE parameter = p_param AND ts <= p_ts
    ORDER BY ts DESC LIMIT 1;
$$;

-- Helper: latest equipment state as of a given time
CREATE OR REPLACE FUNCTION fn_equip_at(p_equip text, p_ts timestamptz)
RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT state FROM equipment_state
    WHERE equipment = p_equip AND ts <= p_ts
    ORDER BY ts DESC LIMIT 1;
$$;

CREATE MATERIALIZED VIEW v_greenhouse_state AS
SELECT
    c.ts,
    -- Indoor climate
    c.temp_avg, c.vpd_avg, c.rh_avg, c.dew_point,
    c.temp_north, c.temp_south, c.temp_east, c.temp_west,
    c.vpd_south, c.vpd_west, c.vpd_east,
    c.lux, c.solar_irradiance_w_m2, c.dli_today,
    c.co2_ppm, c.abs_humidity, c.enthalpy_delta,
    -- Outdoor
    c.outdoor_temp_f, c.outdoor_rh_pct,
    -- Derived
    ROUND((c.temp_avg - COALESCE(c.dew_point, c.temp_avg - 10))::numeric, 1) AS dp_margin_f,
    -- Equipment state at this timestamp
    fn_equip_at('fan1', c.ts) AS fan1,
    fn_equip_at('fan2', c.ts) AS fan2,
    fn_equip_at('vent', c.ts) AS vent,
    fn_equip_at('fog', c.ts) AS fog,
    fn_equip_at('heat1', c.ts) AS heat1,
    fn_equip_at('heat2', c.ts) AS heat2,
    fn_equip_at('mister_south', c.ts) AS mist_south,
    fn_equip_at('mister_west', c.ts) AS mist_west,
    fn_equip_at('mister_center', c.ts) AS mist_center,
    -- Active setpoints at this timestamp
    fn_setpoint_at('temp_high', c.ts) AS sp_temp_high,
    fn_setpoint_at('temp_low', c.ts) AS sp_temp_low,
    fn_setpoint_at('vpd_high', c.ts) AS sp_vpd_high,
    fn_setpoint_at('vpd_low', c.ts) AS sp_vpd_low,
    fn_setpoint_at('bias_cool', c.ts) AS sp_bias_cool,
    fn_setpoint_at('bias_heat', c.ts) AS sp_bias_heat,
    fn_setpoint_at('vpd_hysteresis', c.ts) AS sp_vpd_hysteresis,
    fn_setpoint_at('mist_max_closed_vent_s', c.ts) AS sp_sealed_max_s,
    fn_setpoint_at('mist_thermal_relief_s', c.ts) AS sp_relief_s,
    fn_setpoint_at('vpd_watch_dwell_s', c.ts) AS sp_watch_dwell_s,
    fn_setpoint_at('d_cool_stage_2', c.ts) AS sp_d_cool_s2,
    fn_setpoint_at('mister_engage_kpa', c.ts) AS sp_mister_engage,
    -- Compliance flags
    CASE WHEN c.temp_avg BETWEEN
        COALESCE(fn_setpoint_at('temp_low', c.ts), 58)
        AND COALESCE(fn_setpoint_at('temp_high', c.ts), 82)
        THEN true ELSE false END AS temp_in_band,
    CASE WHEN c.vpd_avg BETWEEN
        COALESCE(fn_setpoint_at('vpd_low', c.ts), 0.5)
        AND COALESCE(fn_setpoint_at('vpd_high', c.ts), 1.5)
        THEN true ELSE false END AS vpd_in_band,
    -- Mode (latest at this timestamp)
    (SELECT value FROM system_state
     WHERE entity = 'greenhouse_state' AND ts <= c.ts
     ORDER BY ts DESC LIMIT 1) AS greenhouse_mode
FROM climate c
WHERE c.temp_avg IS NOT NULL
ORDER BY c.ts;

CREATE INDEX idx_gs_ts ON v_greenhouse_state (ts DESC);

COMMENT ON MATERIALIZED VIEW v_greenhouse_state IS
    'Unified greenhouse time series. One row per sensor reading with equipment, setpoints, compliance, and mode. Refresh: every 5 min by ingestor.';
