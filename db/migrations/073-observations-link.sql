-- 073-observations-link.sql
-- Link observations table to image_observations for visual health tracking

ALTER TABLE observations ADD COLUMN IF NOT EXISTS image_observation_id INT REFERENCES image_observations(id);
ALTER TABLE observations ADD COLUMN IF NOT EXISTS health_score FLOAT;
ALTER TABLE observations ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'manual';

CREATE INDEX IF NOT EXISTS idx_observations_crop ON observations (crop_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_observations_source ON observations (source, ts DESC);

-- View: per-crop health trend (7-day rolling)
CREATE OR REPLACE VIEW v_crop_health_trend AS
SELECT
    c.name AS crop_name,
    c.zone,
    o.ts AT TIME ZONE 'America/Denver' AS observed,
    o.health_score,
    o.type AS observation_type,
    o.notes,
    o.source
FROM observations o
JOIN crops c ON o.crop_id = c.id
WHERE o.ts > now() - interval '30 days'
ORDER BY c.name, o.ts DESC;
