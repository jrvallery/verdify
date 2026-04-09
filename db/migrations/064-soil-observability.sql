-- 064-soil-observability.sql
-- Soil sensor targets + status view for observability

-- Soil moisture targets per zone/crop
CREATE TABLE IF NOT EXISTS soil_moisture_targets (
    id SERIAL PRIMARY KEY,
    zone TEXT NOT NULL,
    crop TEXT,
    min_pct NUMERIC NOT NULL,
    max_pct NUMERIC NOT NULL,
    saturation_pct NUMERIC NOT NULL DEFAULT 85,
    wilt_pct NUMERIC NOT NULL DEFAULT 15,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO soil_moisture_targets (zone, crop, min_pct, max_pct, saturation_pct, wilt_pct, notes) VALUES
('south_1', 'Canna Lily', 40, 60, 80, 20, 'Large pots on floor with drip heads. SEN0601 (moisture+temp+EC).'),
('south_2', 'Canna Lily', 40, 60, 80, 20, 'Adjacent pot cluster. SEN0600 (moisture+temp).'),
('west', 'Unknown pots', 35, 55, 75, 18, 'Random pots, contents unknown. SEN0600 (moisture+temp).');

-- v_soil_status: latest readings per zone with target comparison + trend
CREATE OR REPLACE VIEW v_soil_status AS
WITH latest AS (
    SELECT
        ts,
        soil_moisture_south_1, soil_temp_south_1, soil_ec_south_1,
        soil_moisture_south_2, soil_temp_south_2,
        soil_moisture_west, soil_temp_west
    FROM climate
    WHERE soil_moisture_south_1 IS NOT NULL OR soil_moisture_west IS NOT NULL
    ORDER BY ts DESC LIMIT 1
),
trend AS (
    SELECT
        AVG(soil_moisture_south_1) AS avg_s1,
        AVG(soil_moisture_south_2) AS avg_s2,
        AVG(soil_moisture_west) AS avg_w,
        (array_agg(soil_moisture_south_1 ORDER BY ts DESC))[1] AS last_s1,
        (array_agg(soil_moisture_south_1 ORDER BY ts ASC))[1] AS first_s1,
        (array_agg(soil_moisture_south_2 ORDER BY ts DESC))[1] AS last_s2,
        (array_agg(soil_moisture_south_2 ORDER BY ts ASC))[1] AS first_s2,
        (array_agg(soil_moisture_west ORDER BY ts DESC))[1] AS last_w,
        (array_agg(soil_moisture_west ORDER BY ts ASC))[1] AS first_w
    FROM (
        SELECT ts, soil_moisture_south_1, soil_moisture_south_2, soil_moisture_west
        FROM climate
        WHERE (soil_moisture_south_1 IS NOT NULL OR soil_moisture_west IS NOT NULL)
          AND ts > now() - interval '6 hours'
        ORDER BY ts DESC LIMIT 6
    ) recent
),
unpivoted AS (
    SELECT 'south_1' AS zone,
        l.soil_moisture_south_1 AS moisture, l.soil_temp_south_1 AS temp, l.soil_ec_south_1 AS ec,
        EXTRACT(EPOCH FROM now() - l.ts)::int AS age_s,
        CASE WHEN t.last_s1 - t.first_s1 > 2 THEN 'rising'
             WHEN t.first_s1 - t.last_s1 > 2 THEN 'falling'
             ELSE 'stable' END AS trend
    FROM latest l, trend t
    UNION ALL
    SELECT 'south_2', l.soil_moisture_south_2, l.soil_temp_south_2, NULL,
        EXTRACT(EPOCH FROM now() - l.ts)::int,
        CASE WHEN t.last_s2 - t.first_s2 > 2 THEN 'rising'
             WHEN t.first_s2 - t.last_s2 > 2 THEN 'falling'
             ELSE 'stable' END
    FROM latest l, trend t
    UNION ALL
    SELECT 'west', l.soil_moisture_west, l.soil_temp_west, NULL,
        EXTRACT(EPOCH FROM now() - l.ts)::int,
        CASE WHEN t.last_w - t.first_w > 2 THEN 'rising'
             WHEN t.first_w - t.last_w > 2 THEN 'falling'
             ELSE 'stable' END
    FROM latest l, trend t
)
SELECT u.zone, u.moisture, u.temp, u.ec, u.age_s, u.trend,
    t.min_pct, t.max_pct, t.crop,
    CASE
        WHEN u.moisture IS NULL THEN 'offline'
        WHEN u.moisture < t.wilt_pct THEN 'critical_dry'
        WHEN u.moisture < t.min_pct THEN 'dry'
        WHEN u.moisture > t.saturation_pct THEN 'saturated'
        WHEN u.moisture > t.max_pct THEN 'wet'
        ELSE 'ok'
    END AS status
FROM unpivoted u
LEFT JOIN soil_moisture_targets t ON u.zone = t.zone;
