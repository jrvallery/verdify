"""Shared direct ESP32 push helper.

Kept outside ingestor.py so tasks.py does not import the service entrypoint.
When systemd runs ``python ingestor.py``, importing ``ingestor`` creates a
second module instance with separate state; this module avoids that split.
"""

from __future__ import annotations

import asyncio
import logging
import time

import shared
from entity_map import SETPOINT_MAP

log = logging.getLogger("esp32_push")

_BATCH_PAUSE_EVERY = 8
_BATCH_PAUSE_S = 0.15
_MIN_COMMAND_INTERVAL_S = 0.15
_PUSH_LOCK = asyncio.Lock()
_LAST_COMMAND_TS = 0.0


async def _pace_command() -> None:
    global _LAST_COMMAND_TS
    now = time.monotonic()
    wait_s = _MIN_COMMAND_INTERVAL_S - (now - _LAST_COMMAND_TS)
    if wait_s > 0:
        await asyncio.sleep(wait_s)
    _LAST_COMMAND_TS = time.monotonic()


async def push_to_esp32(changes: list[tuple[str, float, str]]) -> int:
    """Push setpoint changes through the shared aioesphomeapi connection.

    Args:
        changes: ``[(esp32_object_id, value, "number" | "switch"), ...]``.

    Returns:
        Count of successfully pushed changes. Returns 0 when disconnected.
    """
    client = shared.esp32["client"]
    keys = shared.esp32["keys"]
    if client is None:
        return 0

    pushed = 0
    async with _PUSH_LOCK:
        for idx, (obj_id, val, etype) in enumerate(changes, start=1):
            key = keys.get(obj_id)
            if not key:
                log.warning("push_to_esp32: no key for '%s' (%d keys)", obj_id, len(keys))
                continue
            try:
                await _pace_command()
                if etype == "number":
                    result = client.number_command(key, val)
                    if asyncio.iscoroutine(result):
                        await result
                elif etype == "switch":
                    result = client.switch_command(key, val > 0.5)
                    if asyncio.iscoroutine(result):
                        await result
                else:
                    log.warning("push_to_esp32: unsupported entity type '%s' for %s", etype, obj_id)
                    continue

                pushed += 1
                db_param = SETPOINT_MAP.get(obj_id)
                if db_param:
                    shared.recently_pushed[db_param] = time.time()
                    shared.recently_pushed_values[db_param] = float(val)
                if len(changes) > 1 and idx < len(changes) and pushed % _BATCH_PAUSE_EVERY == 0:
                    await asyncio.sleep(_BATCH_PAUSE_S)
            except Exception as e:
                log.warning("ESP32 push failed for %s: %s", obj_id, e)
                break

    return pushed
