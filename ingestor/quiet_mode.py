"""Recording quiet-mode helpers.

This is intentionally not firmware. Quiet mode is an operator overlay in the
dispatcher/setpoint layer: suppress routine noisy equipment while preserving
firmware safety heat/cool rails.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

QUIET_MODE_ENTITY = "recording_quiet_mode"
QUIET_UNTIL_ENTITY = "recording_quiet_until"
QUIET_RESTORE_ENTITY = "recording_quiet_restore"
QUIET_REASON_ENTITY = "recording_quiet_reason"

# Values chosen to keep routine automation quiet without disabling safety:
# - wide temp/VPD bands avoid routine vent/fog/mist actions;
# - safety heat/cool still preempts through firmware;
# - lights and irrigation are disabled at their normal operator switches.
QUIET_MODE_SETPOINTS: dict[str, float] = {
    "temp_low": 35.0,
    "temp_high": 90.0,
    "vpd_low": 0.10,
    "vpd_high": 3.00,
    "vpd_target_south": 3.00,
    "vpd_target_west": 3.00,
    "vpd_target_east": 3.00,
    "vpd_target_center": 3.00,
    "safety_vpd_min": 0.10,
    "safety_vpd_max": 3.00,
    "heat_hysteresis": 0.0,
    "sw_gl_auto_mode": 0.0,
    "sw_irrigation_enabled": 0.0,
    "sw_irrigation_wall_enabled": 0.0,
    "sw_irrigation_center_enabled": 0.0,
    "sw_irrigation_weather_skip": 1.0,
    "sw_occupancy_inhibit": 1.0,
    "sw_summer_vent_enabled": 0.0,
    "sw_mister_closes_vent": 1.0,
    "mister_engage_delay_s": 900.0,
    "mister_all_delay_s": 900.0,
    "vpd_watch_dwell_s": 120.0,
    "fog_escalation_kpa": 1.0,
    "mister_pulse_on_s": 30.0,
    "mister_pulse_gap_s": 60.0,
    "mist_max_closed_vent_s": 120.0,
    "mist_backoff_s": 3600.0,
    "max_relief_cycles": 1.0,
}

QUIET_RESTORE_PARAMS: tuple[str, ...] = tuple(QUIET_MODE_SETPOINTS)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_iso_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def quiet_is_active(mode: str | None, until_value: str | None, now: datetime | None = None) -> bool:
    until = parse_iso_utc(until_value)
    if mode != "on" or until is None:
        return False
    return until > (now or utc_now())


def quiet_expired_needs_restore(mode: str | None, until_value: str | None, now: datetime | None = None) -> bool:
    until = parse_iso_utc(until_value)
    if mode != "on" or until is None:
        return False
    return until <= (now or utc_now())


def build_restore_payload(effective_params: dict[str, float]) -> str:
    payload = {param: effective_params.get(param) for param in QUIET_RESTORE_PARAMS}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def parse_restore_payload(value: str | None) -> dict[str, float]:
    if not value:
        return {}
    try:
        raw = json.loads(value)
    except json.JSONDecodeError:
        return {}
    restored: dict[str, float] = {}
    for param, raw_value in raw.items():
        if raw_value is None:
            continue
        try:
            restored[param] = float(raw_value)
        except (TypeError, ValueError):
            continue
    return restored
