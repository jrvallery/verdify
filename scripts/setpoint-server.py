#!/usr/bin/env /srv/greenhouse/.venv/bin/python3
"""
setpoint-server.py — HTTP setpoint delivery server for ESP32 + grow light control.

Exposes simple endpoints for the ESP32 to toggle grow lights without needing
HA auth tokens in the firmware. Also tracks light state and runtime.

Endpoints:
    GET  /lights              — current state of both lights
    POST /lights/main/on      — turn on greenhouse main
    POST /lights/main/off     — turn off greenhouse main
    POST /lights/grow/on      — turn on greenhouse grow
    POST /lights/grow/off     — turn off greenhouse grow
    GET  /health              — service health check

Listens on 0.0.0.0:8200 (accessible from ESP32 at 192.168.10.111).
Writes state changes to equipment_state table.

Usage:
    setpoint-server.py           # run as foreground service (systemd)
"""

import asyncio
import json
import logging
import os
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import asyncpg

# --- Configuration ---
HA_URL = "http://192.168.30.107:8123"
HA_TOKEN_FILE = "/mnt/jason/agents/shared/credentials/ha_token.txt"
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 8200

LIGHTS = {
    "main": {"ha_entity": "light.greenhouse_main", "equipment": "grow_light_main"},
    "grow": {"ha_entity": "light.greenhouse_grow", "equipment": "grow_light_grow"},
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [setpoint-server] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Global state
_db_pool = None
_ha_token = None
_light_state = {"main": None, "grow": None}  # True=on, False=off, None=unknown


def load_token() -> str:
    with open(HA_TOKEN_FILE) as f:
        return f.read().strip()


def ha_call(service: str, entity_id: str) -> bool:
    """Call HA REST API service. Returns True on success."""
    global _ha_token
    if _ha_token is None:
        _ha_token = load_token()
    url = f"{HA_URL}/api/services/light/{service}"
    body = json.dumps({"entity_id": entity_id}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {_ha_token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception as e:
        log.error("HA call failed: %s %s → %s", service, entity_id, e)
        return False


def ha_get_state(entity_id: str) -> str | None:
    """Get current state of an HA entity. Returns 'on', 'off', or None."""
    global _ha_token
    if _ha_token is None:
        _ha_token = load_token()
    url = f"{HA_URL}/api/states/{entity_id}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {_ha_token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("state")
    except Exception as e:
        log.error("HA state fetch failed: %s → %s", entity_id, e)
        return None


async def record_state_change(equipment: str, is_on: bool) -> None:
    """Write state change to equipment_state table."""
    global _db_pool
    if _db_pool is None:
        return
    try:
        async with _db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO equipment_state (ts, equipment, state) VALUES ($1, $2, $3)",
                datetime.now(UTC),
                equipment,
                is_on,
            )
        log.info("State recorded: %s → %s", equipment, "ON" if is_on else "OFF")
    except Exception as e:
        log.error("DB write failed: %s", e)


def get_db_url() -> str:
    pw = "verdify"
    env_file = "/srv/verdify/.env"
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if line.strip().startswith("POSTGRES_PASSWORD="):
                    pw = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    return f"postgresql://verdify:{pw}@localhost:5432/verdify"


def get_setpoint_text_sync() -> str:
    """Query setpoint_plan for current active values. Synchronous for HTTP thread."""
    import subprocess

    db_cmd = [
        "docker",
        "exec",
        "verdify-timescaledb",
        "psql",
        "-U",
        "verdify",
        "-d",
        "verdify",
        "-t",
        "-A",
        "-F",
        "=",
        "-c",
    ]

    # Planner/dispatcher param names → ESP32 firmware param names
    # The ESP32 pull lambda reads specific key names from this endpoint.
    # Some DB sources use different names (e.g. dispatcher uses ESPHome object_ids,
    # planner uses its own naming). This map ensures the ESP32 always sees the right key.
    # DB trigger (migration 058) normalizes all param names at INSERT — no aliases needed
    # Step 1: ALL current setpoints as baseline
    params = {}
    result = subprocess.run(
        db_cmd
        + [
            "SELECT parameter, value FROM (SELECT DISTINCT ON (parameter) parameter, value "
            "FROM setpoint_changes ORDER BY parameter, ts DESC) sub"
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    for line in result.stdout.strip().split("\n"):
        if "=" in line:
            k, v = line.split("=", 1)
            params[k.strip()] = v.strip()

    # Step 2: Overlay active plan values (v_active_plan resolves supersession by created_at DESC)
    has_plan = False
    result = subprocess.run(
        db_cmd + ["SELECT parameter, value FROM v_active_plan"], capture_output=True, text=True, timeout=5
    )
    for line in result.stdout.strip().split("\n"):
        if "=" in line:
            k, v = line.split("=", 1)
            params[k.strip()] = v.strip()
            has_plan = True

    # Step 3: Build output
    lines = [f"{k}={v}" for k, v in sorted(params.items())]
    lines.append(f"source={'merged' if has_plan else 'fallback'}")

    # Next upcoming change
    result = subprocess.run(
        db_cmd
        + ["SELECT ts || '|' || parameter || '|' || value FROM setpoint_plan WHERE ts > now() ORDER BY ts LIMIT 1"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.stdout.strip():
        parts = result.stdout.strip().split("|")
        if len(parts) == 3:
            lines.append(f"next_ts={parts[0]}")
            lines.append(f"next_param={parts[1]}")
            lines.append(f"next_value={parts[2]}")

    # Occupancy state (real-time from system_state, written by occupancy-bridge.py)
    result = subprocess.run(
        db_cmd + ["SELECT value FROM system_state WHERE entity = 'occupancy' ORDER BY ts DESC LIMIT 1"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    occ = result.stdout.strip()
    lines.append(f"occupancy={'1' if occ == 'occupied' else '0'}")

    # Outdoor conditions (from Tempest via climate table — for ESP32 enthalpy computation)
    result = subprocess.run(
        db_cmd
        + [
            "SELECT round(outdoor_temp_f::numeric,1) || '|' || round(outdoor_rh_pct::numeric,1) "
            "FROM climate WHERE outdoor_temp_f IS NOT NULL ORDER BY ts DESC LIMIT 1"
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    outdoor = result.stdout.strip()
    if "|" in outdoor:
        parts = outdoor.split("|")
        lines.append(f"outdoor_temp={parts[0]}")
        lines.append(f"outdoor_rh={parts[1]}")

    return "\n".join(lines) + "\n"


class LutronHandler(BaseHTTPRequestHandler):
    """HTTP request handler for grow light and setpoint control."""

    def log_message(self, format, *args):
        log.info(format, *args)

    def _respond(self, code: int, body: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_GET(self):
        if self.path == "/lights":
            # Fetch current state from HA
            result = {}
            for name, cfg in LIGHTS.items():
                state = ha_get_state(cfg["ha_entity"])
                result[name] = {"state": state, "entity": cfg["ha_entity"]}
                _light_state[name] = state == "on" if state else None
            self._respond(200, result)

        elif self.path == "/health":
            self._respond(200, {"status": "ok", "lights": dict(_light_state)})

        elif self.path == "/setpoints":
            # Serve current+next planned setpoints as key=value text
            # ESP32 fetches this every 5 minutes for pull-based schedule tracking
            try:
                text = get_setpoint_text_sync()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(text.encode())
            except Exception as e:
                log.error("Setpoint query failed: %s", e)
                self._respond(500, {"error": str(e)})

        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        # Parse: /lights/{name}/{action}
        parts = self.path.strip("/").split("/")
        if len(parts) != 3 or parts[0] != "lights":
            self._respond(400, {"error": "use /lights/{main|grow}/{on|off}"})
            return

        name = parts[1]
        action = parts[2]

        if name not in LIGHTS:
            self._respond(400, {"error": f"unknown light: {name}. Use main or grow"})
            return
        if action not in ("on", "off"):
            self._respond(400, {"error": f"unknown action: {action}. Use on or off"})
            return

        cfg = LIGHTS[name]
        service = f"turn_{action}"
        success = ha_call(service, cfg["ha_entity"])

        if success:
            is_on = action == "on"
            _light_state[name] = is_on
            # Record state change async
            loop = asyncio.new_event_loop()
            loop.run_until_complete(record_state_change(cfg["equipment"], is_on))
            loop.close()
            self._respond(200, {"light": name, "action": action, "success": True})
            log.info("Light %s → %s", name, action.upper())
        else:
            self._respond(502, {"light": name, "action": action, "success": False, "error": "HA call failed"})


async def main():
    global _db_pool

    log.info("Starting Lutron proxy on %s:%d", LISTEN_HOST, LISTEN_PORT)

    # Connect to DB
    _db_pool = await asyncpg.create_pool(get_db_url(), min_size=1, max_size=3)
    log.info("DB pool ready")

    # Fetch initial light state
    for name, cfg in LIGHTS.items():
        state = ha_get_state(cfg["ha_entity"])
        _light_state[name] = state == "on" if state else None
        log.info("Initial state: %s = %s", name, state)

    # Run HTTP server in a thread
    server = HTTPServer((LISTEN_HOST, LISTEN_PORT), LutronHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    log.info("HTTP server listening on %s:%d", LISTEN_HOST, LISTEN_PORT)

    # Keep alive
    try:
        while True:
            await asyncio.sleep(60)
            # Periodically refresh HA token in case it was rotated
            global _ha_token
            try:
                _ha_token = load_token()
            except Exception:
                pass
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
