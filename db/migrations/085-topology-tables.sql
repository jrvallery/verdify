-- 085-topology-tables.sql — Sprint 22 Phase 2
--
-- Promotes physical + logical topology to first-class tables:
--
--   Greenhouse (existing)
--     └── Zone
--         ├── Shelf
--         │   └── Position
--         ├── Sensor
--         ├── Equipment
--         │   └── Switch
--         └── WaterSystem
--     └── PressureGroup (greenhouse-scoped, but groups systems across zones)
--
--   CropCatalog (reference data, greenhouse-scoped to allow per-tenant varieties)
--
-- Prior to Sprint 22, zones / positions / sensors / equipment / switches were
-- encoded as text fields on other tables and hand-typed markdown tables. This
-- migration creates the structural spine. Sprint 22 Phase 3 (import script)
-- populates these tables from vault markdown; Phase 4 wires callers.
--
-- All tables require greenhouse_id (no default) — Sprint 22 is multi-tenant-ready.
-- Everything is additive; no existing table is modified by this migration.

BEGIN;

-- ── Zones ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS zones (
    id              SERIAL PRIMARY KEY,
    greenhouse_id   TEXT NOT NULL REFERENCES greenhouses(id),
    slug            TEXT NOT NULL CHECK (slug ~ '^[a-z][a-z0-9_]*$'),
    name            TEXT NOT NULL,
    orientation     TEXT,
    sensor_modbus_addr INT CHECK (sensor_modbus_addr BETWEEN 1 AND 247),
    peak_temp_f     DOUBLE PRECISION,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'offline', 'decommissioned')),
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (greenhouse_id, slug)
);
COMMENT ON TABLE zones IS
    'Sprint 22: physical zones (south/north/east/west/center). Replaces free-text `zone` columns on crops/observations/alert_log with FK targets.';
CREATE INDEX IF NOT EXISTS idx_zones_ghid ON zones (greenhouse_id, status);


-- ── Shelves ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS shelves (
    id              SERIAL PRIMARY KEY,
    greenhouse_id   TEXT NOT NULL REFERENCES greenhouses(id),
    zone_id         INT NOT NULL REFERENCES zones(id) ON DELETE RESTRICT,
    slug            TEXT NOT NULL CHECK (slug ~ '^[a-z][a-z0-9_]*$'),
    name            TEXT NOT NULL,
    kind            TEXT NOT NULL
                    CHECK (kind IN ('floor','shelf','hang','rack','nft','hydro')),
    tier            INT CHECK (tier >= 0),
    position_scheme TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (greenhouse_id, slug)
);
COMMENT ON TABLE shelves IS
    'Sprint 22: structural sub-regions within a zone (south_floor, south_shelf_top, center_hang, east_nft). Never free-text.';
CREATE INDEX IF NOT EXISTS idx_shelves_zone ON shelves (zone_id);


-- ── Positions ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS positions (
    id              SERIAL PRIMARY KEY,
    greenhouse_id   TEXT NOT NULL REFERENCES greenhouses(id),
    shelf_id        INT NOT NULL REFERENCES shelves(id) ON DELETE RESTRICT,
    label           TEXT NOT NULL CHECK (label ~ '^[A-Z][A-Z0-9_\-]*[A-Z0-9]$'),
    slot_number     INT CHECK (slot_number >= 1),
    mount_type      TEXT NOT NULL
                    CHECK (mount_type IN
                        ('pot','shelf_slot','hanging_hook','nft_port','hydro_raft','direct_ground')),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (greenhouse_id, label)
);
COMMENT ON TABLE positions IS
    'Sprint 22: individual planting slots. FK target for crops.position_id and observations.position_id. Label follows UPPER-SNAKE (SOUTH-FLOOR-1).';
CREATE INDEX IF NOT EXISTS idx_positions_shelf ON positions (shelf_id, is_active);


