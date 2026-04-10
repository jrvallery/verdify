#!/usr/bin/env /srv/greenhouse/.venv/bin/python3
"""
ha-sensor-sync.py — Sync HA-managed devices into Verdify TimescaleDB.

Polls HA REST API every 5 minutes via cron. Data sources:
1. YINMIK water quality tester → climate table hydro columns
2. Grow lights (Lutron) → equipment_state table
3. Config switches → equipment_state table
4. Frigate occupancy → system_state table

Note: Tempest weather data is handled by tempest-sync.py (dedicated script).

Usage:
    ha-sensor-sync.py           # run once
    ha-sensor-sync.py --daemon  # run every 5 min (foreground)
"""

import asyncio
import json
import logging
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

import asyncpg

# --- Configuration ---
HA_URL = "http://192.168.30.107:8123"
HA_TOKEN_FILE = "/mnt/jason/agents/shared/credentials/ha_token.txt"
POLL_INTERVAL_S = 300  # 5 minutes
STATE_FILE = "/srv/verdify/state/ha-sensor-sync-state.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ha-sync] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# --- Tempest weather data now handled by tempest-sync.py (dedicated script) ---
# TEMPEST_MAP removed — see /srv/verdify/scripts/tempest-sync.py

# --- Frigate occupancy sensor ---
OCCUPANCY_ENTITIES = {
    "binary_sensor.greenhouse_zone_person_occupancy": "occupancy",
}

# --- Grow light entities ---
LIGHT_ENTITIES = {
    "light.greenhouse_main": "grow_light_main",
    "light.greenhouse_grow":  "grow_light_grow",
}

# --- Hydroponic water tester (LocalTuya + BLE) ---
HYDRO_MAP = {
    # LocalTuya (primary — renamed from pool_* to greenhouse_hydroponic_*)
    "sensor.greenhouse_hydroponic_ec":         ("hydro_ec_us_cm",    None),
    "sensor.greenhouse_hydroponic_orp":        ("hydro_orp_mv",      None),
    "sensor.greenhouse_hydroponic_ph":         ("hydro_ph",          None),
    "sensor.greenhouse_hydroponic_tds":        ("hydro_tds_ppm",     None),     # ppm from LocalTuya, column is ppt (legacy name)
    "sensor.greenhouse_hydroponic_water_temp": ("hydro_water_temp_f", lambda v: v * 9.0/5.0 + 32.0),  # °C → °F
    # Battery
    "sensor.greenhouse_hydroponic_yinmik_battery": ("hydro_battery_pct", None),
}

# --- HA-computed sensors and input_* entities ---
# REMOVED: All greenhouse_* HA template sensors and input helpers were deleted from HA
# when control moved to ESP32 firmware. They all return HTTP 404.
# Removed entities:
#   sensor.greenhouse_grow_light_hours_today, grow_light_reason, fog_vpd_delta,
#   forecast_today, fan_state, heat_state, humidifan_state, dashboard_status
#   input_number.greenhouse_dif, dli_target, gdd_accumulated, gdd_base_temp, last_fog_vpd_delta
#   input_boolean.greenhouse_grow_light_inhibit
#   input_datetime.greenhouse_grow_light_cutoff

# --- Config switches → equipment_state ---
HA_CONFIG_SWITCHES = {
    "switch.greenhouse_economiser_enabled":          "economiser_enabled",
    "switch.greenhouse_fog_closes_vent":              "fog_closes_vent",
    "switch.greenhouse_irrigation_enabled":           "irrigation_enabled",
    "switch.greenhouse_irrigation_wall_enabled":      "irrigation_wall_enabled",
    "switch.greenhouse_irrigation_center_enabled":    "irrigation_center_enabled",
    "switch.greenhouse_irrigation_weather_skip":      "irrigation_weather_skip",
}


def load_token() -> str:
    with open(HA_TOKEN_FILE) as f:
        return f.read().strip()


