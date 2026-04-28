"""shared.py — Shared mutable state between ingestor and tasks."""

import asyncio

# ESP32 client reference, set by esp32_loop in ingestor.py
# Used by dispatcher in tasks.py for direct setpoint push
esp32 = {"client": None, "keys": {}}

# param -> monotonic timestamp/value of the last direct ESP32 push.
# Shared between ingestor.py callbacks and tasks.py dispatcher so echo
# suppression works even when the service is launched as __main__.
recently_pushed: dict[str, float] = {}
recently_pushed_values: dict[str, float] = {}

# Set by esp32_loop on reconnect — tells dispatcher to clear _last_pushed
# and do a full re-push of all setpoints (prevents stale values after reboot)
force_setpoint_push = asyncio.Event()

# Timestamp of last ESP32 connect (used for boot-window gating)
esp32_connected_at: float = 0.0