-- ── Sensors ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sensors (
    id              SERIAL PRIMARY KEY,
    greenhouse_id   TEXT NOT NULL REFERENCES greenhouses(id),
    slug            TEXT NOT NULL CHECK (slug ~ '^[a-z][a-z0-9_.]*$'),
    zone_id         INT REFERENCES zones(id) ON DELETE SET NULL,
    position_id     INT REFERENCES positions(id) ON DELETE SET NULL,
    kind            TEXT NOT NULL
                    CHECK (kind IN
                        ('climate_probe','soil_probe','co2','light','flow',
                         'hydro_quality','weather','energy','camera','leaf',
                         'pressure','derived')),
    protocol        TEXT NOT NULL
                    CHECK (protocol IN
                        ('modbus_rtu','adc','gpio_pulse','ble','http_api','mqtt',
                         'esphome_native','frigate','derived')),
    model           TEXT,
    modbus_addr     INT CHECK (modbus_addr BETWEEN 1 AND 247),
    gpio_pin        INT CHECK (gpio_pin BETWEEN 0 AND 64),
    unit            TEXT,
    source_table    TEXT,
    source_column   TEXT,
    expected_interval_s INT CHECK (expected_interval_s >= 1),
    accuracy        TEXT,
    installed_date  DATE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (greenhouse_id, slug)
);
COMMENT ON TABLE sensors IS
    'Sprint 22: replaces sensor_registry with proper zone/position FKs. sensor_registry stays as a legacy mirror until Phase 6.';
CREATE INDEX IF NOT EXISTS idx_sensors_zone ON sensors (zone_id, is_active);


-- ── Pressure groups (water manifold constraints) ────────────────────────

CREATE TABLE IF NOT EXISTS pressure_groups (
    id              SERIAL PRIMARY KEY,
    greenhouse_id   TEXT NOT NULL REFERENCES greenhouses(id),
    slug            TEXT NOT NULL CHECK (slug ~ '^[a-z][a-z0-9_]*$'),
    name            TEXT NOT NULL,
    constraint_kind TEXT NOT NULL
                    CHECK (constraint_kind IN
                        ('mister_max_1','drip_max_1','mister_max_2','none')),
    max_concurrent  INT NOT NULL DEFAULT 1 CHECK (max_concurrent BETWEEN 1 AND 8),
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (greenhouse_id, slug)
);
COMMENT ON TABLE pressure_groups IS
    'Sprint 22: water manifold constraint clusters. Encodes "only one mister zone at a time" as relational data instead of firmware-only rule.';


-- ── Equipment ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS equipment (
    id                 SERIAL PRIMARY KEY,
    greenhouse_id      TEXT NOT NULL REFERENCES greenhouses(id),
    slug               TEXT NOT NULL CHECK (slug ~ '^[a-z][a-z0-9_]*$'),
    zone_id            INT REFERENCES zones(id) ON DELETE SET NULL,
    kind               TEXT NOT NULL
                       CHECK (kind IN
                           ('heater','fan','vent','fog','mister','drip','valve',
                            'light','pump','heater_water','sensor_bridge',
                            'controller','camera')),
    name               TEXT NOT NULL,
    model              TEXT,
    manufacturer       TEXT,
    watts              DOUBLE PRECISION CHECK (watts >= 0),
    cost_per_hour_usd  DOUBLE PRECISION CHECK (cost_per_hour_usd >= 0),
    specs              JSONB NOT NULL DEFAULT '{}'::jsonb,
    install_date       DATE,
    is_active          BOOLEAN NOT NULL DEFAULT TRUE,
    notes              TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (greenhouse_id, slug)
);
COMMENT ON TABLE equipment IS
    'Sprint 22: canonical equipment catalog. slug matches telemetry.EquipmentId Literal (mister_south, fan1, heat2, etc.). Replaces equipment_assets as the primary reference table.';
CREATE INDEX IF NOT EXISTS idx_equipment_zone ON equipment (zone_id, is_active);
CREATE INDEX IF NOT EXISTS idx_equipment_kind ON equipment (greenhouse_id, kind);


-- ── Switches (relay pin assignments) ────────────────────────────────────

