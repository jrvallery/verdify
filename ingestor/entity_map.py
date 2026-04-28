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
    "sntp_status": "sntp_status",
}

# ──────────────────────────────────────────────────────────────
# Equipment relay states — Switch entities
# ──────────────────────────────────────────────────────────────
EQUIPMENT_SWITCH_MAP: dict[str, str] = {
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
}

# ──────────────────────────────────────────────────────────────
# Setpoints (NumberInfo — write on change)
# ──────────────────────────────────────────────────────────────
SETPOINT_MAP: dict[str, str] = {
    # Temperature band
    "set_temp_low__f": "temp_low",
    "set_temp_high__f": "temp_high",
    "__heat_stage_2__f": "d_heat_stage_2",
    "__cool_stage_2__f": "d_cool_stage_2",
    "temp_hysteresis__f": "temp_hysteresis",
    "heat_hysteresis__f": "heat_hysteresis",
    "bias_heat__f": "bias_heat",
    "bias_cool__f": "bias_cool",
    # VPD band
    "set_vpd_low_kpa": "vpd_low",
    "set_vpd_high_kpa": "vpd_high",
    "vpd_hysteresis_kpa": "vpd_hysteresis",
    # Safety rails
    "safety_min__f": "safety_min",
    "safety_max__f": "safety_max",
    "safety_seal_margin__f": "safety_max_seal_margin_f",
    "safety_vpd_min_kpa": "safety_vpd_min",
    "safety_vpd_max_kpa": "safety_vpd_max",
    # Mister
    "vpd_mister_engage_kpa": "mister_engage_kpa",
    "vpd_mister_all_kpa": "mister_all_kpa",
    "mister_engage_delay__s_": "mister_engage_delay_s",
    "mister_all_delay__s_": "mister_all_delay_s",
    "mister_on__s_": "mister_on_s",
    "mister_off__s_": "mister_off_s",
    "mister_all_on__s_": "mister_all_on_s",
    "mister_all_off__s_": "mister_all_off_s",
    "mister_water_budget__gal_": "mister_water_budget_gal",
    "mister_max_runtime__min_": "mister_max_runtime_min",
    "max_relief_cycles": "max_relief_cycles",
    "dehum_aggressive_kpa": "dehum_aggressive_kpa",
    "vent_latch_timeout__ms_": "vent_latch_timeout_ms",
    # Equipment timing
    "min_heat_on__s_": "min_heat_on_s",
    "min_heat_off__s_": "min_heat_off_s",
    "min_fan_on__s_": "min_fan_on_s",
    "min_fan_off__s_": "min_fan_off_s",
    "min_vent_on__s_": "min_vent_on_s",
    "min_vent_off__s_": "min_vent_off_s",
    "lead_rotate__s_": "lead_rotate_s",
    "fan_burst__min_": "fan_burst_min",
    "vent_bypass__min_": "vent_bypass_min",
    "fog_burst__min_": "fog_burst_min",
    # Economiser
    "enthalpy_open__kj_kg_": "enthalpy_open",
    "enthalpy_close__kj_kg_": "enthalpy_close",
    "econ_heat_margin__f": "econ_heat_margin_f",
    "site_pressure__hpa_": "site_pressure_hpa",
    # Irrigation wall
    "irrig_wall_start_hour": "irrig_wall_start_hour",
    "irrig_wall_start_min": "irrig_wall_start_min",
    "irrig_wall_duration__min_": "irrig_wall_duration_min",
    "irrig_wall_fert_duration__min_": "irrig_wall_fert_duration_min",
    "irrig_wall_fert_every_n_cycles": "irrig_wall_fert_every_n",
    "irrig_wall_flush__min_": "irrig_wall_flush_min",
    "irrig_wall_interval__days_": "irrig_wall_interval_days",
    # Irrigation center
    "irrig_center_start_hour": "irrig_center_start_hour",
    "irrig_center_start_min": "irrig_center_start_min",
    "irrig_center_duration__min_": "irrig_center_duration_min",
    "irrig_center_fert_duration__min_": "irrig_center_fert_duration_min",
    "irrig_center_fert_every_n_cycles": "irrig_center_fert_every_n",
    "irrig_center_flush__min_": "irrig_center_flush_min",
    "irrig_center_interval__days_": "irrig_center_interval_days",
    # VPD boost
    "irrig_vpd_boost__": "irrig_vpd_boost_pct",
    "irrig_vpd_boost_threshold__hrs_": "irrig_vpd_boost_threshold_hrs",
    # Grow lights
    "gl_dli_target__mol_": "gl_dli_target",
    "gl_lux_threshold": "gl_lux_threshold",
    "gl_lux_hysteresis": "gl_lux_hysteresis",
    "gl_start_hour": "gl_sunrise_hour",
    "gl_cutoff_hour": "gl_sunset_hour",
    # Switches (boolean, tracked as 0.0/1.0)
    "economiser_enabled": "sw_economiser_enabled",
    "fog_closes_vent": "sw_fog_closes_vent",
    "mister_closes_vent": "sw_mister_closes_vent",  # sprint-15.1 fix 7: closes sprint-21 follow-up routing gap
    "gl_auto_mode": "sw_gl_auto_mode",
    "irrigation_enabled": "sw_irrigation_enabled",
    "irrigation_wall_enabled": "sw_irrigation_wall_enabled",
    "irrigation_center_enabled": "sw_irrigation_center_enabled",
    "irrigation_weather_skip": "sw_irrigation_weather_skip",
    "occupancy_mist_inhibit": "sw_occupancy_inhibit",
    # Mister pulse model
    "mister_pulse_on__s_": "mister_pulse_on_s",
    "mister_pulse_gap__s_": "mister_pulse_gap_s",
    "mister_vpd_weight": "mister_vpd_weight",
    # Per-zone VPD targets (pushed by dispatcher from crop band)
    "vpd_target_south__kpa_": "vpd_target_south",
    "vpd_target_west__kpa_": "vpd_target_west",
    "vpd_target_east__kpa_": "vpd_target_east",
    "vpd_target_center__kpa_": "vpd_target_center",
    "mister_center_penalty": "mister_center_penalty",
    "east_adjacency_factor": "east_adjacency_factor",
    "min_fog_on__s_": "min_fog_on_s",
    "min_fog_off__s_": "min_fog_off_s",
    # VPD-primary state machine (Phase 1)
    "vpd_watch_dwell__s_": "vpd_watch_dwell_s",
    "mist_vent_close_lead__s_": "mist_vent_close_lead_s",
    "mist_max_closed_vent__s_": "mist_max_closed_vent_s",
    "fog_escalation__kpa_": "fog_escalation_kpa",
    "mist_vent_reopen_delay__s_": "mist_vent_reopen_delay_s",
    "mist_thermal_relief__s_": "mist_thermal_relief_s",
    "fog_rh_ceiling____": "fog_rh_ceiling_pct",
    "fog_min_temp__f_": "fog_min_temp_f",
    "fog_window_start__hr_": "fog_time_window_start",
    "fog_window_end__hr_": "fog_time_window_end",
    # Sprint-15: summer thermal-driven vent preference gate.
    # 4 numerics + 1 switch. See docs/firmware-sprint-15-summer-vent-spec.md.
    "vent_prefer_temp_delta__f_": "vent_prefer_temp_delta_f",
    "vent_prefer_dp_delta__f_": "vent_prefer_dp_delta_f",
    "outdoor_staleness_max__s_": "outdoor_staleness_max_s",
    "summer_vent_min_runtime__s_": "summer_vent_min_runtime_s",
    "summer_vent_enabled": "sw_summer_vent_enabled",
    # Phase-2 dwell gate (plan firmware stabilization).
    "dwell_gate_ms": "dwell_gate_ms",
    "dwell_gate_enabled": "sw_dwell_gate_enabled",
    # Controller v2: band-first FSM.
    "fsm_controller_enabled": "sw_fsm_controller_enabled",
    "mist_backoff__s_": "mist_backoff_s",
}

