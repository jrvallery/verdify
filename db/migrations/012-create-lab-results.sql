-- Migration 012: Create lab_results table (P2)
-- Manual entry from lab reports (soil, water, tissue analysis).

CREATE TABLE IF NOT EXISTS lab_results (
    id          SERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ DEFAULT now(),
    sample_type TEXT NOT NULL,
    zone        TEXT,
    crop_id     INT REFERENCES crops(id),
    lab_name    TEXT,
    sampled_at  DATE,
    ph          FLOAT,
    ec_ms_cm    FLOAT,
    n_pct       FLOAT,  p_pct  FLOAT,  k_pct  FLOAT,
    ca_pct      FLOAT,  mg_pct FLOAT,  fe_ppm FLOAT,
    mn_ppm      FLOAT,  zn_ppm FLOAT,  b_ppm  FLOAT,
    cu_ppm      FLOAT,  na_ppm FLOAT,  cl_ppm FLOAT,
    notes       TEXT
);