def load_state() -> dict:
    """Load last known light states to detect changes."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def fetch_states(token: str, entity_ids: list[str]) -> dict[str, dict]:
    """Fetch current states for multiple entities from HA API."""
    results = {}
    for eid in entity_ids:
        url = f"{HA_URL}/api/states/{eid}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                results[eid] = data
        except Exception as e:
            log.warning("Failed to fetch %s: %s", eid, e)
    return results


def parse_float(state: str) -> float | None:
    if state in ("unavailable", "unknown", "None", ""):
        return None
    try:
        return float(state)
    except (ValueError, TypeError):
        return None


def get_db_url() -> str:
    env_file = "/srv/verdify/.env"
    pw = "verdify"
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if line.strip().startswith("POSTGRES_PASSWORD="):
                    pw = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    return f"postgresql://verdify:{pw}@localhost:5432/verdify"


async def sync_once(db_url: str) -> None:
    token = load_token()
    now = datetime.now(timezone.utc)

    # Collect all entity IDs to fetch
    all_entities = (list(LIGHT_ENTITIES.keys()) + list(HYDRO_MAP.keys())
                    + list(HA_CONFIG_SWITCHES.keys()) + list(OCCUPANCY_ENTITIES.keys()))
    states = fetch_states(token, all_entities)

    if not states:
        log.warning("No states returned from HA")
        return

    conn = await asyncpg.connect(db_url)
    try:
        # --- 1. Hydro water tester → climate row ---
        climate_cols = {"ts": now}
        for eid, (col, converter) in HYDRO_MAP.items():
            if col is None:
                continue
            if eid in states:
                val = parse_float(states[eid].get("state", ""))
                if val is not None:
                    climate_cols[col] = converter(val) if converter else val

        # Merge hydro data into the most recent ESP32 row (within 5 min)
        if len(climate_cols) > 1:  # more than just ts
            latest_esp32 = await conn.fetchval(
                "SELECT ts FROM climate WHERE ts > now() - interval '5 minutes' "
                "AND temp_avg IS NOT NULL ORDER BY ts DESC LIMIT 1"
            )
            if latest_esp32:
                hydro_cols = {c: v for c, v in climate_cols.items() if c != "ts"}
                if hydro_cols:
                    set_parts = []
                    set_vals = []
                    for i, (c, v) in enumerate(hydro_cols.items()):
                        set_parts.append(f"{c} = ${i+1}")
                        set_vals.append(v)
                    set_vals.append(latest_esp32)
                    await conn.execute(
                        f"UPDATE climate SET {', '.join(set_parts)} WHERE ts = ${len(set_vals)}",
                        *set_vals
                    )
                    log.info("Merged hydro into ESP32 row: %s",
                             ", ".join(f"{k}={v}" for k, v in hydro_cols.items()))
            else:
                cols = list(climate_cols.keys())
                vals = [climate_cols[c] for c in cols]
                placeholders = ", ".join(f"${i+1}" for i in range(len(vals)))
                col_names = ", ".join(cols)
                await conn.execute(f"INSERT INTO climate ({col_names}) VALUES ({placeholders})", *vals)
                log.info("Hydro standalone INSERT (no recent ESP32 row)")

        # --- 3. Grow lights → equipment_state (on-change only) ---
        prev_state = load_state()
        new_state = {}
        for eid, equip_name in LIGHT_ENTITIES.items():
            if eid in states:
                raw = states[eid].get("state", "")
                is_on = raw == "on"
                new_state[eid] = is_on
                prev = prev_state.get(eid)
                if prev is None or prev != is_on:
                    await conn.execute(
                        "INSERT INTO equipment_state (ts, equipment, state) VALUES ($1, $2, $3)",
                        now, equip_name, is_on,
                    )
                    log.info("Light state change: %s → %s", equip_name, "ON" if is_on else "OFF")

        save_state(new_state)

        # --- 4. Config switches → equipment_state (on-change only) ---
        for eid, equip_name in HA_CONFIG_SWITCHES.items():
            if eid in states:
                raw = states[eid].get("state", "")
                is_on = raw == "on"
                prev_key = f"switch_{equip_name}"
                prev = prev_state.get(prev_key)
                if prev is None or prev != is_on:
                    await conn.execute(
                        "INSERT INTO equipment_state (ts, equipment, state) VALUES ($1, $2, $3)",
                        now, equip_name, is_on,
                    )
                    log.info("Config switch: %s → %s", equip_name, "ON" if is_on else "OFF")
                new_state[prev_key] = is_on

        # --- 5. Frigate occupancy → system_state (on-change only) ---
        for eid, entity_name in OCCUPANCY_ENTITIES.items():
            if eid in states:
                raw = states[eid].get("state", "")
                if raw in ("unavailable", "unknown"):
                    continue
                val = "occupied" if raw == "on" else "empty"
                prev_key = f"occupancy_{entity_name}"
                if prev_state.get(prev_key) != val:
                    await conn.execute(
                        "INSERT INTO system_state (ts, entity, value) VALUES ($1, $2, $3)",
                        now, entity_name, val,
                    )
                    new_state[prev_key] = val
                    log.info("Occupancy: %s → %s", entity_name, val)
                else:
                    new_state[prev_key] = val

        save_state(new_state)

    finally:
        await conn.close()


async def run_daemon(db_url: str) -> None:
    log.info("Starting HA sensor sync daemon (interval: %ds)", POLL_INTERVAL_S)
    while True:
        try:
            await sync_once(db_url)
        except Exception as e:
            log.error("Sync error: %s", e)
        await asyncio.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    db_url = get_db_url()
    if "--daemon" in sys.argv:
        asyncio.run(run_daemon(db_url))
    else:
        asyncio.run(sync_once(db_url))
