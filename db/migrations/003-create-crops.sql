-- Migration 003: Create crops table (P0)
-- The keystone table. Every crop-related metric chains back here.

CREATE TABLE IF NOT EXISTS crops (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    variety         TEXT,
    position        TEXT NOT NULL,     -- shelf taxonomy: SOUTH-SHELF-3, EAST-HYDRO-A-1
    zone            TEXT NOT NULL,     -- cardinal: north, south, east, west, center
    planted_date    DATE NOT NULL,
    expected_harvest DATE,
    stage           TEXT DEFAULT 'seed',
    count           INT,
    seed_lot_id     TEXT,
    supplier        TEXT,
    base_temp_f     FLOAT DEFAULT 50.0,
    target_dli      FLOAT,
    target_vpd_low  FLOAT,
    target_vpd_high FLOAT,
    notes           TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_crops_active ON crops(is_active, zone);

-- Valid stages: seed, germinating, seedling, vegetative, flowering, fruiting,
--               harvest_ready, harvested, removed, failed