# ──────────────────────────────────────────────────────────────
# Diagnostics (SensorInfo + TextSensorInfo)
# ──────────────────────────────────────────────────────────────
DIAGNOSTIC_MAP: dict[str, str] = {
    "wifi_signal": "wifi_rssi",  # SensorInfo, dBm
    "free_heap": "heap_bytes",  # SensorInfo
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
    # Controller v2 diagnostics (migration 094): expose the timers that drive
    # SEALED_MIST entry/backoff plus the hot/dry vent moisture-assist flag.
    "sealed_timer_s": "sealed_timer_s",
    "vpd_watch_timer_s": "vpd_watch_timer_s",
    "mist_backoff_timer_s": "mist_backoff_timer_s",
    "vent_mist_assist_active": "vent_mist_assist_active",
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
CFG_READBACK_MAP: dict[str, str] = {
    "cfg___temp_low___f_": "temp_low",
    "cfg___temp_high___f_": "temp_high",
    "cfg_____heat_s2___f_": "d_heat_stage_2",
    "cfg_____cool_s2___f_": "d_cool_stage_2",
    "cfg___temp_hyst___f_": "temp_hysteresis",
    "cfg___heat_hyst___f_": "heat_hysteresis",
    "cfg___vpd_low__kpa_": "vpd_low",
    "cfg___vpd_high__kpa_": "vpd_high",
    "cfg___vpd_hyst__kpa_": "vpd_hysteresis",
    "cfg___bias_heat___f_": "bias_heat",
    "cfg___bias_cool___f_": "bias_cool",
    "cfg___safety_min___f_": "safety_min",
    "cfg___safety_max___f_": "safety_max",
    "cfg___safety_seal_margin___f_": "safety_max_seal_margin_f",
    "cfg___safety_vpd_min__kpa_": "safety_vpd_min",
    "cfg___safety_vpd_max__kpa_": "safety_vpd_max",
    "cfg___site_pressure__hpa_": "site_pressure_hpa",
    "cfg___enthalpy_open__kj_kg___": "enthalpy_open",
    "cfg___enthalpy_close__kj_kg___": "enthalpy_close",
    "cfg___econ_heat_margin___f_": "econ_heat_margin_f",
    "cfg___fan_burst__min_": "fan_burst_min",
    "cfg___vent_bypass__min_": "vent_bypass_min",
    "cfg___fog_burst__min_": "fog_burst_min",
    "cfg___lead_rotate_timeout__s_": "lead_rotate_s",
    "cfg___fallback_window__s_": "fallback_window_s",
    "cfg___min_heat_on__s_": "min_heat_on_s",
    "cfg___min_heat_off__s_": "min_heat_off_s",
    "cfg___min_fan_on__s_": "min_fan_on_s",
    "cfg___min_fan_off__s_": "min_fan_off_s",
    "cfg___min_vent_on__s_": "min_vent_on_s",
    "cfg___min_vent_off__s_": "min_vent_off_s",
    "cfg_mister_engage__kpa_": "mister_engage_kpa",
    "cfg_mister_all__kpa_": "mister_all_kpa",
    # Sprint-3 (firmware): per-zone VPD targets + mister scoring readbacks.
    # The dispatcher pushes these six every planner cycle; before firmware
    # sprint-3 there was no cfg_* readback, so alert_monitor fired
    # setpoint_unconfirmed every cycle. Firmware sensor names use the
    # "Cfg • Foo Bar (unit)" pattern, which slugifies to cfg___foo_bar__unit_.
    "cfg___vpd_target_south__kpa_": "vpd_target_south",
    "cfg___vpd_target_west__kpa_": "vpd_target_west",
    "cfg___vpd_target_east__kpa_": "vpd_target_east",
    "cfg___vpd_target_center__kpa_": "vpd_target_center",
    "cfg___mister_center_penalty": "mister_center_penalty",
    "cfg___east_adjacency_factor": "east_adjacency_factor",
    # Per-zone VPD targets (from crop band, pushed by dispatcher)
    "vpd_target_south__kpa_": "vpd_target_south",
    "vpd_target_west__kpa_": "vpd_target_west",
    "vpd_target_east__kpa_": "vpd_target_east",
    "vpd_target_center__kpa_": "vpd_target_center",
    "mister_center_penalty": "mister_center_penalty",
    # Mister vent coordination
    "sw_mister_closes_vent": "sw_mister_closes_vent",
    # Sprint-15: summer thermal-driven vent readbacks.
    # 5 tunable readbacks (matching SETPOINT_MAP above) + 2 live outdoor
    # readings (firmware exposes the Tempest-sourced values it's comparing).
    # See docs/firmware-sprint-15-summer-vent-spec.md.
    "cfg___vent_prefer_temp_delta__f_": "vent_prefer_temp_delta_f",
    "cfg___vent_prefer_dp_delta__f_": "vent_prefer_dp_delta_f",
    "cfg___outdoor_staleness_max__s_": "outdoor_staleness_max_s",
    "cfg___summer_vent_min_runtime__s_": "summer_vent_min_runtime_s",
    "cfg_summer_vent_enabled": "sw_summer_vent_enabled",
    "cfg___outdoor_temp___f_": "outdoor_temp_f",
    "cfg___outdoor_dewpoint___f_": "outdoor_dewpoint_f",
    # Phase 1c: 10 fire-and-forget tunable readbacks. Dispatcher pushed
    # these but firmware never echoed — alert_monitor couldn't verify
    # landings. Same "Cfg • Foo Bar (unit)" → cfg___foo_bar__unit_
    # slug pattern as sprint-15 block above.
    "cfg_fsm_controller_enabled": "sw_fsm_controller_enabled",
    "cfg___mist_backoff__s_": "mist_backoff_s",
    "cfg___mister_pulse_on__s_": "mister_pulse_on_s",
    "cfg___mister_pulse_gap__s_": "mister_pulse_gap_s",
    "cfg___mister_water_budget__gal_": "mister_water_budget_gal",
    "cfg___mister_vpd_weight": "mister_vpd_weight",
    "cfg___vpd_watch_dwell__s_": "vpd_watch_dwell_s",
    "cfg___mist_vent_close_lead__s_": "mist_vent_close_lead_s",
    "cfg___mist_max_closed_vent__s_": "mist_max_closed_vent_s",
    "cfg___mist_vent_reopen_delay__s_": "mist_vent_reopen_delay_s",
    "cfg___mist_thermal_relief__s_": "mist_thermal_relief_s",
    "cfg___fog_escalation__kpa_": "fog_escalation_kpa",
    "cfg___fog_window_start__hour_": "fog_time_window_start",
    "cfg___fog_window_end__hour_": "fog_time_window_end",
    "cfg___max_relief_cycles": "max_relief_cycles",
    "cfg___dehum_aggressive__kpa_": "dehum_aggressive_kpa",
    "cfg___vent_latch_timeout__ms_": "vent_latch_timeout_ms",
    "cfg___gl_lux_hysteresis": "gl_lux_hysteresis",
}

# ──────────────────────────────────────────────────────────────
# Inverse maps: DB parameter name → ESP32 object_id
# Auto-generated from SETPOINT_MAP. Used by dispatcher for push.
# ──────────────────────────────────────────────────────────────
PARAM_TO_ENTITY = {v: k for k, v in SETPOINT_MAP.items() if not v.startswith("sw_")}
SWITCH_TO_ENTITY = {v: k for k, v in SETPOINT_MAP.items() if v.startswith("sw_")}
