-- 052-cost-views-gas-fix.sql
-- Add gas cost (heat2) to v_cost_today and ensure v_greenhouse_now references it

-- v_cost_today: add cost_gas column using heat2 runtime × 75K BTU/hr ÷ 100K BTU/therm × $1.20/therm
CREATE OR REPLACE VIEW v_cost_today AS
WITH today_start AS (
    SELECT (date_trunc('day', now() AT TIME ZONE 'America/Denver') AT TIME ZONE 'America/Denver') AS ts
),
events_with_next AS (
    SELECT e.equipment, e.state, e.ts,
           lead(e.ts) OVER (PARTITION BY e.equipment ORDER BY e.ts) AS next_ts
    FROM equipment_state e, today_start t
    WHERE e.ts >= t.ts
),
runtimes AS (
    SELECT equipment,
           SUM(CASE WHEN state = true
               THEN EXTRACT(epoch FROM COALESCE(next_ts, now()) - ts) / 3600
               ELSE 0 END) AS hours_on
    FROM events_with_next
    GROUP BY equipment
)
SELECT
    ROUND(COALESCE(SUM(r.hours_on * COALESCE(ea.wattage, 0) / 1000.0 * 0.111), 0)::numeric, 2) AS cost_electric,
    ROUND(COALESCE((SELECT r2.hours_on * 75000.0 / 100000.0 * 0.83
                    FROM runtimes r2 WHERE r2.equipment = 'heat2'), 0)::numeric, 2) AS cost_gas,
    ROUND(COALESCE((SELECT (MAX(c.water_total_gal) - MIN(c.water_total_gal)) * 0.00484
                    FROM climate c, today_start t
                    WHERE c.ts >= t.ts AND c.water_total_gal > 0), 0)::numeric, 2) AS cost_water,
    ROUND((
        COALESCE(SUM(r.hours_on * COALESCE(ea.wattage, 0) / 1000.0 * 0.111), 0)
      + COALESCE((SELECT r2.hours_on * 75000.0 / 100000.0 * 0.83
                  FROM runtimes r2 WHERE r2.equipment = 'heat2'), 0)
      + COALESCE((SELECT (MAX(c.water_total_gal) - MIN(c.water_total_gal)) * 0.00484
                  FROM climate c, today_start t
                  WHERE c.ts >= t.ts AND c.water_total_gal > 0), 0)
    )::numeric, 2) AS cost_total
FROM runtimes r
LEFT JOIN equipment_assets ea ON r.equipment = ea.equipment;

-- v_greenhouse_now: add cost columns from v_cost_today
CREATE OR REPLACE VIEW v_greenhouse_now AS
SELECT
    c.ts,
    ROUND(c.temp_avg::numeric, 1) AS temp_avg,
    ROUND(c.temp_north::numeric, 1) AS temp_north,
    ROUND(c.temp_south::numeric, 1) AS temp_south,
    ROUND(c.temp_east::numeric, 1) AS temp_east,
    ROUND(c.temp_west::numeric, 1) AS temp_west,
    ROUND(c.rh_avg::numeric, 1) AS rh_avg,
    ROUND(c.vpd_avg::numeric, 2) AS vpd_avg,
    ROUND(c.co2_ppm::numeric, 0) AS co2_ppm,
    ROUND(c.lux::numeric, 0) AS lux,
    ROUND(c.dli_today::numeric, 2) AS dli_today,
    o.outdoor_temp_f, o.outdoor_rh_pct, o.wind_mph, o.pressure_hpa,
    ROUND(c.mister_water_today::numeric, 1) AS mister_water_today,
    h.hydro_ph, h.hydro_ec_us_cm, h.hydro_tds_ppm, h.hydro_water_temp_f,
    d.wifi_rssi, ROUND(d.heap_bytes::numeric, 0) AS heap_kb, ROUND(d.uptime_s::numeric, 0) AS uptime_s,
    (SELECT value FROM system_state WHERE entity = 'greenhouse_state' ORDER BY ts DESC LIMIT 1) AS state,
    (SELECT value FROM system_state WHERE entity = 'lead_fan' ORDER BY ts DESC LIMIT 1) AS lead_fan,
    fn_system_health() AS health_score,
    (SELECT count(*) FROM alert_log WHERE disposition = 'open') AS open_alerts,
    cost.cost_electric, cost.cost_gas, cost.cost_water, cost.cost_total
FROM climate c
LEFT JOIN LATERAL (
    SELECT wifi_rssi, heap_bytes, uptime_s FROM diagnostics ORDER BY ts DESC LIMIT 1
) d ON true
LEFT JOIN LATERAL (
    SELECT ROUND(climate.outdoor_temp_f::numeric, 1) AS outdoor_temp_f,
           ROUND(climate.outdoor_rh_pct::numeric, 0) AS outdoor_rh_pct,
           ROUND(climate.wind_speed_mph::numeric, 1) AS wind_mph,
           ROUND(climate.pressure_hpa::numeric, 1) AS pressure_hpa
    FROM climate
    WHERE climate.outdoor_temp_f IS NOT NULL AND climate.ts > (now() - interval '30 min')
    ORDER BY climate.ts DESC LIMIT 1
) o ON true
LEFT JOIN LATERAL (
    SELECT ROUND(climate.hydro_ph::numeric, 1) AS hydro_ph,
           ROUND(climate.hydro_ec_us_cm::numeric, 0) AS hydro_ec_us_cm,
           ROUND(climate.hydro_tds_ppm::numeric, 0) AS hydro_tds_ppm,
           ROUND(climate.hydro_water_temp_f::numeric, 1) AS hydro_water_temp_f
    FROM climate
    WHERE climate.hydro_ph IS NOT NULL AND climate.ts > (now() - interval '30 min')
    ORDER BY climate.ts DESC LIMIT 1
) h ON true
CROSS JOIN v_cost_today cost
WHERE c.temp_avg IS NOT NULL
ORDER BY c.ts DESC LIMIT 1;
