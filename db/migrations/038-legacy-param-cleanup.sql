-- Migration 038: Remove legacy parameter names from setpoint_changes
-- These are historical artifacts from pre-alignment naming.
-- Canonical names already exist for all of these (migration 035 renamed active data).
-- This deletes the remaining stale entries that weren't caught by 035.

DELETE FROM setpoint_changes WHERE parameter = 'd_cool_s2';
DELETE FROM setpoint_changes WHERE parameter = 'd_heat_s2';
DELETE FROM setpoint_changes WHERE parameter = 'fallback_window';
DELETE FROM setpoint_changes WHERE parameter = 'lead_rotate_timeout';
DELETE FROM setpoint_changes WHERE parameter = 'min_fan_off';
DELETE FROM setpoint_changes WHERE parameter = 'min_fan_on';
DELETE FROM setpoint_changes WHERE parameter = 'min_heat_on';
DELETE FROM setpoint_changes WHERE parameter = 'min_heat_off';
DELETE FROM setpoint_changes WHERE parameter = 'min_vent_off';
DELETE FROM setpoint_changes WHERE parameter = 'min_vent_on';
DELETE FROM setpoint_changes WHERE parameter = 'site_pressure';
DELETE FROM setpoint_changes WHERE parameter = 'temp_hyst';
DELETE FROM setpoint_changes WHERE parameter = 'vpd_hyst';
