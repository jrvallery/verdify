-- Migration 020: Runtime Costs — equipment specs + computed cost columns + backfill
-- Rate constants: electric $0.111/kWh, gas $1.20/therm, water $0.01192/gal

-- 1. Populate equipment_assets with canonical specs
INSERT INTO equipment_assets (equipment, description, wattage, btu_rating) VALUES
  ('heat1', 'Primary electric heater', 1500, NULL),
  ('heat2', 'Secondary gas heater', NULL, 30000),
  ('fan1', 'Circulation fan 1', 150, NULL),
  ('fan2', 'Circulation fan 2', 150, NULL),
  ('fog', 'Fog machine', 200, NULL),
  ('vent', 'Ventilation gate', 10, NULL),
  ('grow_light_main', 'Grow light main (Lutron)', 300, NULL),
  ('grow_light_grow', 'Grow light grow (Lutron)', 300, NULL)
ON CONFLICT (equipment) DO UPDATE SET
  description = EXCLUDED.description,
  wattage = EXCLUDED.wattage,
  btu_rating = EXCLUDED.btu_rating;

-- 2. Add computed cost columns to daily_summary
ALTER TABLE daily_summary ADD COLUMN IF NOT EXISTS kwh_estimated      FLOAT;
ALTER TABLE daily_summary ADD COLUMN IF NOT EXISTS therms_estimated   FLOAT;
ALTER TABLE daily_summary ADD COLUMN IF NOT EXISTS cost_electric      FLOAT;
ALTER TABLE daily_summary ADD COLUMN IF NOT EXISTS cost_gas           FLOAT;
ALTER TABLE daily_summary ADD COLUMN IF NOT EXISTS cost_water         FLOAT;
ALTER TABLE daily_summary ADD COLUMN IF NOT EXISTS cost_total         FLOAT;

-- 3. Backfill computed costs for all days
-- Electric: heat1(1500W) + fan1+fan2(150W ea) + fog(200W) + vent(10W)
-- Gas: heat2 at 30000 BTU/hr → therms (÷100000)
-- Water: water_used_gal × $0.01192/gal
UPDATE daily_summary SET
  kwh_estimated = ROUND((
    COALESCE(runtime_heat1_min, 0) / 60.0 * 1.5 +
    COALESCE(runtime_fan1_min, 0) / 60.0 * 0.15 +
    COALESCE(runtime_fan2_min, 0) / 60.0 * 0.15 +
    COALESCE(runtime_fog_min, 0) / 60.0 * 0.2 +
    COALESCE(runtime_vent_min, 0) / 60.0 * 0.01
  )::numeric, 3),
  therms_estimated = ROUND((
    COALESCE(runtime_heat2_min, 0) / 60.0 * 30000.0 / 100000.0
  )::numeric, 4),
  cost_electric = ROUND((
    (COALESCE(runtime_heat1_min, 0) / 60.0 * 1.5 +
     COALESCE(runtime_fan1_min, 0) / 60.0 * 0.15 +
     COALESCE(runtime_fan2_min, 0) / 60.0 * 0.15 +
     COALESCE(runtime_fog_min, 0) / 60.0 * 0.2 +
     COALESCE(runtime_vent_min, 0) / 60.0 * 0.01) * 0.111
  )::numeric, 2),
  cost_gas = ROUND((
    COALESCE(runtime_heat2_min, 0) / 60.0 * 30000.0 / 100000.0 * 1.20
  )::numeric, 2),
  cost_water = ROUND((
    COALESCE(water_used_gal, 0) * 0.01192
  )::numeric, 2),
  cost_total = ROUND((
    (COALESCE(runtime_heat1_min, 0) / 60.0 * 1.5 +
     COALESCE(runtime_fan1_min, 0) / 60.0 * 0.15 +
     COALESCE(runtime_fan2_min, 0) / 60.0 * 0.15 +
     COALESCE(runtime_fog_min, 0) / 60.0 * 0.2 +
     COALESCE(runtime_vent_min, 0) / 60.0 * 0.01) * 0.111 +
    COALESCE(runtime_heat2_min, 0) / 60.0 * 30000.0 / 100000.0 * 1.20 +
    COALESCE(water_used_gal, 0) * 0.01192
  )::numeric, 2);
