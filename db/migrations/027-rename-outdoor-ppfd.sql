-- Migration 027: Rename outdoor_ppfd → outdoor_lux
-- The column stores Tempest illuminance in lux, not PPFD in µmol/m²/s.
-- The name "outdoor_ppfd" is misleading and causes confusion in dashboards.

-- Step 1: Rename the column
ALTER TABLE climate RENAME COLUMN outdoor_ppfd TO outdoor_lux;

-- Step 2: Update sensor_registry
UPDATE sensor_registry
SET sensor_id = 'climate.outdoor_lux',
    source_column = 'outdoor_lux',
    description = 'Tempest/Panorama illuminance (lux). Rooftop weather station. NOT PPFD — this is human-visible light, not PAR.'
WHERE sensor_id = 'climate.outdoor_ppfd';

-- Step 3: Recreate v_light_transmission with new column name
CREATE OR REPLACE VIEW v_light_transmission AS
SELECT
  time_bucket('5 minutes', c.ts) AS ts,
  AVG(c.lux) AS indoor_lux,
  AVG(o.outdoor_lux) AS outdoor_lux,
  CASE WHEN AVG(o.outdoor_lux) > 0
    THEN ROUND((AVG(c.lux) / AVG(o.outdoor_lux) * 100)::numeric, 1)
  END AS transmission_pct
FROM climate c
JOIN climate o ON time_bucket('5 minutes', c.ts) = time_bucket('5 minutes', o.ts)
WHERE c.lux IS NOT NULL AND o.outdoor_lux IS NOT NULL AND o.outdoor_lux > 0
GROUP BY 1;

-- Step 4: Update staleness view CASE to use new column name
-- (Will be handled by recreating the full view in the next statement)
