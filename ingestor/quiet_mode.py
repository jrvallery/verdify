"""Recording quiet-mode metadata helpers.

Quiet mode no longer changes target bands or dispatcher setpoints. Frigate
occupancy is enforced by firmware through the greenhouse_occupied switch; this
module remains only for the timed operator metadata used by the recording
helper script and status displays.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

QUIET_MODE_ENTITY = "recording_quiet_mode"
QUIET_UNTIL_ENTITY = "recording_quiet_until"
QUIET_RESTORE_ENTITY = "recording_quiet_restore"
QUIET_REASON_ENTITY = "recording_quiet_reason"

# Setpoint overlays are intentionally retired. Do not add target, band, safety,
# irrigation, or lighting params here; quiet behavior belongs in firmware.
QUIET_MODE_SETPOINTS: dict[str, float] = {}

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
