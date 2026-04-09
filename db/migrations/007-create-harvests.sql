-- Migration 007: Create harvests table (P0)
-- Every harvest event. Denominator for all efficiency metrics (kWh/kg, gal/kg, $/kg).

CREATE TABLE IF NOT EXISTS harvests (
    id            SERIAL PRIMARY KEY,
    ts            TIMESTAMPTZ DEFAULT now(),
    crop_id       INT REFERENCES crops(id),
    weight_kg     FLOAT,
    unit_count    INT,
    quality_grade TEXT,
    zone          TEXT,
    destination   TEXT,
    unit_price    FLOAT,
    revenue       FLOAT,
    operator      TEXT,
    notes         TEXT
);
