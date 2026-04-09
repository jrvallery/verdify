-- 072-image-observations.sql
-- Greenhouse Intelligence System v1 — image analysis + model predictions

-- Gemini Vision analysis results per snapshot
CREATE TABLE IF NOT EXISTS image_observations (
    id SERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    camera TEXT NOT NULL,
    zone TEXT NOT NULL,
    image_path TEXT NOT NULL,
    model TEXT DEFAULT 'gemini-2.0-flash',
    raw_response JSONB,
    crops_observed JSONB,
    environment_notes TEXT,
    recommended_actions TEXT[],
    processing_ms INT,
    tokens_used INT,
    confidence FLOAT
);
CREATE INDEX IF NOT EXISTS idx_imgobs_ts ON image_observations (ts DESC);
CREATE INDEX IF NOT EXISTS idx_imgobs_zone ON image_observations (zone, ts DESC);

-- GreenLight model predictions vs actual sensor data
CREATE TABLE IF NOT EXISTS model_predictions (
    ts TIMESTAMPTZ NOT NULL,
    predicted_temp_f FLOAT,
    predicted_rh_pct FLOAT,
    actual_temp_f FLOAT,
    actual_rh_pct FLOAT,
    temp_deviation FLOAT,
    rh_deviation FLOAT,
    model_version TEXT DEFAULT 'greenlight-2.0',
    weather_source TEXT DEFAULT 'open-meteo'
);
SELECT create_hypertable('model_predictions', 'ts', if_not_exists => TRUE);

-- Camera-to-zone mapping
CREATE TABLE IF NOT EXISTS camera_zone_map (
    camera TEXT NOT NULL,
    zone TEXT NOT NULL,
    coverage_pct INT DEFAULT 100,
    notes TEXT,
    PRIMARY KEY (camera, zone)
);

-- Seed camera-zone mapping
INSERT INTO camera_zone_map (camera, zone, coverage_pct, notes) VALUES
    ('greenhouse_1', 'south', 80, 'Main camera — good view of south wall + floor pots'),
    ('greenhouse_1', 'center', 60, 'Partial view of center benches + hanging orchids'),
    ('greenhouse_1', 'west', 30, 'Edge view of west shelving'),
    ('greenhouse_2', 'east', 80, 'Secondary camera — hydro racks + east shelves'),
    ('greenhouse_2', 'west', 50, 'Good view of west wall shelving'),
    ('greenhouse_2', 'north', 40, 'Partial view of north equipment area')
ON CONFLICT DO NOTHING;

-- View: latest observations per zone
CREATE OR REPLACE VIEW v_latest_observations AS
SELECT DISTINCT ON (zone)
    zone, ts, camera, confidence,
    crops_observed,
    environment_notes,
    recommended_actions
FROM image_observations
ORDER BY zone, ts DESC;
