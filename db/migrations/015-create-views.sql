-- Migration 015: Create new derived views
-- These compute from existing data. No new hardware required.

-- v_disease_risk: Botrytis and condensation risk scoring
-- Rolling 6-hour Botrytis window (RH > 85% AND temp 60–80°F)
-- 4-hour condensation window (VPD < 0.4 kPa)
CREATE OR REPLACE VIEW v_disease_risk AS
WITH recent AS (
    SELECT ts, rh_avg, temp_avg, vpd_avg
    FROM climate
    WHERE ts >= now() - INTERVAL '24 hours'
      AND rh_avg IS NOT NULL AND temp_avg IS NOT NULL
),
botrytis_windows AS (
    SELECT ts,
        CASE WHEN rh_avg > 85 AND temp_avg BETWEEN 60 AND 80 THEN 1 ELSE 0 END AS botrytis_flag,
        CASE WHEN vpd_avg < 0.4 THEN 1 ELSE 0 END AS condensation_flag
    FROM recent
)
SELECT
    date_trunc('hour', ts) AS hour,
    ROUND(AVG(botrytis_flag)::numeric * 100, 1) AS botrytis_risk_pct,
    ROUND(AVG(condensation_flag)::numeric * 100, 1) AS condensation_risk_pct,
    ROUND((SUM(botrytis_flag) * 2.0 / 60.0)::numeric, 2) AS botrytis_consecutive_hours,
    ROUND((SUM(condensation_flag) * 2.0 / 60.0)::numeric, 2) AS condensation_consecutive_hours
FROM botrytis_windows
GROUP BY 1
ORDER BY 1;

-- v_relay_stuck: Detect equipment ON too long without OFF event
-- Thresholds: heater > 3h, fan > 4h, fog > 2h, vent > 6h
CREATE MATERIALIZED VIEW IF NOT EXISTS v_relay_stuck AS
WITH latest_on AS (
    SELECT equipment, MAX(ts) AS last_on_ts
    FROM equipment_state
    WHERE state = TRUE
    GROUP BY equipment
),
latest_off AS (
    SELECT equipment, MAX(ts) AS last_off_ts
    FROM equipment_state
    WHERE state = FALSE
    GROUP BY equipment
),
stuck_check AS (
    SELECT
        lo.equipment,
        lo.last_on_ts,
        lf.last_off_ts,
        EXTRACT(EPOCH FROM (now() - lo.last_on_ts)) / 3600.0 AS hours_on,
        CASE lo.equipment
            WHEN 'heat1' THEN 3 WHEN 'heat2' THEN 3
            WHEN 'fan1' THEN 4 WHEN 'fan2' THEN 4
            WHEN 'fog' THEN 2
            WHEN 'vent' THEN 6
            ELSE 8
        END AS threshold_hours
    FROM latest_on lo
    LEFT JOIN latest_off lf ON lo.equipment = lf.equipment
    WHERE lo.last_on_ts > COALESCE(lf.last_off_ts, '1970-01-01'::timestamptz)
)
SELECT equipment, last_on_ts, hours_on, threshold_hours,
       (hours_on > threshold_hours) AS is_stuck
FROM stuck_check;

-- v_dif: Day/Night temperature differential
-- Day = 07:00–19:00 MT, Night = 19:00–07:00 MT
CREATE OR REPLACE VIEW v_dif AS
SELECT
    date_trunc('day', ts AT TIME ZONE 'America/Denver') AS date,
    ROUND(AVG(CASE
        WHEN EXTRACT(HOUR FROM ts AT TIME ZONE 'America/Denver') BETWEEN 7 AND 18
        THEN temp_avg END)::numeric, 2) AS day_avg_temp,
    ROUND(AVG(CASE
        WHEN EXTRACT(HOUR FROM ts AT TIME ZONE 'America/Denver') NOT BETWEEN 7 AND 18
        THEN temp_avg END)::numeric, 2) AS night_avg_temp,
    ROUND((AVG(CASE
        WHEN EXTRACT(HOUR FROM ts AT TIME ZONE 'America/Denver') BETWEEN 7 AND 18
        THEN temp_avg END) -
      AVG(CASE
        WHEN EXTRACT(HOUR FROM ts AT TIME ZONE 'America/Denver') NOT BETWEEN 7 AND 18
        THEN temp_avg END))::numeric, 2) AS dif
FROM climate
WHERE temp_avg IS NOT NULL
GROUP BY 1
ORDER BY 1;

-- v_water_efficiency: Water usage per unit of light and yield
CREATE OR REPLACE VIEW v_water_efficiency AS
SELECT
    ds.date,
    ds.water_used_gal,
    ds.dli_final,
    CASE WHEN ds.dli_final > 0
         THEN ROUND((ds.water_used_gal / ds.dli_final)::numeric, 3)
         ELSE NULL END AS gal_per_mol_dli
FROM daily_summary ds
WHERE ds.water_used_gal IS NOT NULL
ORDER BY ds.date;

-- v_gdd: Growing degree days per crop since planting
-- GDD_day = max(0, daily_avg_temp - crop.base_temp_f)
CREATE OR REPLACE VIEW v_gdd AS
WITH daily_temps AS (
    SELECT
        date_trunc('day', ts) AS date,
        AVG(temp_avg) AS avg_temp_f
    FROM climate
    WHERE temp_avg IS NOT NULL
    GROUP BY 1
)
SELECT
    c.id AS crop_id,
    c.name,
    c.position,
    dt.date,
    GREATEST(0, dt.avg_temp_f - c.base_temp_f) AS gdd_day,
    SUM(GREATEST(0, dt.avg_temp_f - c.base_temp_f))
        OVER (PARTITION BY c.id ORDER BY dt.date ROWS UNBOUNDED PRECEDING) AS gdd_cumulative
FROM crops c
JOIN daily_temps dt ON dt.date >= c.planted_date::timestamptz
WHERE c.is_active = TRUE
ORDER BY c.id, dt.date;
