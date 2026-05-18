"""
entity_map.py — Maps ESPHome object_id → database target

Object IDs are derived from the entity's friendly name by ESPHome's
str_sanitize() (lowercase, non-alphanumeric → '_', collapse repeats).
These were verified against live ESP32 entity enumeration 2026-03-22.

Structure:
  CLIMATE_MAP:        object_id → column name in `climate` table
  EQUIPMENT_BINARY_MAP: object_id → equipment name in `equipment_state` (BinarySensor)
  EQUIPMENT_SWITCH_MAP: object_id → equipment name in `equipment_state` (Switch)
  STATE_MAP:          object_id → entity name in `system_state` table (TextSensor)
  SETPOINT_MAP:       object_id → parameter name in `setpoint_changes` (Number)
  DIAGNOSTIC_MAP:     object_id → column name in `diagnostics` table
  DAILY_ACCUM_MAP:    object_id → column name in `daily_summary` table
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from verdify_schemas.tunable_registry import (  # noqa: E402
    CFG_READBACK_ALIASES_REG,
    CFG_READBACK_MAP_REG,
    SETPOINT_MAP_REG,
)

# ──────────────────────────────────────────────────────────────
# Climate sensor columns (SensorInfo)
# ──────────────────────────────────────────────────────────────
CLIMATE_MAP: dict[str, str] = {
    # Temperature (°F)
    "avg_temp___f_": "temp_avg",
    "north_temp___f_": "temp_north",
    "south_temp___f_": "temp_south",
    "east_temp___f_": "temp_east",
    "west_temp___f_": "temp_west",
    "case_temp___f_": "temp_case",
    "control_tin___f_": "temp_control",
    "exterior_intake_temp___f_": "temp_intake",
    # Relative Humidity (%)
    "avg_rh____": "rh_avg",
    "north_rh____": "rh_north",
    "south_rh____": "rh_south",
    "east_rh____": "rh_east",
    "west_rh____": "rh_west",
    "case_rh____": "rh_case",
    # VPD (kPa)
    "avg_vpd__kpa_": "vpd_avg",
    "north_vpd__kpa_": "vpd_north",
    "south_vpd__kpa_": "vpd_south",
    "east_vpd__kpa_": "vpd_east",
    "west_vpd__kpa_": "vpd_west",
    "control_vpd__kpa_": "vpd_control",
    # Derived climate
    "dew_point___f_": "dew_point",
    "abs_humidity__g_m__": "abs_humidity",
    "enthalpy____kj_kg_": "enthalpy_delta",
    # Air quality
    "co___ppm_": "co2_ppm",
    # Light
    "light__lx_": "lux",
    "dli__mol_m___day___": "dli_today",
    # Water
    "water_flow__gpm_": "flow_gpm",
    "water_used__gal_": "water_total_gal",
    # Mister
    "mister_water_today": "mister_water_today",
    # Soil sensors (DFRobot SEN0600/SEN0601, Modbus RTU)
    # South 1 (addr 7, SEN0601): moisture + temp + EC
    # South 2 (addr 8, SEN0600): moisture + temp
    # West (addr 9, SEN0600): moisture + temp
    # object_ids verified via esphome.helpers.sanitize()
    "south_1_soil_moisture____": "soil_moisture_south_1",
    "south_1_soil_temp___f_": "soil_temp_south_1",
    "south_1_soil_ec___s_cm_": "soil_ec_south_1",
    "south_2_soil_moisture____": "soil_moisture_south_2",
    "south_2_soil_temp___f_": "soil_temp_south_2",
    "west_soil_moisture____": "soil_moisture_west",
    "west_soil_temp___f_": "soil_temp_west",
    # Exterior intake (additional sensors beyond temp)
    "exterior_intake_rh____": "intake_rh",
    "exterior_intake_vpd__kpa_": "intake_vpd",
    "outdoor_illuminance": "outdoor_illuminance",
    # Tempest weather (UDP direct from ESP32, replaces HA tempest_sync)
    "tempest_temperature": "outdoor_temp_f",
    "tempest_humidity": "outdoor_rh_pct",
    "tempest_wind_speed": "wind_speed_mph",
    "tempest_wind_direction": "wind_direction_deg",
    "tempest_wind_gust": "wind_gust_mph",
    "tempest_wind_lull": "wind_lull_mph",
    "tempest_pressure": "pressure_hpa",
    "tempest_solar_irradiance": "solar_irradiance_w_m2",
    "tempest_uv_index": "uv_index",
    "tempest_illuminance": "outdoor_lux",
    "tempest_precipitation_rate": "precip_in",  # NOTE: arrives as mm/min, DB expects in
    "tempest_lightning_count": "lightning_count",
    "tempest_lightning_distance": "lightning_avg_dist_mi",  # NOTE: arrives as km, DB expects mi
}

# ──────────────────────────────────────────────────────────────
# Equipment relay states — BinarySensor entities
# ──────────────────────────────────────────────────────────────
EQUIPMENT_BINARY_MAP: dict[str, str] = {
    "fan_1_running": "fan1",
    "fan_2_running": "fan2",
    "heat_1_running": "heat1",
    "heat_2_running": "heat2",
    "fog_running": "fog",
    "vent_open": "vent",
    "mister_running": "mister_any",
    "mister_budget_exceeded": "mister_budget_exceeded",
    "economiser_blocked": "economiser_blocked",
    "leak_detected": "leak_detected",  # SAFETY CRITICAL
    "water_flowing": "water_flowing",
    "heap_pressure_warning": "heap_pressure_warning",
    "heap_pressure_critical": "heap_pressure_critical",
    "fan_burst_active": "fan_burst_active",
    "fog_burst_active": "fog_burst_active",
    "vent_bypass_active": "vent_bypass_active",
}

# ──────────────────────────────────────────────────────────────
# Equipment relay states — Switch entities
# ──────────────────────────────────────────────────────────────
EQUIPMENT_SWITCH_MAP: dict[str, str] = {
    "greenhouse_occupied": "occupancy",
    "mister___south_wall": "mister_south",
    "mister___south_wall__fert__": "mister_south_fert",
    "mister___west_wall": "mister_west",
    "mister___west_wall__fert__": "mister_west_fert",
    "mister___center": "mister_center",
    "drip___wall": "drip_wall",
    "drip___wall__fert__": "drip_wall_fert",
    "drip___center": "drip_center",
    "drip___center__fert__": "drip_center_fert",
    "valve___fert__master": "fert_master_valve",
    "grow_light_main": "grow_light_main",
    "grow_light_grow": "grow_light_grow",
    # Config switches (boolean tunables exposed as HA switches)
    "economiser_enabled": "economiser_enabled",
    "fog_closes_vent": "fog_closes_vent",
    "irrigation_enabled": "irrigation_enabled",
    "irrigation_wall_enabled": "irrigation_wall_enabled",
    "irrigation_center_enabled": "irrigation_center_enabled",
    "irrigation_weather_skip": "irrigation_weather_skip",
    "gl_auto_mode": "gl_auto_mode",
    "occupancy_mist_inhibit": "occupancy_inhibit",
}

# Combined for legacy callers — not used by ingestor directly
EQUIPMENT_MAP: dict[str, str] = {**EQUIPMENT_BINARY_MAP, **EQUIPMENT_SWITCH_MAP}

# ──────────────────────────────────────────────────────────────
# State machine text entities (TextSensorInfo)
# ──────────────────────────────────────────────────────────────
STATE_MAP: dict[str, str] = {
    "greenhouse_state": "greenhouse_state",
    "lead_fan": "lead_fan",
    "last_state_transition": "last_transition",
    "mister_state": "mister_state",
    "mister_selected_zone": "mister_zone",
    # OBS-1e (Sprint 16): firmware silent-override audit.
    # Value is a comma-separated list of active override flags from
    # evaluate_overrides() (e.g. "occupancy_blocks_moisture,fog_gate_rh"
    # or "none"). Ingestor also diffs transitions and writes one row per
    # start event to the override_events table.
    "active_overrides": "overrides_active",
    # Sprint-15.1 fix 8: diagnostic trace — which branch of
    # determine_mode() chose the current mode. Lets post-hoc queries
    # distinguish `summer_vent_preempt` from `temp_vent` from
    # `seal_enter` etc. Populated by controls.yaml from
    # ctl_state.last_mode_reason on every cycle.
    "mode_reason": "mode_reason",
    "gl_main_state": "gl_main_state",
    "gl_main_reason": "gl_main_reason",
    "gl_main_decision_epoch": "gl_main_decision_epoch",  # TextSensorInfo exact epoch string
    "gl_grow_state": "gl_grow_state",
    "gl_grow_reason": "gl_grow_reason",
    "gl_grow_decision_epoch": "gl_grow_decision_epoch",  # TextSensorInfo exact epoch string
}

# ──────────────────────────────────────────────────────────────
# Setpoints (NumberInfo — write on change)
# ──────────────────────────────────────────────────────────────
SETPOINT_MAP: dict[str, str] = dict(SETPOINT_MAP_REG)

# ──────────────────────────────────────────────────────────────
# Diagnostics (SensorInfo + TextSensorInfo)
# ──────────────────────────────────────────────────────────────
DIAGNOSTIC_MAP: dict[str, str] = {
    "wifi_signal": "wifi_rssi",  # SensorInfo, dBm
    "free_heap": "heap_bytes",  # SensorInfo
    "minimum_free_heap": "heap_min_free_kb",  # SensorInfo, kB
    "largest_free_heap_block": "heap_largest_free_block_kb",  # SensorInfo, kB
    "uptime": "uptime_s",  # SensorInfo
    "probe_health": "probe_health",  # TextSensorInfo
    "reset_reason": "reset_reason",  # TextSensorInfo
    "firmware_version": "firmware_version",  # TextSensorInfo
    # FW-10 (Sprint 17): how many zone probes (north/south/east/west) are
    # currently contributing to the avg_temp/rh/vpd aggregates. Stale probes
    # (>5 min since last reading) are excluded. Planner distrusts aggregates
    # when count < 4.
    "active_probe_count": "active_probe_count",  # SensorInfo, 0-4
    # OBS-3 (Sprint 18): firmware ControlState breaker counters, exposed so
    # the planner can see how close firmware is to forcing a VENTILATE
    # latch (relief_cycle_count) and how long that latch has been active
    # (vent_latch_timer_s). See migration 082.
    "relief_cycle_count": "relief_cycle_count",  # SensorInfo, 0-max_relief_cycles
    "vent_latch_timer_s": "vent_latch_timer_s",  # SensorInfo, 0-1800 s
    # Band-first controller diagnostics (migration 094): expose the timers that drive
    # SEALED_MIST entry/backoff plus the hot/dry vent moisture-assist flag.
    "sealed_timer_s": "sealed_timer_s",
    "vpd_watch_timer_s": "vpd_watch_timer_s",
    "mist_backoff_timer_s": "mist_backoff_timer_s",
    "vent_mist_assist_active": "vent_mist_assist_active",
    "controller_time_epoch": "controller_time_epoch",  # TextSensorInfo exact epoch string
    "controller_local_hour": "controller_local_hour",
    "sntp_valid": "sntp_valid",
    "sntp_miss_count": "sntp_miss_count",
    "last_sntp_sync_age_s": "last_sntp_sync_age_s",
}

# ──────────────────────────────────────────────────────────────
# Daily accumulator sensors (SensorInfo, snapshot at midnight)
# ──────────────────────────────────────────────────────────────
DAILY_ACCUM_MAP: dict[str, str] = {
    # Cycle counts
    "cycles___fan_1__today_": "cycles_fan1",
    "cycles___fan_2__today_": "cycles_fan2",
    "cycles___heat_1__today_": "cycles_heat1",
    "cycles___heat_2__today_": "cycles_heat2",
    "cycles___fog_fan__today_": "cycles_fog",
    "cycles___vent__today_": "cycles_vent",
    "de_hum_cycles__today_": "cycles_dehum",
    "safety_de_hum_cycles__today_": "cycles_safety_dehum",
    "cycles___mister_south__today_": "cycles_mister_south",
    "cycles___mister_west__today_": "cycles_mister_west",
    "cycles___mister_center__today_": "cycles_mister_center",
    "cycles___drip_wall__today_": "cycles_drip_wall",
    "cycles___drip_center__today_": "cycles_drip_center",
    # Runtime (relay minutes)
    "runtime___fan_1__min_today_": "runtime_fan1_min",
    "runtime___fan_2__min_today_": "runtime_fan2_min",
    "runtime___heat_1__min_today_": "runtime_heat1_min",
    "runtime___heat_2__min_today_": "runtime_heat2_min",
    "runtime___fog__min_today_": "runtime_fog_min",
    "runtime___vent__min_today_": "runtime_vent_min",
    # Runtime (mister hours)
    "mister_south_wall_runtime__today_": "runtime_mister_south_h",
    "mister_west_wall_runtime__today_": "runtime_mister_west_h",
    "mister_center_runtime__today_": "runtime_mister_center_h",
    # Drip runtimes
    "wall_drips_runtime__today_": "runtime_drip_wall_h",
    "center_drips_runtime__today_": "runtime_drip_center_h",
    # Firmware sprint-2 fairness watchdog counter (resets at midnight)
    "mister_fairness_overrides__today_": "mister_fairness_overrides_today",
}

# ──────────────────────────────────────────────────────────────
# ESP32 Configured Value Readback (cfg_* diagnostic sensors)
# Maps ESP32 object_id → canonical DB parameter name
# Written to setpoint_snapshot table for ground-truth tracking
# ──────────────────────────────────────────────────────────────
CFG_READBACK_MAP: dict[str, str] = {**CFG_READBACK_MAP_REG, **CFG_READBACK_ALIASES_REG}

# ──────────────────────────────────────────────────────────────
# Inverse maps: DB parameter name → ESP32 object_id
# Auto-generated from SETPOINT_MAP. Used by dispatcher for push.
# ──────────────────────────────────────────────────────────────
PARAM_TO_ENTITY = {v: k for k, v in SETPOINT_MAP.items() if not v.startswith("sw_")}
SWITCH_TO_ENTITY = {v: k for k, v in SETPOINT_MAP.items() if v.startswith("sw_")}
