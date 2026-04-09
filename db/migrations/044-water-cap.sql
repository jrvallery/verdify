-- Migration 044: Cap v_water_daily at 200 gal/day to handle counter resets
-- Problem: cumulative counter jumps (e.g., 4 → 3894 on Jan 5) produce phantom usage.
-- Fix: cap daily delta at 200 gal (physical max for this greenhouse).

CREATE OR REPLACE VIEW v_water_daily AS
SELECT day,
  CASE WHEN used_gal > 200 THEN NULL  -- counter reset day, discard
       ELSE used_gal
  END AS used_gal
FROM (
  SELECT date_trunc('day', ts) AS day,
    max(water_total_gal) - min(water_total_gal) AS used_gal
  FROM climate
  WHERE water_total_gal IS NOT NULL AND water_total_gal > 0
  GROUP BY date_trunc('day', ts)
) sub
ORDER BY day DESC;

COMMENT ON VIEW v_water_daily IS 'Daily water usage from cumulative pulse counter. Nulls days with >200 gal delta (counter reset artifacts).';
