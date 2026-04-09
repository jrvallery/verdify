-- Migration 014: Add energy and grow light columns to daily_summary
-- All NULLable — pending CT clamp and grow light integration.

ALTER TABLE daily_summary ADD COLUMN IF NOT EXISTS kwh_total              FLOAT;
ALTER TABLE daily_summary ADD COLUMN IF NOT EXISTS kwh_heat               FLOAT;
ALTER TABLE daily_summary ADD COLUMN IF NOT EXISTS kwh_fans               FLOAT;
ALTER TABLE daily_summary ADD COLUMN IF NOT EXISTS kwh_other              FLOAT;
ALTER TABLE daily_summary ADD COLUMN IF NOT EXISTS peak_kw                FLOAT;
ALTER TABLE daily_summary ADD COLUMN IF NOT EXISTS gas_used_therms        FLOAT;
ALTER TABLE daily_summary ADD COLUMN IF NOT EXISTS runtime_grow_light_min FLOAT;
ALTER TABLE daily_summary ADD COLUMN IF NOT EXISTS cycles_grow_light      INT;
