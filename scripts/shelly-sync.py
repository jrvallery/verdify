#!/usr/bin/env /srv/greenhouse/.venv/bin/python3
"""
shelly-sync.py — Sync Shelly Pro EM50 electricity meter data from HA into energy table.

The Shelly Pro EM50 (ac15186daafc) monitors the greenhouse electrical panel:
  Channel 0: General circuit (fans, fog, vent, grow lights) — single CT clamp
  Channel 1: Heater circuit (heat2 gas igniter, heat1 electric) — single CT clamp

NOTE: watts_fans is always 0 because the Shelly only has 2 CT clamps and cannot
distinguish fans (52W each) from other loads on the general circuit (ch0).
To break out fan power, a third CT clamp or smart plug would be needed.

Fetches current power/energy from HA every 5 minutes.
Also supports --backfill to pull historical data.

Usage:
    shelly-sync.py             # run once (cron mode)
    shelly-sync.py --backfill  # backfill from HA history
"""

import asyncio
import json
import logging
import sys
import urllib.request
from datetime import UTC, datetime, timedelta

import asyncpg

HA_URL = "http://192.168.30.107:8123"
TOKEN = open("/mnt/jason/agents/shared/credentials/ha_token.txt").read().strip()

# Shelly Pro EM50 greenhouse meter
SHELLY_PREFIX = "sensor.shellyproem50_ac15186daafc_energy_meter"
ENTITIES = {
    f"{SHELLY_PREFIX}_0_power": ("ch0_power_w", None),
    f"{SHELLY_PREFIX}_0_total_active_energy": ("ch0_energy_kwh", None),
    f"{SHELLY_PREFIX}_0_current": ("ch0_current_a", None),
    f"{SHELLY_PREFIX}_0_apparent_power": ("ch0_apparent_va", None),
    f"{SHELLY_PREFIX}_1_power": ("ch1_power_w", lambda v: abs(v)),  # heater shows negative
    # NOTE: ch1 total_active_energy entity does not exist in HA (only ch0 has it)
    f"{SHELLY_PREFIX}_1_apparent_power": ("ch1_apparent_va", None),
}

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [shelly-sync] %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)


def get_db_url() -> str:
    pw = "verdify"
    with open("/srv/verdify/.env") as f:
        for line in f:
            if line.strip().startswith("POSTGRES_PASSWORD="):
                pw = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    return f"postgresql://verdify:{pw}@localhost:5432/verdify"


def parse_float(s):
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def fetch_ha_states(entity_ids):
    """Fetch current states for entities from HA."""
    results = {}
    for eid in entity_ids:
        url = f"{HA_URL}/api/states/{eid}"
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                results[eid] = json.loads(resp.read())
        except Exception as e:
            log.warning("Failed to fetch %s: %s", eid, e)
    return results


def fetch_ha_history(entity_id, start, end):
    """Fetch history for one entity from HA."""
    records = []
    current = start
    while current < end:
        day_end = min(current + timedelta(days=1), end)
        start_str = current.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = day_end.strftime("%Y-%m-%dT%H:%M:%SZ")
        url = (
            f"{HA_URL}/api/history/period/{start_str}?filter_entity_id={entity_id}&end_time={end_str}&minimal_response"
        )
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                if data and data[0]:
                    for r in data[0]:
                        if r["state"] not in ("unavailable", "unknown", ""):
                            val = parse_float(r["state"])
                            if val is not None:
                                ts = datetime.fromisoformat(r["last_changed"].replace("Z", "+00:00"))
                                records.append((ts, val))
        except Exception as e:
            log.warning("  %s: %s", current.date(), e)
        current = day_end
    return records


