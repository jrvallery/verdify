-- 075-greenhouses-registry.sql
-- Multi-tenant foundation: greenhouses registry + greenhouse_id on core tables

-- The tenant table
CREATE TABLE IF NOT EXISTS greenhouses (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_email TEXT,
    timezone TEXT NOT NULL DEFAULT 'America/Denver',
    latitude FLOAT,
    longitude FLOAT,
    elevation_ft FLOAT,
    esp32_host TEXT,
    esp32_port INT DEFAULT 6053,
    esp32_api_key TEXT,
    mqtt_topic TEXT,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'provisioning')),
    config JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Seed with the Vallery greenhouse
INSERT INTO greenhouses (id, name, owner_email, timezone, latitude, longitude, elevation_ft,
    esp32_host, esp32_port, mqtt_topic, config)
VALUES (
    'vallery', 'Vallery Greenhouse', 'jason@vallery.net', 'America/Denver',
    40.1672, -105.1019, 4979,
    '192.168.10.111', 6053,
    'greenhouse/vallery',
    '{"area_sqft": 367, "volume_cuft": 3614, "glazing": "Gallina PoliCarb 2P 6mm Opal",
      "wall_height_in": 96, "peak_height_in": 143, "fan_cfm": 4900}'::jsonb
) ON CONFLICT (id) DO NOTHING;

-- Add greenhouse_id to core tables (default = 'vallery' so nothing breaks)
ALTER TABLE climate ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE equipment_state ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE setpoint_changes ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE setpoint_plan ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE diagnostics ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE daily_summary ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE system_state ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE energy ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE alert_log ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE crops ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE observations ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE crop_events ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE image_observations ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE setpoint_snapshot ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE plan_journal ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE planner_lessons ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE weather_forecast ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE forecast_action_log ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE forecast_deviation_log ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE model_predictions ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE soil_moisture_targets ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE camera_zone_map ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);

-- Indexes for tenant isolation (on high-volume tables only)
CREATE INDEX IF NOT EXISTS idx_climate_ghid ON climate (greenhouse_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_equipment_ghid ON equipment_state (greenhouse_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_setpoint_changes_ghid ON setpoint_changes (greenhouse_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_daily_summary_ghid ON daily_summary (greenhouse_id, date);
CREATE INDEX IF NOT EXISTS idx_crops_ghid ON crops (greenhouse_id, is_active);