CREATE TABLE IF NOT EXISTS switches (
    id                   SERIAL PRIMARY KEY,
    greenhouse_id        TEXT NOT NULL REFERENCES greenhouses(id),
    slug                 TEXT NOT NULL CHECK (slug ~ '^[a-z][a-z0-9_]*\.\d+$'),
    equipment_id         INT REFERENCES equipment(id) ON DELETE SET NULL,
    board                TEXT NOT NULL
                         CHECK (board IN ('pcf_out_1','pcf_out_2','pcf_in','gpio')),
    pin                  INT NOT NULL CHECK (pin BETWEEN 0 AND 15),
    purpose              TEXT NOT NULL,
    state_source_column  TEXT,
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    notes                TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (greenhouse_id, board, pin),
    UNIQUE (greenhouse_id, slug)
);
COMMENT ON TABLE switches IS
    'Sprint 22: PCF8574 + GPIO pin assignments. Replaces the hand-typed relay map in website/greenhouse/equipment.md. slug = "<board>.<pin>" (e.g., pcf_out_1.3).';
CREATE INDEX IF NOT EXISTS idx_switches_equipment ON switches (equipment_id);


-- ── Water systems ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS water_systems (
    id                  SERIAL PRIMARY KEY,
    greenhouse_id       TEXT NOT NULL REFERENCES greenhouses(id),
    slug                TEXT NOT NULL CHECK (slug ~ '^[a-z][a-z0-9_]*$'),
    zone_id             INT REFERENCES zones(id) ON DELETE SET NULL,
    equipment_id        INT REFERENCES equipment(id) ON DELETE SET NULL,
    pressure_group_id   INT REFERENCES pressure_groups(id) ON DELETE SET NULL,
    kind                TEXT NOT NULL
                        CHECK (kind IN ('mister','drip','fog','fertigation','nft','manual')),
    name                TEXT NOT NULL,
    nozzle_count        INT CHECK (nozzle_count >= 0),
    head_count          INT CHECK (head_count >= 0),
    mount               TEXT,
    is_fert_path        BOOLEAN NOT NULL DEFAULT FALSE,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    effectiveness_note  TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (greenhouse_id, slug)
);
COMMENT ON TABLE water_systems IS
    'Sprint 22: mister/drip/fog systems with head/nozzle counts + pressure group FK. Gives the planner a queryable model of the water manifold.';
CREATE INDEX IF NOT EXISTS idx_water_systems_pg ON water_systems (pressure_group_id);
CREATE INDEX IF NOT EXISTS idx_water_systems_zone ON water_systems (zone_id);


-- ── Crop catalog ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS crop_catalog (
    id                          SERIAL PRIMARY KEY,
    slug                        TEXT NOT NULL UNIQUE
                                CHECK (slug ~ '^[a-z][a-z0-9_]*$'),
    common_name                 TEXT NOT NULL,
    scientific_name             TEXT,
    category                    TEXT NOT NULL
                                CHECK (category IN
                                    ('fruit','leafy_green','herb','flower','root',
                                     'legume','brassica','ornamental','tropical','vine')),
    season                      TEXT NOT NULL
                                CHECK (season IN
                                    ('cool','warm','hot','year_round','short_day','long_day')),
    cycle_days_min              INT CHECK (cycle_days_min >= 0),
    cycle_days_max              INT CHECK (cycle_days_max >= 0),
    base_temp_f                 DOUBLE PRECISION DEFAULT 50.0,
    default_target_dli          DOUBLE PRECISION CHECK (default_target_dli >= 0),
    default_target_vpd_low      DOUBLE PRECISION CHECK (default_target_vpd_low BETWEEN 0 AND 20),
    default_target_vpd_high     DOUBLE PRECISION CHECK (default_target_vpd_high BETWEEN 0 AND 20),
    default_ph_low              DOUBLE PRECISION CHECK (default_ph_low BETWEEN 0 AND 14),
    default_ph_high             DOUBLE PRECISION CHECK (default_ph_high BETWEEN 0 AND 14),
    default_ec_low              DOUBLE PRECISION CHECK (default_ec_low >= 0),
    default_ec_high             DOUBLE PRECISION CHECK (default_ec_high >= 0),
    notes                       TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE crop_catalog IS
    'Sprint 22: reference table for crop types. Promotes crops.name + crop_target_profiles.crop_type from free text to a typed FK target.';


COMMIT;