async def sync_current(conn):
    """Fetch current Shelly readings and insert into energy table."""
    states = fetch_ha_states(list(ENTITIES.keys()))
    if not states:
        log.warning("No Shelly states returned")
        return

    now = datetime.now(UTC)
    vals = {}
    for eid, (col, conv) in ENTITIES.items():
        if eid in states:
            v = parse_float(states[eid].get("state", ""))
            if v is not None:
                vals[col] = conv(v) if conv else v

    if not vals:
        return

    # Map to energy table columns
    watts_total = vals.get("ch0_power_w", 0) + vals.get("ch1_power_w", 0)
    kwh_total = vals.get("ch0_energy_kwh") or 0  # only ch0 has cumulative energy in HA

    await conn.execute(
        """
        INSERT INTO energy (ts, watts_total, watts_heat, watts_fans, watts_other, kwh_today)
        VALUES ($1, $2, $3, $4, $5, $6)
    """,
        now,
        watts_total,
        vals.get("ch1_power_w", 0),  # heater channel
        0,  # can't distinguish fans from general circuit
        vals.get("ch0_power_w", 0),  # general circuit
        kwh_total,
    )
    log.info(
        "Shelly: total=%dW (ch0=%dW ch1=%dW) cumulative=%.1f kWh",
        watts_total,
        vals.get("ch0_power_w", 0),
        vals.get("ch1_power_w", 0),
        kwh_total,
    )


async def backfill(conn):
    """Pull Shelly history from HA and populate energy table."""
    start = datetime(2025, 8, 1, tzinfo=UTC)
    end = datetime.now(UTC)

    # Fetch power readings for both channels
    log.info("Fetching Shelly ch0 power history...")
    ch0_power = fetch_ha_history(f"{SHELLY_PREFIX}_0_power", start, end)
    log.info("Got %d ch0 power readings", len(ch0_power))

    log.info("Fetching Shelly ch1 power history...")
    ch1_power = fetch_ha_history(f"{SHELLY_PREFIX}_1_power", start, end)
    log.info("Got %d ch1 power readings", len(ch1_power))

    log.info("Fetching Shelly ch0 energy history...")
    ch0_energy = fetch_ha_history(f"{SHELLY_PREFIX}_0_total_active_energy", start, end)
    log.info("Got %d ch0 energy readings", len(ch0_energy))

    # Build a time-indexed map of ch1 power for joining
    ch1_map = {ts.replace(second=0, microsecond=0): abs(val) for ts, val in ch1_power}
    ch0_energy_map = {ts.replace(second=0, microsecond=0): val for ts, val in ch0_energy}

    # Use ch0 power timestamps as the base, join with ch1
    rows = []
    for ts, ch0_w in ch0_power:
        key = ts.replace(second=0, microsecond=0)
        ch1_w = ch1_map.get(key, 0)
        kwh = ch0_energy_map.get(key)  # only ch0 has cumulative energy
        rows.append((ts, ch0_w + ch1_w, ch1_w, 0, ch0_w, kwh))

    if not rows:
        log.info("No rows to insert")
        return

    # Bulk insert, skip existing timestamps
    await conn.execute(
        "CREATE TEMP TABLE _shelly (ts TIMESTAMPTZ, watts_total FLOAT, watts_heat FLOAT, watts_fans FLOAT, watts_other FLOAT, kwh_today FLOAT)"
    )
    await conn.executemany("INSERT INTO _shelly VALUES ($1,$2,$3,$4,$5,$6)", rows)

    result = await conn.execute("""
        INSERT INTO energy (ts, watts_total, watts_heat, watts_fans, watts_other, kwh_today)
        SELECT s.ts, s.watts_total, s.watts_heat, s.watts_fans, s.watts_other, s.kwh_today
        FROM _shelly s
        WHERE NOT EXISTS (
            SELECT 1 FROM energy e WHERE e.ts BETWEEN s.ts - interval '30 seconds' AND s.ts + interval '30 seconds'
        )
    """)
    count = int(result.split()[-1]) if result else 0
    await conn.execute("DROP TABLE _shelly")
    log.info("Backfilled %d energy rows from Shelly history", count)


async def main():
    conn = await asyncpg.connect(get_db_url())
    try:
        if "--backfill" in sys.argv:
            await backfill(conn)
        else:
            await sync_current(conn)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
