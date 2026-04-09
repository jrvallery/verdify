-- 058-canonical-param-names.sql
-- Fix dual-name parameter oscillation (Bug #1-#2)
--
-- Problem: planner and reactive-planner write different names for the same ESP32 tunable.
-- v_active_plan treats them as distinct, causing the dispatcher to oscillate between values.
--
-- Solution: normalize all parameter names to canonical DB names in both setpoint_plan
-- and setpoint_changes. Add a trigger to auto-normalize on INSERT.

-- Alias map: non-canonical → canonical
-- These are ESP32 object_ids that should have been written as DB parameter names
CREATE OR REPLACE FUNCTION normalize_param_name(p TEXT) RETURNS TEXT AS $$
BEGIN
    RETURN CASE p
        WHEN 'set_vpd_high_kpa' THEN 'vpd_high'
        WHEN 'set_vpd_low_kpa' THEN 'vpd_low'
        WHEN 'set_temp_low__f' THEN 'temp_low'
        WHEN 'set_temp_high__f' THEN 'temp_high'
        WHEN 'vpd_mister_engage_kpa' THEN 'mister_engage_kpa'
        WHEN 'vpd_mister_all_kpa' THEN 'mister_all_kpa'
        ELSE p
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Normalize existing data in setpoint_plan
UPDATE setpoint_plan SET parameter = normalize_param_name(parameter)
WHERE parameter IN ('set_vpd_high_kpa', 'set_vpd_low_kpa', 'set_temp_low__f', 'set_temp_high__f', 'vpd_mister_engage_kpa', 'vpd_mister_all_kpa');

-- Normalize existing data in setpoint_changes
UPDATE setpoint_changes SET parameter = normalize_param_name(parameter)
WHERE parameter IN ('set_vpd_high_kpa', 'set_vpd_low_kpa', 'set_temp_low__f', 'set_temp_high__f', 'vpd_mister_engage_kpa', 'vpd_mister_all_kpa');

-- Auto-normalize trigger on setpoint_plan INSERT
CREATE OR REPLACE FUNCTION normalize_plan_param() RETURNS trigger AS $$
BEGIN
    NEW.parameter := normalize_param_name(NEW.parameter);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_normalize_plan_param ON setpoint_plan;
CREATE TRIGGER trg_normalize_plan_param
    BEFORE INSERT ON setpoint_plan
    FOR EACH ROW EXECUTE FUNCTION normalize_plan_param();

-- Auto-normalize trigger on setpoint_changes INSERT
CREATE OR REPLACE FUNCTION normalize_changes_param() RETURNS trigger AS $$
BEGIN
    NEW.parameter := normalize_param_name(NEW.parameter);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_normalize_changes_param ON setpoint_changes;
CREATE TRIGGER trg_normalize_changes_param
    BEFORE INSERT ON setpoint_changes
    FOR EACH ROW EXECUTE FUNCTION normalize_changes_param();
