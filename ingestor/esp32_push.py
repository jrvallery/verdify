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
    for obj_id, val, etype in changes:
        key = keys.get(obj_id)
        if not key:
            log.warning("push_to_esp32: no key for '%s' (%d keys)", obj_id, len(keys))
            continue
        try:
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
        except Exception as e:
            log.warning("ESP32 push failed for %s: %s", obj_id, e)
            break

    return pushed
