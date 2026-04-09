-- Migration 035: Align setpoint parameter names across ingestor ↔ dispatcher
-- The dispatcher (Iris planning) uses canonical names; the ingestor historically
-- used different abbreviations. This renames all historical data to match.

BEGIN;

UPDATE setpoint_changes SET parameter = 'd_heat_stage_2' WHERE parameter = 'heat_stage2_delta';
UPDATE setpoint_changes SET parameter = 'd_cool_stage_2' WHERE parameter = 'cool_stage2_delta';
UPDATE setpoint_changes SET parameter = 'safety_min' WHERE parameter = 'safety_temp_min';
UPDATE setpoint_changes SET parameter = 'safety_max' WHERE parameter = 'safety_temp_max';
UPDATE setpoint_changes SET parameter = 'min_heat_on_s' WHERE parameter = 'heat_min_on_s';
UPDATE setpoint_changes SET parameter = 'min_heat_off_s' WHERE parameter = 'heat_min_off_s';
UPDATE setpoint_changes SET parameter = 'min_fan_on_s' WHERE parameter = 'fan_min_on_s';
UPDATE setpoint_changes SET parameter = 'min_fan_off_s' WHERE parameter = 'fan_min_off_s';
UPDATE setpoint_changes SET parameter = 'min_vent_on_s' WHERE parameter = 'vent_min_on_s';
UPDATE setpoint_changes SET parameter = 'min_vent_off_s' WHERE parameter = 'vent_min_off_s';
UPDATE setpoint_changes SET parameter = 'mister_engage_kpa' WHERE parameter = 'mister_engage_vpd';
UPDATE setpoint_changes SET parameter = 'mister_all_kpa' WHERE parameter = 'mister_all_vpd';
UPDATE setpoint_changes SET parameter = 'irrig_wall_start_hour' WHERE parameter = 'irrig_wall_start_h';
UPDATE setpoint_changes SET parameter = 'irrig_wall_start_min' WHERE parameter = 'irrig_wall_start_m';
UPDATE setpoint_changes SET parameter = 'irrig_wall_fert_duration_min' WHERE parameter = 'irrig_wall_fert_min';
UPDATE setpoint_changes SET parameter = 'irrig_wall_fert_every_n' WHERE parameter = 'irrig_wall_fert_n';
UPDATE setpoint_changes SET parameter = 'irrig_center_start_hour' WHERE parameter = 'irrig_center_start_h';
UPDATE setpoint_changes SET parameter = 'irrig_center_start_min' WHERE parameter = 'irrig_center_start_m';
UPDATE setpoint_changes SET parameter = 'irrig_center_fert_duration_min' WHERE parameter = 'irrig_center_fert_min';
UPDATE setpoint_changes SET parameter = 'irrig_center_fert_every_n' WHERE parameter = 'irrig_center_fert_n';
UPDATE setpoint_changes SET parameter = 'irrig_vpd_boost_threshold_hrs' WHERE parameter = 'irrig_vpd_boost_threshold_h';

COMMIT;
