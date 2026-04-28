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

# param -> latest cfg_* readback from ESP32. Used by reconnect dispatch to
# reconcile desired setpoints against device state instead of force-pushing
# values the firmware has already confirmed.
cfg_readback: dict[str, float] = {}

# Set by esp32_loop on reconnect — tells dispatcher to reconcile desired
# setpoints against cfg_readback and push only drift/missing values.
force_setpoint_push = asyncio.Event()

# Timestamp of last ESP32 connect (used for boot-window gating)
esp32_connected_at: float = 0.0
