-- Migration 005: Create observations table (P0)
-- Timestamped field observations: pest scouting, disease, growth notes.

CREATE TABLE IF NOT EXISTS observations (
    id           SERIAL PRIMARY KEY,
    ts           TIMESTAMPTZ DEFAULT now(),
    obs_type     TEXT NOT NULL,
    zone         TEXT,
    position     TEXT,        -- shelf taxonomy reference
    severity     INT CHECK(severity BETWEEN 1 AND 5),
    species      TEXT,
    count        INT,
    affected_pct FLOAT,
    crop_id      INT REFERENCES crops(id),
    photo_path   TEXT,        -- relative path in Obsidian vault
    observer     TEXT,        -- 'emily', 'jason', 'verdify-agent', 'camera'
    source       TEXT DEFAULT 'manual',
    notes        TEXT
);

CREATE INDEX IF NOT EXISTS idx_obs_ts ON observations(ts DESC);
CREATE INDEX IF NOT EXISTS idx_obs_type ON observations(obs_type, zone, ts);

-- Valid obs_types: pest, disease, growth, environmental, beneficial_insect,
--                  general, camera_assessment
