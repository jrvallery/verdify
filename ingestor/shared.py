"""shared.py — Shared mutable state between ingestor and tasks."""

# ESP32 client reference, set by esp32_loop in ingestor.py
# Used by dispatcher in tasks.py for direct setpoint push
esp32 = {"client": None, "keys": {}}
