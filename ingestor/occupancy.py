"""Occupancy bridge actions for Frigate/Sentinel greenhouse presence."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta

import asyncpg
from esp32_push import push_occupancy_to_esp32
from quiet_mode import (
    QUIET_MODE_ENTITY,
    QUIET_REASON_ENTITY,
    QUIET_RESTORE_ENTITY,
    QUIET_UNTIL_ENTITY,
    build_restore_payload,
    iso_utc,
    parse_iso_utc,
    quiet_is_active,
)

from verdify_schemas import SystemStateRow

log = logging.getLogger("occupancy")

OCCUPANCY_ENTITY = "occupancy"
QUIET_OCCUPANCY_ACTIVE_ENTITY = "recording_quiet_occupancy_active"
OCCUPANCY_QUIET_EXTENSION_MIN = int(os.environ.get("OCCUPANCY_QUIET_EXTENSION_MIN", "15"))
QUIET_STATE_ENTITIES = (
    QUIET_MODE_ENTITY,
    QUIET_UNTIL_ENTITY,
    QUIET_RESTORE_ENTITY,
    QUIET_REASON_ENTITY,
    QUIET_OCCUPANCY_ACTIVE_ENTITY,
)


async def _fetch_system_state(conn: asyncpg.Connection, entities: tuple[str, ...]) -> dict[str, str]:
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (entity) entity, value
        FROM system_state
        WHERE entity = ANY($1::text[])
        ORDER BY entity, ts DESC
        """,
        list(entities),
    )
    return {row["entity"]: row["value"] for row in rows}


async def _insert_system_state(conn: asyncpg.Connection, entity: str, value: str) -> None:
    SystemStateRow(ts=datetime.now(UTC), entity=entity, value=value)
    await conn.execute(
        "INSERT INTO system_state (ts, entity, value) VALUES (now(), $1, $2)",
        entity,
        value,
    )


async def _fetch_effective_params(conn: asyncpg.Connection) -> dict[str, float]:
    rows = await conn.fetch(
        """
        SELECT parameter, value
        FROM (
          SELECT DISTINCT ON (parameter) parameter, value
          FROM setpoint_changes
          ORDER BY parameter, ts DESC
        ) latest
        """
    )
    params = {row["parameter"]: float(row["value"]) for row in rows}

    rows = await conn.fetch("SELECT parameter, value FROM v_active_plan")
    for row in rows:
        params[row["parameter"]] = float(row["value"])
    return params


def _is_occupancy_owned(reason: str | None) -> bool:
    return bool(reason and reason.startswith("occupancy:"))


async def _enable_occupancy_quiet(conn: asyncpg.Connection, state: dict[str, str], source: str) -> str:
    now = datetime.now(UTC)
    requested_until = now + timedelta(minutes=OCCUPANCY_QUIET_EXTENSION_MIN)
    current_until = parse_iso_utc(state.get(QUIET_UNTIL_ENTITY))
    active = quiet_is_active(state.get(QUIET_MODE_ENTITY), state.get(QUIET_UNTIL_ENTITY), now)
    reason = state.get(QUIET_REASON_ENTITY)
    occupancy_owned = _is_occupancy_owned(reason)

    if not active:
        effective = await _fetch_effective_params(conn)
        await _insert_system_state(conn, QUIET_RESTORE_ENTITY, build_restore_payload(effective))

    until = requested_until
    should_write_reason = True
    if active and not occupancy_owned and current_until is not None and current_until > requested_until:
        # A manual quiet window already covers this occupancy refresh. Preserve
        # manual ownership so the later empty observation does not cancel it.
        until = current_until
        should_write_reason = False

    if should_write_reason:
        await _insert_system_state(conn, QUIET_REASON_ENTITY, f"occupancy:{source}")
    await _insert_system_state(conn, QUIET_UNTIL_ENTITY, iso_utc(until))
    await _insert_system_state(conn, QUIET_MODE_ENTITY, "on")
    await _insert_system_state(conn, QUIET_OCCUPANCY_ACTIVE_ENTITY, "on")
    return iso_utc(until)


async def _release_occupancy_quiet(conn: asyncpg.Connection, state: dict[str, str], source: str) -> str:
    await _insert_system_state(conn, QUIET_OCCUPANCY_ACTIVE_ENTITY, "off")
    if _is_occupancy_owned(state.get(QUIET_REASON_ENTITY)):
        now = datetime.now(UTC)
        await _insert_system_state(conn, QUIET_REASON_ENTITY, f"occupancy_released:{source}")
        await _insert_system_state(conn, QUIET_UNTIL_ENTITY, iso_utc(now))
        # Leave mode "on" with an expired until so the dispatcher takes the
        # existing restore path on its next cycle.
        return "expired_for_restore"
    return "left_manual_quiet_unchanged"


async def sync_occupancy_state(pool: asyncpg.Pool, occupied: bool, source: str) -> None:
    """Record occupancy, apply quiet-mode state, and push occupancy to ESP32."""
    label = "occupied" if occupied else "empty"
    async with pool.acquire() as conn:
        await _insert_system_state(conn, OCCUPANCY_ENTITY, label)
        quiet_state = await _fetch_system_state(conn, QUIET_STATE_ENTITIES)
        if occupied:
            until = await _enable_occupancy_quiet(conn, quiet_state, source)
            log.info("Occupancy: %s via %s; quiet mode held until %s", label, source, until)
        else:
            action = await _release_occupancy_quiet(conn, quiet_state, source)
            log.info("Occupancy: %s via %s; quiet mode action=%s", label, source, action)

    await push_occupancy_to_esp32(occupied, source)


async def refresh_latest_occupancy_state(pool: asyncpg.Pool, source: str) -> None:
    """Replay the latest recorded occupancy after ESP32 API reconnect."""
    async with pool.acquire() as conn:
        value = await conn.fetchval(
            """
            SELECT value
            FROM system_state
            WHERE entity = $1
            ORDER BY ts DESC
            LIMIT 1
            """,
            OCCUPANCY_ENTITY,
        )
    if value not in {"occupied", "empty"}:
        return
    await sync_occupancy_state(pool, value == "occupied", source)
