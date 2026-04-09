-- Migration 010: Create equipment_assets + maintenance_log tables (P2)
-- Enables preventive maintenance tracking.

CREATE TABLE IF NOT EXISTS equipment_assets (
    id           SERIAL PRIMARY KEY,
    equipment    TEXT UNIQUE NOT NULL,  -- matches equipment_state.equipment values
    description  TEXT,
    model        TEXT,
    serial_no    TEXT,
    install_date DATE,
    warranty_exp DATE,
    wattage      FLOAT,    -- actual rated watts (replaces $watt_* template vars)
    btu_rating   FLOAT,
    notes        TEXT
);

CREATE TABLE IF NOT EXISTS maintenance_log (
    id           SERIAL PRIMARY KEY,
    ts           TIMESTAMPTZ DEFAULT now(),
    equipment    TEXT REFERENCES equipment_assets(equipment),
    service_type TEXT,
    description  TEXT,
    cost         FLOAT,
    technician   TEXT,
    next_due     DATE,
    notes        TEXT
);
