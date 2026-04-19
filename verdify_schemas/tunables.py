"""Canonical tunable parameter names.

Single source of truth for every parameter the planner can emit and the
dispatcher can push. Used by PlanTransition, SetpointChange, and every MCP
tool that accepts a `parameter` argument.

Pairs with `ingestor/entity_map.py` SETPOINT_MAP — the schema test
`test_tunables_match_entity_map` asserts these two sets stay in sync, so a
new ESP32 entity that isn't added here (or vice versa) fails CI instead of
being silently dropped.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator

# Non-switch tunables — numeric values, validated as floats.
# Mirror of {v for v in SETPOINT_MAP.values() if not v.startswith("sw_")}.
NUMERIC_TUNABLES: frozenset[str] = frozenset(
    {
        # Temperature band
        "temp_low",
        "temp_high",
        "d_heat_stage_2",
        "d_cool_stage_2",
        "temp_hysteresis",
        "bias_heat",
        "bias_cool",
        # VPD band
        "vpd_low",
        "vpd_high",
        "vpd_hysteresis",
        # Safety rails
        "safety_min",
        "safety_max",
        "safety_vpd_min",
        "safety_vpd_max",
        # Mister
        "mister_engage_kpa",
        "mister_all_kpa",
        "mister_engage_delay_s",
        "mister_all_delay_s",
        "mister_on_s",
        "mister_off_s",
        "mister_all_on_s",
        "mister_all_off_s",
        "mister_water_budget_gal",
        "mister_max_runtime_min",
        # Equipment timing
        "min_heat_on_s",
        "min_heat_off_s",
        "min_fan_on_s",
        "min_fan_off_s",
        "min_vent_on_s",
        "min_vent_off_s",
        "lead_rotate_s",
        "fan_burst_min",
        "vent_bypass_min",
        "fog_burst_min",
        # Firmware-internal, readback-only (no SETPOINT_MAP route) — present
        # in entity_map.CFG_READBACK_MAP so SetpointSnapshot writes validate.
        "fallback_window_s",
        # Economiser
        "enthalpy_open",
        "enthalpy_close",
        "site_pressure_hpa",
        # Irrigation wall
        "irrig_wall_start_hour",
        "irrig_wall_start_min",
        "irrig_wall_duration_min",
        "irrig_wall_fert_duration_min",
        "irrig_wall_fert_every_n",
        "irrig_wall_flush_min",
        "irrig_wall_interval_days",
        # Irrigation center
        "irrig_center_start_hour",
        "irrig_center_start_min",
        "irrig_center_duration_min",
        "irrig_center_fert_duration_min",
        "irrig_center_fert_every_n",
        "irrig_center_flush_min",
        "irrig_center_interval_days",
        # VPD boost
        "irrig_vpd_boost_pct",
        "irrig_vpd_boost_threshold_hrs",
        # Grow lights
        "gl_dli_target",
        "gl_lux_threshold",
        "gl_sunrise_hour",
        "gl_sunset_hour",
        # Mister pulse model
        "mister_pulse_on_s",
        "mister_pulse_gap_s",
        "mister_vpd_weight",
        # Per-zone VPD targets
        "vpd_target_south",
        "vpd_target_west",
        "vpd_target_east",
        "vpd_target_center",
        "mister_center_penalty",
        "east_adjacency_factor",
        "min_fog_on_s",
        "min_fog_off_s",
        # VPD-primary state machine
        "vpd_watch_dwell_s",
        "mist_vent_close_lead_s",
        "mist_max_closed_vent_s",
        "fog_escalation_kpa",
        "mist_vent_reopen_delay_s",
        "mist_thermal_relief_s",
        "fog_rh_ceiling_pct",
        "fog_min_temp_f",
        "fog_time_window_start",
        "fog_time_window_end",
    }
)

# Switch tunables — boolean, stored as 0.0 / 1.0 on the wire.
# Mirror of {v for v in SETPOINT_MAP.values() if v.startswith("sw_")}.
SWITCH_TUNABLES: frozenset[str] = frozenset(
    {
        "sw_economiser_enabled",
        "sw_fog_closes_vent",
        "sw_gl_auto_mode",
        "sw_irrigation_enabled",
        "sw_irrigation_wall_enabled",
        "sw_irrigation_center_enabled",
        "sw_irrigation_weather_skip",
        "sw_occupancy_inhibit",
        # NOTE: sw_mister_closes_vent exists as an ESP32 switch (firmware
        # tunables.yaml line 1069) and as a CFG readback, but is NOT in
        # SETPOINT_MAP today — dispatcher can't push it. Not adding here
        # until the routing gap is closed; see Sprint 21 follow-up.
    }
)

ALL_TUNABLES: frozenset[str] = NUMERIC_TUNABLES | SWITCH_TUNABLES


def _validate_tunable(v: str) -> str:
    if v not in ALL_TUNABLES:
        raise ValueError(
            f"Unknown tunable parameter: {v!r}. "
            f"Add to NUMERIC_TUNABLES or SWITCH_TUNABLES in verdify_schemas/tunables.py "
            f"if this is a new dispatcher-emitted parameter."
        )
    return v


TunableParameter = Annotated[str, AfterValidator(_validate_tunable)]
