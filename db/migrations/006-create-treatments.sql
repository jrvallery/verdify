-- Migration 006: Create treatments table (P0)
-- Every spray, biological release, or treatment application.

CREATE TABLE IF NOT EXISTS treatments (
    id                SERIAL PRIMARY KEY,
    ts                TIMESTAMPTZ DEFAULT now(),
    product           TEXT NOT NULL,
    active_ingredient TEXT,
    concentration     FLOAT,
    rate              FLOAT,
    rate_unit         TEXT,
    method            TEXT,
    zone              TEXT,
    crop_id           INT REFERENCES crops(id),
    target_pest       TEXT,
    phi_days          INT,       -- pre-harvest interval
    rei_hours         INT,       -- restricted entry interval
    applicator        TEXT,
    observation_id    INT REFERENCES observations(id),
    notes             TEXT
);

CREATE INDEX IF NOT EXISTS idx_treatments_ts ON treatments(ts DESC);
CREATE INDEX IF NOT EXISTS idx_treatments_phi ON treatments(crop_id, ts)
    WHERE phi_days IS NOT NULL;
