-- Migration 030: Create utility_cost + consumables_log tables
-- Epic: E-OWN-01 (Cost Tracking Pipeline)

-- Table 1: Monthly utility costs by category
CREATE TABLE IF NOT EXISTS utility_cost (
    id          SERIAL PRIMARY KEY,
    month       DATE NOT NULL,
    category    TEXT NOT NULL CHECK (category IN ('electric', 'water', 'propane', 'other')),
    amount_usd  NUMERIC(10,2) NOT NULL,
    kwh         NUMERIC(10,2),
    gallons     NUMERIC(10,2),
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (month, category)
);

CREATE INDEX IF NOT EXISTS idx_utility_cost_month ON utility_cost (month);
CREATE TRIGGER trg_utility_cost_updated_at BEFORE UPDATE ON utility_cost
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE utility_cost IS 'Monthly utility bills by category. One row per month per utility type.';

-- Table 2: Individual consumable purchases
CREATE TABLE IF NOT EXISTS consumables_log (
    id              SERIAL PRIMARY KEY,
    purchased_date  DATE NOT NULL,
    category        TEXT NOT NULL CHECK (category IN ('soil', 'nutrients', 'seeds', 'parts', 'containers', 'other')),
    item_name       TEXT NOT NULL,
    quantity        NUMERIC(10,2),
    unit            TEXT,
    cost_usd        NUMERIC(10,2) NOT NULL,
    zone            TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_consumables_date ON consumables_log (purchased_date DESC);
CREATE INDEX IF NOT EXISTS idx_consumables_category ON consumables_log (category, purchased_date DESC);

COMMENT ON TABLE consumables_log IS 'Greenhouse supply purchases. Seeds, soil, nutrients, parts, containers.';
