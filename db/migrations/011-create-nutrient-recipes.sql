-- Migration 011: Create nutrient_recipes table (P2)
-- Enables recipe vs. actual comparison for fertigation.

CREATE TABLE IF NOT EXISTS nutrient_recipes (
    id               SERIAL PRIMARY KEY,
    name             TEXT NOT NULL,
    crop_id          INT REFERENCES crops(id),
    stage            TEXT,
    target_ec        FLOAT,
    target_ph_low    FLOAT,
    target_ph_high   FLOAT,
    n_ppm            FLOAT,
    p_ppm            FLOAT,
    k_ppm            FLOAT,
    ca_ppm           FLOAT,
    mg_ppm           FLOAT,
    fe_ppm           FLOAT,
    stock_a_ml_per_l FLOAT,
    stock_b_ml_per_l FLOAT,
    notes            TEXT,
    is_active        BOOLEAN DEFAULT TRUE,
    created_at       TIMESTAMPTZ DEFAULT now()
);
