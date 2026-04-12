"""
tasks.py — Periodic background tasks absorbed from standalone cron scripts.

Each function is an async coroutine that takes an asyncpg.Pool and runs one
unit of work. Called by task_loop() in ingestor.py on defined intervals.

Replaces 10 cron jobs with a single in-process task scheduler.
"""

import asyncio
import json
import logging
import urllib.error
import urllib.request
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import asyncpg

log = logging.getLogger("tasks")

# ── Shared config (from config.py / environment) ────────────────
from config import (
    HA_TOKEN_FILE,
    HA_URL,
    SLACK_CHANNEL,
    SLACK_TOKEN_FILE,
    STATE_DIR,
    WATTAGES,
)
from config import (
    load_token as _load_token,
)


def _parse_float(s) -> float | None:
    if s in ("unavailable", "unknown", "None", "", None):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _fetch_ha_entity(token: str, entity_id: str) -> dict | None:
    """Fetch a single HA entity state (blocking — run in executor for batch)."""
    url = f"{HA_URL}/api/states/{entity_id}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def _fetch_ha_batch(token: str, entity_ids: list[str]) -> dict[str, dict]:
    """Fetch multiple HA entity states (blocking)."""
    results = {}
    for eid in entity_ids:
        data = _fetch_ha_entity(token, eid)
        if data:
            results[eid] = data
    return results


def _post_slack(token: str, channel: str, text: str, thread_ts: str | None = None) -> str | None:
    payload = {"channel": channel, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result.get("ts") if result.get("ok") else None
    except Exception:
        return None


# ═════════════════════════════════════════════════════════════════
# 1. WATER FLOWING + LEAK DETECTION (every 60s)
# ═════════════════════════════════════════════════════════════════
_leak_counter = 0


async def water_flowing_sync(pool: asyncpg.Pool) -> None:
    global _leak_counter
    async with pool.acquire() as conn:
        flow = await conn.fetchval("SELECT flow_gpm FROM climate WHERE flow_gpm IS NOT NULL ORDER BY ts DESC LIMIT 1")
        flow = float(flow) if flow is not None else 0.0

        # water_flowing
        flowing = flow > 0.05
        current = await conn.fetchval(
            "SELECT state FROM equipment_state WHERE equipment = 'water_flowing' ORDER BY ts DESC LIMIT 1"
        )
        if current is None or flowing != current:
            await conn.execute(
                "INSERT INTO equipment_state (ts, equipment, state) VALUES (NOW(), 'water_flowing', $1)", flowing
            )

        # leak_detected
        leak_candidate = False
        if flow > 0.10:
            valve_names = [
                "mister_south",
                "mister_west",
                "mister_center",
                "mister_any",
                "drip_wall",
                "drip_center",
                "mister_south_fert",
                "mister_west_fert",
                "drip_wall_fert",
                "drip_center_fert",
                "fert_master_valve",
            ]
            ph = ", ".join(f"${i + 1}" for i in range(len(valve_names)))
            any_open = await conn.fetchval(
                f"""
                SELECT bool_or(sub.state) FROM (
                    SELECT DISTINCT ON (equipment) state
                    FROM equipment_state WHERE equipment IN ({ph})
                    ORDER BY equipment, ts DESC
                ) sub
            """,
                *valve_names,
            )
            if not any_open:
                leak_candidate = True

        _leak_counter = (_leak_counter + 1) if leak_candidate else 0
        leak = _leak_counter >= 3

        current_leak = await conn.fetchval(
            "SELECT state FROM equipment_state WHERE equipment = 'leak_detected' ORDER BY ts DESC LIMIT 1"
        )
        if current_leak is None or leak != current_leak:
            await conn.execute(
                "INSERT INTO equipment_state (ts, equipment, state) VALUES (NOW(), 'leak_detected', $1)", leak
            )


# ═════════════════════════════════════════════════════════════════
# 2. MATERIALIZED VIEW REFRESH (every 300s)
# ═════════════════════════════════════════════════════════════════
async def matview_refresh(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute("SELECT refresh_relay_stuck(0, '{}'::jsonb)")
        await conn.execute("SELECT refresh_climate_merged(0, '{}'::jsonb)")
    log.debug("Materialized views refreshed")


# ═════════════════════════════════════════════════════════════════
# 3. SHELLY ENERGY SYNC (every 300s)
# ═════════════════════════════════════════════════════════════════
_SHELLY_PREFIX = "sensor.shellyproem50_ac15186daafc_energy_meter"
_SHELLY_ENTITIES = {
    f"{_SHELLY_PREFIX}_0_power": ("ch0_power_w", None),
    f"{_SHELLY_PREFIX}_0_total_active_energy": ("ch0_energy_kwh", None),
    f"{_SHELLY_PREFIX}_0_current": ("ch0_current_a", None),
    f"{_SHELLY_PREFIX}_0_apparent_power": ("ch0_apparent_va", None),
    f"{_SHELLY_PREFIX}_1_power": ("ch1_power_w", lambda v: abs(v)),
    f"{_SHELLY_PREFIX}_1_apparent_power": ("ch1_apparent_va", None),
}


async def shelly_sync(pool: asyncpg.Pool) -> None:
    token = _load_token(HA_TOKEN_FILE)
    loop = asyncio.get_event_loop()
    states = await loop.run_in_executor(None, _fetch_ha_batch, token, list(_SHELLY_ENTITIES.keys()))
    if not states:
        return

    vals = {}
    for eid, (col, conv) in _SHELLY_ENTITIES.items():
        if eid in states:
            v = _parse_float(states[eid].get("state", ""))
            if v is not None:
                vals[col] = conv(v) if conv else v
    if not vals:
        return

    watts_total = vals.get("ch0_power_w", 0) + vals.get("ch1_power_w", 0)
    kwh_total = vals.get("ch0_energy_kwh") or 0

    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO energy (ts, watts_total, watts_heat, watts_fans, watts_other, kwh_today) VALUES ($1,$2,$3,$4,$5,$6)",
            datetime.now(UTC),
            watts_total,
            vals.get("ch1_power_w", 0),
            0,
            vals.get("ch0_power_w", 0),
            kwh_total,
        )
    log.debug("Shelly: %dW (ch0=%d ch1=%d)", watts_total, vals.get("ch0_power_w", 0), vals.get("ch1_power_w", 0))


# ═════════════════════════════════════════════════════════════════
# 4. TEMPEST WEATHER SYNC (every 300s)
# ═════════════════════════════════════════════════════════════════
_TEMPEST_MAP = {
    "sensor.panorama_temperature": ("outdoor_temp_f", None),
    "sensor.panorama_humidity": ("outdoor_rh_pct", None),
    "sensor.panorama_wind_speed": ("wind_speed_mph", None),
    "sensor.panorama_wind_direction": ("wind_direction_deg", None),
    "sensor.panorama_illuminance": ("outdoor_lux", None),
    "sensor.panorama_irradiance": ("solar_irradiance_w_m2", None),
    "sensor.panorama_air_pressure": ("pressure_hpa", lambda v: v * 33.8639),
    "sensor.panorama_precipitation": ("precip_in", None),
    "sensor.panorama_uv_index": ("uv_index", None),
    "sensor.panorama_wind_gust": ("wind_gust_mph", None),
    "sensor.panorama_wind_lull": ("wind_lull_mph", None),
    "sensor.panorama_wind_speed_average": ("wind_speed_avg_mph", None),
    "sensor.panorama_wind_direction_average": ("wind_direction_avg_deg", None),
    "sensor.panorama_feels_like": ("feels_like_f", None),
    "sensor.panorama_wet_bulb_temperature": ("wet_bulb_temp_f", None),
    "sensor.panorama_vapor_pressure": ("vapor_pressure_inhg", None),
    "sensor.panorama_air_density": ("air_density_kg_m3", None),
    "sensor.panorama_precipitation_intensity": ("precip_intensity_in_h", None),
    "sensor.panorama_lightning_count": ("lightning_count", lambda v: int(v)),
    "sensor.panorama_lightning_average_distance": ("lightning_avg_dist_mi", None),
}


async def tempest_sync(pool: asyncpg.Pool) -> None:
    token = _load_token(HA_TOKEN_FILE)
    loop = asyncio.get_event_loop()
    states = await loop.run_in_executor(None, _fetch_ha_batch, token, list(_TEMPEST_MAP.keys()))
    if not states:
        return

    now = datetime.now(UTC)
    outdoor_cols = {}
    for eid, (col, conv) in _TEMPEST_MAP.items():
        if eid in states:
            val = _parse_float(states[eid].get("state", ""))
            if val is not None:
                outdoor_cols[col] = conv(val) if conv else val
    if not outdoor_cols:
        return

    async with pool.acquire() as conn:
        # Update ALL recent climate rows missing outdoor data (not just the latest)
        parts, vals = [], []
        for i, (c, v) in enumerate(outdoor_cols.items()):
            parts.append(f"{c} = ${i + 1}")
            vals.append(v)
        count = await conn.fetchval(
            "SELECT count(*) FROM climate WHERE ts > now() - interval '6 minutes' AND temp_avg IS NOT NULL AND outdoor_temp_f IS NULL"
        )
        if count and count > 0:
            result = await conn.execute(
                f"UPDATE climate SET {', '.join(parts)} WHERE ts > now() - interval '6 minutes' AND temp_avg IS NOT NULL AND outdoor_temp_f IS NULL",
                *vals,
            )
            log.debug("Tempest: %d outdoor cols synced to %s rows", len(outdoor_cols), result.split()[-1])
        elif not count or count == 0:
            # All recent rows already have outdoor data, update the latest one with freshest values
            latest = await conn.fetchval(
                "SELECT ts FROM climate WHERE ts > now() - interval '5 minutes' AND temp_avg IS NOT NULL ORDER BY ts DESC LIMIT 1"
            )
            if latest:
                vals.append(latest)
                await conn.execute(f"UPDATE climate SET {', '.join(parts)} WHERE ts = ${len(vals)}", *vals)
                log.debug("Tempest: %d outdoor cols refreshed on latest row", len(outdoor_cols))
            else:
                outdoor_cols["ts"] = now
                cols = list(outdoor_cols.keys())
                ins_vals = [outdoor_cols[c] for c in cols]
                ph = ", ".join(f"${i + 1}" for i in range(len(ins_vals)))
                await conn.execute(f"INSERT INTO climate ({', '.join(cols)}) VALUES ({ph})", *ins_vals)
                log.debug("Tempest: inserted new outdoor-only row")


# ═════════════════════════════════════════════════════════════════
# 5. HA SENSOR SYNC — hydro, lights, switches, occupancy (every 300s)
# ═════════════════════════════════════════════════════════════════
_HYDRO_MAP = {
    "sensor.greenhouse_hydroponic_ec": ("hydro_ec_us_cm", None),
    "sensor.greenhouse_hydroponic_orp": ("hydro_orp_mv", None),
    "sensor.greenhouse_hydroponic_ph": ("hydro_ph", None),
    "sensor.greenhouse_hydroponic_tds": ("hydro_tds_ppm", None),
    "sensor.greenhouse_hydroponic_water_temp": ("hydro_water_temp_f", lambda v: v * 9.0 / 5.0 + 32.0),
    "sensor.greenhouse_hydroponic_yinmik_battery": ("hydro_battery_pct", None),
}
_LIGHT_ENTITIES = {
    "light.greenhouse_main": "grow_light_main",
    "light.greenhouse_grow": "grow_light_grow",
}
_HA_SWITCHES = {
    "switch.greenhouse_economiser_enabled": "economiser_enabled",
    "switch.greenhouse_fog_closes_vent": "fog_closes_vent",
    "switch.greenhouse_irrigation_enabled": "irrigation_enabled",
    "switch.greenhouse_irrigation_wall_enabled": "irrigation_wall_enabled",
    "switch.greenhouse_irrigation_center_enabled": "irrigation_center_enabled",
    "switch.greenhouse_irrigation_weather_skip": "irrigation_weather_skip",
}
_OCCUPANCY_ENTITIES = {
    "binary_sensor.greenhouse_zone_person_occupancy": "occupancy",
}
_ha_prev_state: dict = {}
_HA_STATE_FILE = STATE_DIR / "ha-sensor-sync-state.json"


async def ha_sensor_sync(pool: asyncpg.Pool) -> None:
    global _ha_prev_state
    token = _load_token(HA_TOKEN_FILE)
    all_eids = list(_LIGHT_ENTITIES) + list(_HYDRO_MAP) + list(_HA_SWITCHES) + list(_OCCUPANCY_ENTITIES)
    loop = asyncio.get_event_loop()
    states = await loop.run_in_executor(None, _fetch_ha_batch, token, all_eids)
    if not states:
        return

    # Load previous state on first run
    if not _ha_prev_state and _HA_STATE_FILE.exists():
        _ha_prev_state = json.loads(_HA_STATE_FILE.read_text())

    now = datetime.now(UTC)
    new_state = dict(_ha_prev_state)

    async with pool.acquire() as conn:
        # Hydro → climate
        hydro_cols = {}
        for eid, (col, conv) in _HYDRO_MAP.items():
            if eid in states:
                val = _parse_float(states[eid].get("state", ""))
                if val is not None:
                    hydro_cols[col] = conv(val) if conv else val
        if hydro_cols:
            latest = await conn.fetchval(
                "SELECT ts FROM climate WHERE ts > now() - interval '5 minutes' AND temp_avg IS NOT NULL ORDER BY ts DESC LIMIT 1"
            )
            if latest:
                parts, vals = [], []
                for i, (c, v) in enumerate(hydro_cols.items()):
                    parts.append(f"{c} = ${i + 1}")
                    vals.append(v)
                vals.append(latest)
                await conn.execute(f"UPDATE climate SET {', '.join(parts)} WHERE ts = ${len(vals)}", *vals)

        # Grow lights → equipment_state (on-change)
        for eid, equip in _LIGHT_ENTITIES.items():
            if eid in states:
                is_on = states[eid].get("state", "") == "on"
                if new_state.get(eid) != is_on:
                    await conn.execute(
                        "INSERT INTO equipment_state (ts, equipment, state) VALUES ($1, $2, $3)", now, equip, is_on
                    )
                    log.info("Light: %s → %s", equip, "ON" if is_on else "OFF")
                new_state[eid] = is_on

        # Config switches → equipment_state (on-change)
        for eid, equip in _HA_SWITCHES.items():
            if eid in states:
                is_on = states[eid].get("state", "") == "on"
                key = f"switch_{equip}"
                if new_state.get(key) != is_on:
                    await conn.execute(
                        "INSERT INTO equipment_state (ts, equipment, state) VALUES ($1, $2, $3)", now, equip, is_on
                    )
                new_state[key] = is_on

        # Occupancy → system_state (on-change)
        for eid, entity in _OCCUPANCY_ENTITIES.items():
            if eid in states:
                raw = states[eid].get("state", "")
                if raw in ("unavailable", "unknown"):
                    continue
                val = "occupied" if raw == "on" else "empty"
                key = f"occupancy_{entity}"
                if new_state.get(key) != val:
                    await conn.execute(
                        "INSERT INTO system_state (ts, entity, value) VALUES ($1, $2, $3)", now, entity, val
                    )
                new_state[key] = val

    _ha_prev_state = new_state
    _HA_STATE_FILE.write_text(json.dumps(new_state))


# ═════════════════════════════════════════════════════════════════
# 6. ALERT MONITOR (every 300s)
# ═════════════════════════════════════════════════════════════════
async def alert_monitor(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        alerts = []

        # 1. sensor_offline (exclude legacy firmware entities)
        _STALE_EXCLUDE = {"state.mister_state", "state.mister_zone"}
        for r in await conn.fetch(
            "SELECT sensor_id, type, staleness_ratio FROM v_sensor_staleness WHERE is_stale = true"
        ):
            if r["sensor_id"] in _STALE_EXCLUDE:
                continue
            ratio = r["staleness_ratio"]
            alerts.append(
                {
                    "alert_type": "sensor_offline",
                    "severity": "warning",
                    "category": "sensor",
                    "sensor_id": r["sensor_id"],
                    "zone": None,
                    "message": f"Sensor `{r['sensor_id']}` offline ({ratio:.0f}x expected interval)"
                    if ratio
                    else f"Sensor `{r['sensor_id']}` offline",
                    "details": {"type": r["type"], "staleness_ratio": float(ratio) if ratio else None},
                    "metric_value": float(ratio) if ratio else None,
                    "threshold_value": None,
                }
            )

        # 2. relay_stuck
        for r in await conn.fetch(
            "SELECT equipment, hours_on, threshold_hours FROM v_relay_stuck WHERE is_stuck = true"
        ):
            alerts.append(
                {
                    "alert_type": "relay_stuck",
                    "severity": "warning",
                    "category": "equipment",
                    "sensor_id": f"equipment.{r['equipment']}",
                    "zone": None,
                    "message": f"Relay `{r['equipment']}` stuck ON for {r['hours_on']:.1f}h",
                    "details": {"hours_on": float(r["hours_on"])},
                    "metric_value": float(r["hours_on"]),
                    "threshold_value": float(r["threshold_hours"]),
                }
            )

        # 3. VPD stress
        row = await conn.fetchrow(
            "SELECT vpd_stress_hours FROM v_stress_hours_today WHERE date >= date_trunc('day', now() AT TIME ZONE 'America/Denver') ORDER BY date DESC LIMIT 1"
        )
        if row and row["vpd_stress_hours"] and float(row["vpd_stress_hours"]) > 2.0:
            hrs = float(row["vpd_stress_hours"])
            alerts.append(
                {
                    "alert_type": "vpd_stress",
                    "severity": "warning",
                    "category": "climate",
                    "sensor_id": "climate.vpd_avg",
                    "zone": None,
                    "message": f"VPD stress: {hrs:.1f} hours today",
                    "details": {"vpd_stress_hours": hrs},
                    "metric_value": hrs,
                    "threshold_value": 2.0,
                }
            )

        # 4. Temp safety
        row = await conn.fetchrow(
            "SELECT ts, temp_avg FROM climate WHERE temp_avg IS NOT NULL AND ts >= now() - interval '10 minutes' ORDER BY ts DESC LIMIT 1"
        )
        if row and row["temp_avg"] is not None:
            t = row["temp_avg"]
            if t < 40:
                alerts.append(
                    {
                        "alert_type": "temp_safety",
                        "severity": "critical",
                        "category": "climate",
                        "sensor_id": "climate.temp_avg",
                        "zone": None,
                        "message": f"FREEZE WARNING — {t:.1f}°F",
                        "details": {"temp_f": t},
                        "metric_value": t,
                        "threshold_value": 40.0,
                    }
                )
            elif t > 100:
                alerts.append(
                    {
                        "alert_type": "temp_safety",
                        "severity": "critical",
                        "category": "climate",
                        "sensor_id": "climate.temp_avg",
                        "zone": None,
                        "message": f"OVERHEAT WARNING — {t:.1f}°F",
                        "details": {"temp_f": t},
                        "metric_value": t,
                        "threshold_value": 100.0,
                    }
                )

        # 4b. VPD extreme
        vpd_row = await conn.fetchrow(
            "SELECT vpd_avg FROM climate WHERE vpd_avg IS NOT NULL AND ts >= now() - interval '10 minutes' ORDER BY ts DESC LIMIT 1"
        )
        if vpd_row and vpd_row["vpd_avg"] is not None:
            v = vpd_row["vpd_avg"]
            if v < 0.3 or v > 3.0:
                alerts.append(
                    {
                        "alert_type": "vpd_extreme",
                        "severity": "warning",
                        "category": "climate",
                        "sensor_id": "climate.vpd_avg",
                        "zone": None,
                        "message": f"VPD {'low' if v < 0.3 else 'high'}: {v:.2f} kPa",
                        "details": {"vpd_kpa": v},
                        "metric_value": v,
                        "threshold_value": 0.3 if v < 0.3 else 3.0,
                    }
                )

        # 5. Leak
        row = await conn.fetchrow(
            "SELECT ts, state FROM equipment_state WHERE equipment = 'leak_detected' ORDER BY ts DESC LIMIT 1"
        )
        if row and row["state"]:
            alerts.append(
                {
                    "alert_type": "leak_detected",
                    "severity": "critical",
                    "category": "water",
                    "sensor_id": "equipment.leak_detected",
                    "zone": None,
                    "message": f"LEAK DETECTED since {row['ts'].strftime('%H:%M')} UTC",
                    "details": {"since": row["ts"].isoformat()},
                    "metric_value": None,
                    "threshold_value": None,
                }
            )

        # 6. ESP32 reboot
        row = await conn.fetchrow(
            "SELECT uptime_s, reset_reason FROM diagnostics WHERE ts >= now() - interval '10 minutes' AND uptime_s IS NOT NULL ORDER BY ts DESC LIMIT 1"
        )
        if row and row["uptime_s"] < 300:
            alerts.append(
                {
                    "alert_type": "esp32_reboot",
                    "severity": "info",
                    "category": "system",
                    "sensor_id": "diag.uptime_s",
                    "zone": None,
                    "message": f"ESP32 rebooted — uptime {row['uptime_s']:.0f}s",
                    "details": {"uptime_s": row["uptime_s"]},
                    "metric_value": None,
                    "threshold_value": None,
                }
            )

        # 7. Planner stale
        plan_age = await conn.fetchval("SELECT EXTRACT(EPOCH FROM now() - MAX(created_at))::int FROM setpoint_plan")
        if plan_age and plan_age > 28800:
            alerts.append(
                {
                    "alert_type": "planner_stale",
                    "severity": "warning",
                    "category": "system",
                    "sensor_id": "system.planner",
                    "zone": None,
                    "message": f"No plan in {plan_age // 3600}h",
                    "details": {"age_s": plan_age},
                    "metric_value": None,
                    "threshold_value": None,
                }
            )

        # 8. Safety value sanity check — catch zeroed/invalid safety rails
        for r in await conn.fetch("""
            SELECT DISTINCT ON (parameter) parameter, value
            FROM setpoint_snapshot
            WHERE parameter IN ('safety_min','safety_max','safety_vpd_min','safety_vpd_max')
              AND ts > now() - interval '5 minutes'
            ORDER BY parameter, ts DESC
        """):
            val = r["value"]
            param = r["parameter"]
            is_invalid = (
                val is None
                or val == 0
                or (param == "safety_min" and (val < 30 or val > 70))
                or (param == "safety_max" and (val < 70 or val > 120))
                or (param == "safety_vpd_min" and val < 0)
                or (param == "safety_vpd_max" and val < 1)
            )
            if is_invalid:
                alerts.append(
                    {
                        "alert_type": "safety_invalid",
                        "severity": "critical",
                        "category": "safety",
                        "sensor_id": f"setpoint.{param}",
                        "zone": None,
                        "message": f"CRITICAL: {param}={val} is invalid — state machine safety compromised",
                        "details": {"parameter": param, "value": val},
                        "metric_value": float(val) if val else 0,
                        "threshold_value": None,
                    }
                )

        # 9. Heat manual override
        heat = await conn.fetchrow("SELECT AVG(watts_heat) AS w FROM energy WHERE ts > now() - interval '10 minutes'")
        if heat and heat["w"] and heat["w"] > 1000:
            h1 = await conn.fetchval(
                "SELECT state FROM equipment_state WHERE equipment = 'heat1' ORDER BY ts DESC LIMIT 1"
            )
            h2 = await conn.fetchval(
                "SELECT state FROM equipment_state WHERE equipment = 'heat2' ORDER BY ts DESC LIMIT 1"
            )
            if not h1 and not h2:
                alerts.append(
                    {
                        "alert_type": "heat_manual_override",
                        "severity": "warning",
                        "category": "equipment",
                        "sensor_id": "equipment.heat1",
                        "zone": None,
                        "message": f"Heat drawing {int(heat['w'])}W but ESP32 reports OFF",
                        "details": {"watts": int(heat["w"])},
                        "metric_value": float(heat["w"]),
                        "threshold_value": 1000.0,
                    }
                )

        # 9. Soil sensor offline (daytime only, 6AM–10PM MDT)
        local_hour = datetime.now(ZoneInfo("America/Denver")).hour
        if 6 <= local_hour < 22:
            soil_cols = [
                ("soil_moisture_south_1", "soil.south_1"),
                ("soil_temp_south_1", "soil.south_1"),
                ("soil_ec_south_1", "soil.south_1"),
                ("soil_moisture_south_2", "soil.south_2"),
                ("soil_temp_south_2", "soil.south_2"),
                ("soil_moisture_west", "soil.west"),
                ("soil_temp_west", "soil.west"),
            ]
            for col, sensor_id in soil_cols:
                non_null = await conn.fetchval(
                    f"SELECT COUNT(*) FROM climate WHERE ts >= now() - interval '30 minutes' AND {col} IS NOT NULL"
                )
                if non_null == 0:
                    alerts.append(
                        {
                            "alert_type": "soil_sensor_offline",
                            "severity": "warning",
                            "category": "sensor",
                            "sensor_id": f"{sensor_id}.{col}",
                            "zone": None,
                            "message": f"Soil sensor `{col}` has no data for 30 min",
                            "details": {"column": col, "sensor": sensor_id},
                            "metric_value": None,
                            "threshold_value": 30.0,
                        }
                    )

        # Reactive trigger marker removed in Sprint 5 P6 — deviation monitor handles replans

        # ── Deduplicate + insert + resolve ──
        active_keys = {(a["alert_type"], a["sensor_id"]) for a in alerts}
        open_rows = await conn.fetch(
            "SELECT id, alert_type, sensor_id, slack_ts FROM alert_log WHERE disposition = 'open'"
        )
        open_keys = {(r["alert_type"], r["sensor_id"]): r for r in open_rows}

        slack_token = None
        new_count = 0
        for a in alerts:
            key = (a["alert_type"], a["sensor_id"])
            if key in open_keys:
                continue
            should_slack = a["alert_type"] not in ("sensor_offline", "esp32_reboot")
            slack_ts = None
            if should_slack:
                if slack_token is None:
                    try:
                        slack_token = _load_token(SLACK_TOKEN_FILE)
                    except Exception:
                        slack_token = ""
                if slack_token:
                    emoji = {
                        "critical": "\U0001f534",
                        "warning": "\U0001f7e1",
                        "warn": "\U0001f7e1",
                        "info": "\u2139\ufe0f",
                    }.get(a["severity"], "")
                    slack_ts = _post_slack(
                        slack_token,
                        SLACK_CHANNEL,
                        f"{emoji} *[{a['severity'].upper()}]* `{a['alert_type']}` — {a['message']}",
                    )

            await conn.execute(
                "INSERT INTO alert_log (alert_type, severity, category, sensor_id, zone, message, details, source, slack_ts, metric_value, threshold_value) VALUES ($1,$2,$3,$4,$5,$6,$7,'system',$8,$9,$10)",
                a["alert_type"],
                a["severity"],
                a["category"],
                a["sensor_id"],
                a["zone"],
                a["message"],
                json.dumps(a["details"]) if a.get("details") else None,
                slack_ts,
                a.get("metric_value"),
                a.get("threshold_value"),
            )
            new_count += 1

        # Auto-resolve
        resolved = 0
        for key, row in open_keys.items():
            if key not in active_keys:
                await conn.execute(
                    "UPDATE alert_log SET disposition = 'resolved', resolved_at = now(), resolved_by = 'system', resolution = 'auto-resolved' WHERE id = $1",
                    row["id"],
                )
                if row["slack_ts"]:
                    if slack_token is None:
                        try:
                            slack_token = _load_token(SLACK_TOKEN_FILE)
                        except Exception:
                            slack_token = ""
                    if slack_token:
                        _post_slack(
                            slack_token,
                            SLACK_CHANNEL,
                            f"\u2705 Resolved: `{row['alert_type']}` for `{row['sensor_id']}`",
                            thread_ts=row["slack_ts"],
                        )
                resolved += 1

        if new_count or resolved:
            log.info("Alerts: %d new, %d resolved", new_count, resolved)


# Reactive planner REMOVED in Sprint 5 P6 — replaced by forecast deviation monitor (P4)


# ═════════════════════════════════════════════════════════════════
# 8. SETPOINT DISPATCHER (every 300s)
# ═════════════════════════════════════════════════════════════════
from entity_map import PARAM_TO_ENTITY, SWITCH_TO_ENTITY

# In-memory cache of last pushed values — prevents re-pushing unchanged setpoints
_last_pushed: dict[str, float] = {}


async def setpoint_dispatcher(pool: asyncpg.Pool) -> None:
    global _last_pushed
    # Parameters driven by the target band curve, not the AI planner
    BAND_DRIVEN = {
        "temp_high",
        "temp_low",
        "vpd_high",
        "vpd_low",
        "vpd_target_south",
        "vpd_target_west",
        "vpd_target_east",
        "vpd_target_center",
        "mister_engage_delay_s",
        "mister_all_delay_s",
        "mister_center_penalty",
    }
    async with pool.acquire() as conn:
        # Compute crop-science band (outer envelope) + per-zone VPD targets
        band_row = await conn.fetchrow("SELECT * FROM fn_band_setpoints(now())")
        zone_row = await conn.fetchrow("SELECT * FROM fn_zone_vpd_targets(now())")

        planned = await conn.fetch("SELECT parameter, value, ts, plan_id, reason FROM v_active_plan")
        planner_params = {r["parameter"]: r["value"] for r in (planned or [])}

        changes = []

        # Band-driven params: planner can tighten within band, clamped to edges
        if band_row:
            for param in ("temp_low", "temp_high", "vpd_low", "vpd_high"):
                band_lo = float(band_row["temp_low" if param.startswith("temp") else "vpd_low"])
                band_hi = float(band_row["temp_high" if param.startswith("temp") else "vpd_high"])
                planner_val = planner_params.get(param)
                if planner_val is not None:
                    val = max(band_lo, min(band_hi, float(planner_val)))
                else:
                    val = float(band_row[param])
                val = round(val, 1)
                last = _last_pushed.get(param)
                if last is not None and abs(last - val) < 0.1:
                    continue
                changes.append((param, val))

        # Per-zone VPD targets (from crop data per zone)
        if zone_row:
            for param in ("vpd_target_south", "vpd_target_west", "vpd_target_east", "vpd_target_center"):
                val = round(float(zone_row[param]), 2)
                last = _last_pushed.get(param)
                if last is not None and abs(last - val) < 0.02:
                    continue
                changes.append((param, val))

        # Mister tuning defaults: band-derived fallbacks, planner can override
        # engage/all_kpa default to band ceiling; planner may set different values
        if band_row:
            vpd_hi = float(band_row["vpd_high"])
            mister_defaults = {
                "mister_engage_kpa": round(vpd_hi, 2),
                "mister_all_kpa": round(vpd_hi + 0.3, 2),
            }
            # Only set defaults if planner hasn't specified a value
            for param, val in mister_defaults.items():
                if param in planner_params:
                    continue  # Planner owns this — don't override
                last = _last_pushed.get(param)
                if last is not None and abs(last - val) < 0.01:
                    continue
                changes.append((param, val))

        # Process planner setpoints (tactical knobs — skip band params already handled)
        for row in planned or []:
            param, planned_val = row["parameter"], row["value"]
            if param.startswith("plan_") or param in BAND_DRIVEN:
                continue

            last = _last_pushed.get(param)
            if param.startswith("sw_"):
                planned_bool = planned_val > 0.5
                if last is not None and ((last > 0.5) == planned_bool):
                    continue
                changes.append((param, 1.0 if planned_bool else 0.0))
            else:
                if last is not None and abs(last - planned_val) < 0.05:
                    continue
                changes.append((param, planned_val))

        if not changes:
            (STATE_DIR / "setpoint-dispatcher.log").touch()
            return

        for param, val in changes:
            source = "band" if param in BAND_DRIVEN else "plan"
            await conn.execute(
                "INSERT INTO setpoint_changes (ts, parameter, value, source) VALUES (now(), $1, $2, $3)",
                param,
                val,
                source,
            )
            _last_pushed[param] = val
        log.info(
            "Dispatcher: pushed %d setpoint changes (%d band, %d plan)",
            len(changes),
            sum(1 for p, _ in changes if p in BAND_DRIVEN),
            sum(1 for p, _ in changes if p not in BAND_DRIVEN),
        )

    # Direct ESP32 push via shared ingestor connection (non-blocking optimization)
    try:
        from ingestor import push_to_esp32

        esp32_changes = []
        for param, val in changes:
            if param.startswith("sw_"):
                eid = SWITCH_TO_ENTITY.get(param)
                if eid:
                    esp32_changes.append((eid, val, "switch"))
            else:
                eid = PARAM_TO_ENTITY.get(param)
                if eid:
                    esp32_changes.append((eid, val, "number"))
        if esp32_changes:
            pushed = await push_to_esp32(esp32_changes)
            log.info("Dispatcher: direct-pushed %d/%d to ESP32", pushed, len(esp32_changes))
    except Exception as e:
        log.warning("ESP32 direct push failed: %s", e)

    (STATE_DIR / "setpoint-dispatcher.log").touch()


# ═════════════════════════════════════════════════════════════════
# 9. FORECAST SYNC (every 3600s)
# ═════════════════════════════════════════════════════════════════
_DENVER = ZoneInfo("America/Denver")
_FORECAST_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude=40.1672&longitude=-105.1019"
    "&hourly=temperature_2m,relative_humidity_2m,dew_point_2m,"
    "apparent_temperature,precipitation_probability,precipitation,"
    "rain,snowfall,weather_code,"
    "cloud_cover,cloud_cover_low,cloud_cover_high,"
    "wind_speed_10m,wind_direction_10m,wind_gusts_10m,"
    "shortwave_radiation,direct_radiation,diffuse_radiation,"
    "uv_index,sunshine_duration,"
    "vapour_pressure_deficit,surface_pressure,"
    "et0_fao_evapotranspiration,"
    "soil_temperature_0cm,visibility"
    "&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
    "&forecast_days=16&timezone=America%2FDenver"
)


def _fetch_forecast() -> list[dict] | None:
    req = urllib.request.Request(_FORECAST_URL, headers={"User-Agent": "verdify-ingestor/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        if not times:
            return None
        n = len(times)
        rows = []
        for i in range(n):
            rows.append(
                {
                    "ts": times[i],
                    "temp_f": hourly.get("temperature_2m", [None] * n)[i],
                    "rh_pct": hourly.get("relative_humidity_2m", [None] * n)[i],
                    "dew_point_f": hourly.get("dew_point_2m", [None] * n)[i],
                    "feels_like_f": hourly.get("apparent_temperature", [None] * n)[i],
                    "vpd_kpa": hourly.get("vapour_pressure_deficit", [None] * n)[i],
                    "precip_prob_pct": hourly.get("precipitation_probability", [None] * n)[i],
                    "precip_in": hourly.get("precipitation", [None] * n)[i],
                    "rain_in": hourly.get("rain", [None] * n)[i],
                    "snow_in": hourly.get("snowfall", [None] * n)[i],
                    "weather_code": hourly.get("weather_code", [None] * n)[i],
                    "cloud_cover_pct": hourly.get("cloud_cover", [None] * n)[i],
                    "cloud_cover_low_pct": hourly.get("cloud_cover_low", [None] * n)[i],
                    "cloud_cover_high_pct": hourly.get("cloud_cover_high", [None] * n)[i],
                    "wind_speed_mph": hourly.get("wind_speed_10m", [None] * n)[i],
                    "wind_dir_deg": hourly.get("wind_direction_10m", [None] * n)[i],
                    "wind_gust_mph": hourly.get("wind_gusts_10m", [None] * n)[i],
                    "solar_w_m2": hourly.get("shortwave_radiation", [None] * n)[i],
                    "direct_radiation_w_m2": hourly.get("direct_radiation", [None] * n)[i],
                    "diffuse_radiation_w_m2": hourly.get("diffuse_radiation", [None] * n)[i],
                    "uv_index": hourly.get("uv_index", [None] * n)[i],
                    "sunshine_duration_s": hourly.get("sunshine_duration", [None] * n)[i],
                    "surface_pressure_hpa": hourly.get("surface_pressure", [None] * n)[i],
                    "et0_mm": hourly.get("et0_fao_evapotranspiration", [None] * n)[i],
                    "soil_temp_f": hourly.get("soil_temperature_0cm", [None] * n)[i],
                    "visibility_m": hourly.get("visibility", [None] * n)[i],
                }
            )
        return rows
    except Exception as e:
        log.warning("Forecast fetch failed: %s", e)
        return None


async def forecast_sync(pool: asyncpg.Pool) -> None:
    loop = asyncio.get_event_loop()
    rows = await loop.run_in_executor(None, _fetch_forecast)
    if not rows:
        return
    now = datetime.now(UTC)
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM weather_forecast WHERE fetched_at < now() - interval '30 days'")
        for row in rows:
            ts = datetime.fromisoformat(row["ts"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=_DENVER).astimezone(UTC)
            await conn.execute(
                """
                INSERT INTO weather_forecast (ts, fetched_at, temp_f, rh_pct, wind_speed_mph, wind_dir_deg,
                    cloud_cover_pct, precip_prob_pct, solar_w_m2, dew_point_f, feels_like_f, vpd_kpa,
                    precip_in, rain_in, snow_in, wind_gust_mph, uv_index, et0_mm,
                    direct_radiation_w_m2, diffuse_radiation_w_m2, sunshine_duration_s, weather_code,
                    cloud_cover_low_pct, cloud_cover_high_pct, surface_pressure_hpa, soil_temp_f, visibility_m)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27)
            """,
                ts,
                now,
                row.get("temp_f"),
                row.get("rh_pct"),
                row.get("wind_speed_mph"),
                row.get("wind_dir_deg"),
                row.get("cloud_cover_pct"),
                row.get("precip_prob_pct"),
                row.get("solar_w_m2"),
                row.get("dew_point_f"),
                row.get("feels_like_f"),
                row.get("vpd_kpa"),
                row.get("precip_in"),
                row.get("rain_in"),
                row.get("snow_in"),
                row.get("wind_gust_mph"),
                row.get("uv_index"),
                row.get("et0_mm"),
                row.get("direct_radiation_w_m2"),
                row.get("diffuse_radiation_w_m2"),
                row.get("sunshine_duration_s"),
                row.get("weather_code"),
                row.get("cloud_cover_low_pct"),
                row.get("cloud_cover_high_pct"),
                row.get("surface_pressure_hpa"),
                row.get("soil_temp_f"),
                row.get("visibility_m"),
            )
    log.info("Forecast: %d rows inserted", len(rows))


# ═════════════════════════════════════════════════════════════════
# 10. GROW LIGHT DAILY (every 86400s — runs at ~00:10 UTC)
# ═════════════════════════════════════════════════════════════════
_GL_SQL = """
WITH light_events AS (
    SELECT ts, equipment, state,
        LEAD(ts) OVER (PARTITION BY equipment ORDER BY ts) AS next_ts,
        LEAD(state) OVER (PARTITION BY equipment ORDER BY ts) AS next_state
    FROM equipment_state
    WHERE equipment IN ('grow_light_main', 'grow_light_grow')
      AND date_trunc('day', ts)::date = $1
)
SELECT
    COALESCE(SUM(CASE WHEN state = true AND next_state = false AND next_ts IS NOT NULL
        THEN EXTRACT(EPOCH FROM (next_ts - ts)) / 60.0 ELSE 0 END), 0) AS runtime_min,
    COALESCE(SUM(CASE WHEN state = true THEN 1 ELSE 0 END), 0) AS cycles
FROM light_events;
"""

WATTAGES = {
    "heat1": 1500,
    "fan1": 52,
    "fan2": 52,
    "fog": 800,
    "grow_light_main": 630,
    "grow_light_grow": 816,
    "vent": 10,
}
HEAT2_BTU, THERM_BTU = 75000, 100000


async def grow_light_daily(pool: asyncpg.Pool) -> None:
    """Comprehensive daily_summary backfill — runtimes, cycles, energy, costs for yesterday."""
    async with pool.acquire() as conn:
        yesterday = await conn.fetchval("SELECT CURRENT_DATE - 1")
        rows = await conn.fetch(
            "SELECT equipment, on_minutes, cycles FROM v_equipment_runtime_daily WHERE day = $1", yesterday
        )
        rt = {r["equipment"]: (float(r["on_minutes"] or 0), int(r["cycles"] or 0)) for r in rows}

        # Runtimes
        rf1 = rt.get("fan1", (0, 0))[0]
        rf2 = rt.get("fan2", (0, 0))[0]
        rh1 = rt.get("heat1", (0, 0))[0]
        rh2 = rt.get("heat2", (0, 0))[0]
        rfg = rt.get("fog", (0, 0))[0]
        rv = rt.get("vent", (0, 0))[0]
        rms = rt.get("mister_south", (0, 0))[0] / 60.0
        rmw = rt.get("mister_west", (0, 0))[0] / 60.0
        rmc = rt.get("mister_center", (0, 0))[0] / 60.0
        rdw = rt.get("drip_wall", (0, 0))[0] / 60.0
        rdc = rt.get("drip_center", (0, 0))[0] / 60.0
        rgl = rt.get("grow_light_main", (0, 0))[0] + rt.get("grow_light_grow", (0, 0))[0]

        # Energy
        kwh = sum(rt.get(e, (0, 0))[0] / 60.0 * w / 1000.0 for e, w in WATTAGES.items())
        therms = rh2 / 60.0 * HEAT2_BTU / THERM_BTU
        water_gal = (
            await conn.fetchval("SELECT COALESCE(water_used_gal, 0) FROM daily_summary WHERE date = $1", yesterday) or 0
        )
        ce = round(kwh * 0.111, 2)
        cg = round(therms * 0.83, 2)
        cw = round(float(water_gal) * 0.00484, 2)
        ct = round(ce + cg + cw, 2)

        await conn.execute(
            """
            UPDATE daily_summary SET
                runtime_fan1_min=$2, runtime_fan2_min=$3, runtime_heat1_min=$4, runtime_heat2_min=$5,
                runtime_fog_min=$6, runtime_vent_min=$7,
                runtime_mister_south_h=$8, runtime_mister_west_h=$9, runtime_mister_center_h=$10,
                runtime_drip_wall_h=$11, runtime_drip_center_h=$12, runtime_grow_light_min=$13,
                cycles_fan1=$14, cycles_fan2=$15, cycles_heat1=$16, cycles_heat2=$17,
                cycles_fog=$18, cycles_vent=$19,
                cycles_grow_light=$20,
                kwh_estimated=$21, therms_estimated=$22,
                cost_electric=$23, cost_gas=$24, cost_water=$25, cost_total=$26
            WHERE date = $1
        """,
            yesterday,
            rf1,
            rf2,
            rh1,
            rh2,
            rfg,
            rv,
            rms,
            rmw,
            rmc,
            rdw,
            rdc,
            rgl,
            rt.get("fan1", (0, 0))[1],
            rt.get("fan2", (0, 0))[1],
            rt.get("heat1", (0, 0))[1],
            rt.get("heat2", (0, 0))[1],
            rt.get("fog", (0, 0))[1],
            rt.get("vent", (0, 0))[1],
            rt.get("grow_light_main", (0, 0))[1] + rt.get("grow_light_grow", (0, 0))[1],
            round(kwh, 2),
            round(therms, 3),
            ce,
            cg,
            cw,
            ct,
        )

    log.info("Daily summary (%s): %.1f kWh, %.3f therms, $%.2f", yesterday, kwh, therms, ct)

    # ── utility_cost monthly roll-up (idempotent) ──
    async with pool.acquire() as conn:
        month_start = yesterday.replace(day=1)
        row = await conn.fetchrow(
            """
            SELECT ROUND(SUM(COALESCE(cost_electric,0))::numeric, 2) AS ce,
                   ROUND(SUM(COALESCE(cost_gas,0))::numeric, 2)      AS cg,
                   ROUND(SUM(COALESCE(cost_water,0))::numeric, 2)    AS cw,
                   ROUND(SUM(COALESCE(kwh_estimated,0))::numeric, 2) AS kwh,
                   ROUND(SUM(COALESCE(water_used_gal,0))::numeric, 2) AS gal
            FROM daily_summary
            WHERE date >= $1 AND date < ($1 + INTERVAL '1 month')::date
        """,
            month_start,
        )
        if row:
            await conn.execute(
                """
                INSERT INTO utility_cost (month, category, amount_usd, kwh, notes)
                VALUES ($1, 'electric', $2, $3, 'Auto from daily_summary')
                ON CONFLICT (month, category) DO UPDATE SET
                    amount_usd = EXCLUDED.amount_usd, kwh = EXCLUDED.kwh, updated_at = now()
            """,
                month_start,
                row["ce"],
                row["kwh"],
            )
            await conn.execute(
                """
                INSERT INTO utility_cost (month, category, amount_usd, notes)
                VALUES ($1, 'propane', $2, 'Auto from daily_summary')
                ON CONFLICT (month, category) DO UPDATE SET
                    amount_usd = EXCLUDED.amount_usd, updated_at = now()
            """,
                month_start,
                row["cg"],
            )
            await conn.execute(
                """
                INSERT INTO utility_cost (month, category, amount_usd, gallons, notes)
                VALUES ($1, 'water', $2, $3, 'Auto from daily_summary')
                ON CONFLICT (month, category) DO UPDATE SET
                    amount_usd = EXCLUDED.amount_usd, gallons = EXCLUDED.gallons, updated_at = now()
            """,
                month_start,
                row["cw"],
                row["gal"],
            )
        log.info("utility_cost updated for %s", month_start)


# ═════════════════════════════════════════════════════════════════
# 11. FORECAST ACTION ENGINE (every 900s = 15 min)
# ═════════════════════════════════════════════════════════════════
import subprocess as _sp


async def forecast_action_engine(pool: asyncpg.Pool) -> None:
    """Run forecast-action-engine.py as subprocess."""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: _sp.run(
            ["/srv/greenhouse/.venv/bin/python3", "/srv/verdify/scripts/forecast-action-engine.py"],
            capture_output=True,
            text=True,
            timeout=60,
        ),
    )
    if result.returncode != 0:
        log.error("Forecast engine failed: %s", result.stderr[:200])
    elif "actions taken" in result.stderr:
        # Log the summary line
        for line in result.stderr.strip().split("\n"):
            if "actions taken" in line or "TRIGGERED" in line:
                log.info("Forecast: %s", line.split("] ")[-1] if "] " in line else line)


# ═════════════════════════════════════════════════════════════════
# 12. FORECAST DEVIATION CHECK (every 900s = 15 min)
# ═════════════════════════════════════════════════════════════════
async def forecast_deviation_check(pool: asyncpg.Pool) -> None:
    """Compare current conditions to forecast. Write trigger file if deviation exceeds threshold."""
    trigger_file = STATE_DIR / "replan-needed.json"

    async with pool.acquire() as conn:
        current = await conn.fetchrow("""
            SELECT outdoor_temp_f, outdoor_rh_pct,
                   COALESCE(solar_irradiance_w_m2, 0) as solar_w_m2
            FROM climate WHERE outdoor_temp_f IS NOT NULL ORDER BY ts DESC LIMIT 1
        """)
        if not current:
            return

        forecast = await conn.fetchrow("""
            SELECT temp_f, rh_pct,
                   COALESCE(direct_radiation_w_m2 + diffuse_radiation_w_m2, 0) as solar_w_m2
            FROM weather_forecast
            WHERE ts >= date_trunc('hour', now())
              AND ts < date_trunc('hour', now()) + interval '1 hour'
            ORDER BY fetched_at DESC LIMIT 1
        """)
        if not forecast:
            return

        thresholds = await conn.fetch("SELECT * FROM forecast_deviation_thresholds WHERE enabled")

        param_map = {
            "temp_f": ("outdoor_temp_f", "temp_f"),
            "rh_pct": ("outdoor_rh_pct", "rh_pct"),
            "solar_w_m2": ("solar_w_m2", "solar_w_m2"),
        }

        deviations = []
        for t in thresholds:
            obs_col, fc_col = param_map.get(t["parameter"], (None, None))
            if not obs_col:
                continue
            observed = current[obs_col]
            forecasted = forecast[fc_col]
            if observed is None or forecasted is None:
                continue
            delta = abs(float(observed) - float(forecasted))
            if delta > t["threshold"]:
                deviations.append(
                    {
                        "parameter": t["parameter"],
                        "observed": round(float(observed), 1),
                        "forecasted": round(float(forecasted), 1),
                        "delta": round(delta, 1),
                        "threshold": t["threshold"],
                    }
                )
                await conn.execute(
                    "INSERT INTO forecast_deviation_log (parameter, observed, forecasted, delta, threshold) VALUES ($1,$2,$3,$4,$5)",
                    t["parameter"],
                    float(observed),
                    float(forecasted),
                    delta,
                    t["threshold"],
                )

        if not deviations:
            return

        # Check cooldown
        if trigger_file.exists():
            import time as _t

            age_min = (_t.time() - trigger_file.stat().st_mtime) / 60
            min_cooldown = min(t["cooldown_min"] for t in thresholds)
            if age_min < min_cooldown:
                return

        trigger = {
            "ts": datetime.now(UTC).isoformat(),
            "deviations": deviations,
            "reason": f"Forecast deviation: {', '.join(d['parameter'] for d in deviations)}",
        }
        trigger_file.write_text(json.dumps(trigger, indent=2))
        log.warning("Replan triggered: %s", trigger["reason"])


# ═════════════════════════════════════════════════════════════════
# 13. LIVE DAILY SUMMARY (every 1800s = 30 min)
# ═════════════════════════════════════════════════════════════════
_DS_WATTAGES = {
    "heat1": 1500,
    "fan1": 52,
    "fan2": 52,
    "fog": 800,
    "grow_light_main": 630,
    "grow_light_grow": 816,
    "vent": 10,
}


async def daily_summary_live(pool: asyncpg.Pool) -> None:
    """Update daily_summary for today with live running aggregates."""
    async with pool.acquire() as conn:
        today = await conn.fetchval("SELECT (now() AT TIME ZONE 'America/Denver')::date")

        # Ensure row exists
        await conn.execute("INSERT INTO daily_summary (date) VALUES ($1) ON CONFLICT (date) DO NOTHING", today)

        # Climate aggregates
        climate = await conn.fetchrow(
            """
            SELECT MIN(temp_avg) AS temp_min, MAX(temp_avg) AS temp_max, AVG(temp_avg) AS temp_avg,
                   MIN(vpd_avg) AS vpd_min, MAX(vpd_avg) AS vpd_max, AVG(vpd_avg) AS vpd_avg,
                   MIN(rh_avg) AS rh_min, MAX(rh_avg) AS rh_max, AVG(rh_avg) AS rh_avg,
                   AVG(co2_ppm) AS co2_avg, MAX(dli_today) AS dli_final,
                   MAX(mister_water_today) AS mister_water_gal
            FROM climate
            WHERE ts >= $1::date AT TIME ZONE 'America/Denver'
              AND ts < ($1::date + 1) AT TIME ZONE 'America/Denver'
              AND temp_avg IS NOT NULL
        """,
            today,
        )

        # Stress hours — computed with time-appropriate setpoints
        # Load today's setpoint timeline for band parameters
        band_changes = await conn.fetch(
            """
            SELECT parameter, value, ts
            FROM setpoint_changes
            WHERE parameter IN ('temp_high','temp_low','vpd_high','vpd_low')
              AND ts <= ($1::date + 1) AT TIME ZONE 'America/Denver'
              AND CASE
                  WHEN parameter IN ('temp_high','temp_low') THEN value BETWEEN 30 AND 120
                  WHEN parameter IN ('vpd_high','vpd_low') THEN value BETWEEN 0.1 AND 5.0
              END
            ORDER BY parameter, ts
            """,
            today,
        )
        # Build per-parameter sorted timeline
        from bisect import bisect_right

        _timelines: dict[str, list[tuple]] = {}
        for r in band_changes:
            _timelines.setdefault(r["parameter"], []).append((r["ts"], float(r["value"])))

        def _band_at(param: str, ts):
            tl = _timelines.get(param, [])
            if not tl:
                return None
            idx = bisect_right(tl, (ts,)) - 1
            return tl[idx][1] if idx >= 0 else tl[0][1]

        # Load today's climate readings
        readings = await conn.fetch(
            """
            SELECT ts, temp_avg, vpd_avg FROM climate
            WHERE ts >= $1::date AT TIME ZONE 'America/Denver'
              AND ts < ($1::date + 1) AT TIME ZONE 'America/Denver'
              AND temp_avg IS NOT NULL
            ORDER BY ts
            """,
            today,
        )

        # Compute stress with time-appropriate bands
        heat_s = cold_s = vpd_hi_s = vpd_lo_s = 0
        temp_in_band = vpd_in_band = both_in_band = 0
        interval_h = 1.0 / 60.0  # ~1 minute per reading
        for r in readings:
            th = _band_at("temp_high", r["ts"])
            tl = _band_at("temp_low", r["ts"])
            vh = _band_at("vpd_high", r["ts"])
            vl = _band_at("vpd_low", r["ts"])
            if th is None or tl is None or vh is None or vl is None:
                continue
            temp = float(r["temp_avg"])
            vpd = float(r["vpd_avg"])
            if temp > th:
                heat_s += interval_h
            elif temp < tl:
                cold_s += interval_h
            if vpd > vh:
                vpd_hi_s += interval_h
            elif vpd < vl:
                vpd_lo_s += interval_h
            t_ok = tl <= temp <= th
            v_ok = vl <= vpd <= vh
            if t_ok:
                temp_in_band += 1
            if v_ok:
                vpd_in_band += 1
            if t_ok and v_ok:
                both_in_band += 1

        n = len(readings) or 1
        compliance_pct = round((both_in_band / n) * 100, 1)
        temp_compliance_pct = round((temp_in_band / n) * 100, 1)
        vpd_compliance_pct = round((vpd_in_band / n) * 100, 1)
        stress = {
            "heat": round(heat_s, 2),
            "vpd_high": round(vpd_hi_s, 2),
            "cold": round(cold_s, 2),
            "vpd_low": round(vpd_lo_s, 2),
        }

        # Dew point margin (condensation risk)
        dp = await conn.fetchrow(
            """
            SELECT min_margin_f, COALESCE(risk_hours, 0) AS risk_hours
            FROM v_dew_point_risk WHERE date = $1
        """,
            today,
        )

        # Equipment runtimes calculated directly from equipment_state transitions
        _RT_EQUIP = (
            "fan1",
            "fan2",
            "fog",
            "heat1",
            "heat2",
            "vent",
            "grow_light_main",
            "grow_light_grow",
            "mister_south",
            "mister_west",
            "mister_center",
            "drip_wall",
            "drip_center",
        )
        rt_rows = await conn.fetch(
            """
            WITH day_bounds AS (
                SELECT $1::date AT TIME ZONE 'America/Denver' AS day_start,
                       ($1::date + 1) AT TIME ZONE 'America/Denver' AS day_end
            ),
            transitions AS (
                SELECT equipment, ts, state,
                       lead(ts) OVER (PARTITION BY equipment ORDER BY ts) AS next_ts
                FROM equipment_state, day_bounds
                WHERE ts >= day_bounds.day_start AND ts < day_bounds.day_end
                  AND equipment = ANY($2::text[])
            )
            SELECT equipment,
                   round(sum(extract(epoch FROM
                       coalesce(next_ts, (SELECT day_end FROM day_bounds)) - ts
                   ) / 60.0) FILTER (WHERE state = true), 1) AS on_minutes
            FROM transitions
            GROUP BY equipment
        """,
            today,
            list(_RT_EQUIP),
        )
        rt = {r["equipment"]: float(r["on_minutes"] or 0) for r in rt_rows}

        # Energy from runtimes
        kwh = sum(rt.get(e, 0) / 60.0 * w / 1000.0 for e, w in _DS_WATTAGES.items())
        therms = rt.get("heat2", 0) / 60.0 * 75000 / 100000

        # Water
        water_gal = (
            await conn.fetchval(
                """
            SELECT COALESCE(MAX(water_total_gal) - MIN(water_total_gal), 0)
            FROM climate WHERE ts >= $1::date AT TIME ZONE 'America/Denver'
              AND ts < ($1::date + 1) AT TIME ZONE 'America/Denver'
              AND water_total_gal > 0
        """,
                today,
            )
            or 0
        )

        # Costs
        ce = round(kwh * 0.111, 2)
        cg = round(therms * 0.83, 2)
        cw = round(float(water_gal) * 0.00484, 2)
        ct = round(ce + cg + cw, 2)

        gl_min = rt.get("grow_light_main", 0) + rt.get("grow_light_grow", 0)

        await conn.execute(
            """
            UPDATE daily_summary SET
                temp_min=$2, temp_max=$3, temp_avg=$4,
                vpd_min=$5, vpd_max=$6, vpd_avg=$7,
                rh_min=$8, rh_max=$9,
                co2_avg=$10, dli_final=$11,
                stress_hours_heat=$12, stress_hours_vpd_high=$13,
                stress_hours_cold=$14, stress_hours_vpd_low=$15,
                runtime_fan1_min=$16, runtime_fan2_min=$17,
                runtime_heat1_min=$18, runtime_heat2_min=$19,
                runtime_fog_min=$20, runtime_vent_min=$21,
                runtime_grow_light_min=$22,
                runtime_mister_south_h=$23, runtime_mister_west_h=$24, runtime_mister_center_h=$25,
                runtime_drip_wall_h=$26, runtime_drip_center_h=$27,
                kwh_estimated=$28, therms_estimated=$29,
                cost_electric=$30, cost_gas=$31, cost_water=$32, cost_total=$33,
                water_used_gal=$34, mister_water_gal=$35,
                min_dp_margin_f=$36, dp_risk_hours=$37,
                compliance_pct=$38,
                temp_compliance_pct=$39,
                vpd_compliance_pct=$40
            WHERE date = $1
        """,
            today,
            climate["temp_min"] if climate else None,
            climate["temp_max"] if climate else None,
            climate["temp_avg"] if climate else None,
            climate["vpd_min"] if climate else None,
            climate["vpd_max"] if climate else None,
            climate["vpd_avg"] if climate else None,
            climate["rh_min"] if climate else None,
            climate["rh_max"] if climate else None,
            climate["co2_avg"] if climate else None,
            climate["dli_final"] if climate else None,
            float(stress["heat"]) if stress else 0,
            float(stress["vpd_high"]) if stress else 0,
            float(stress["cold"]) if stress else 0,
            float(stress["vpd_low"]) if stress else 0,
            rt.get("fan1", 0),
            rt.get("fan2", 0),
            rt.get("heat1", 0),
            rt.get("heat2", 0),
            rt.get("fog", 0),
            rt.get("vent", 0),
            gl_min,
            rt.get("mister_south", 0) / 60.0,
            rt.get("mister_west", 0) / 60.0,
            rt.get("mister_center", 0) / 60.0,
            rt.get("drip_wall", 0) / 60.0,
            rt.get("drip_center", 0) / 60.0,
            round(kwh, 2),
            round(therms, 3),
            ce,
            cg,
            cw,
            ct,
            float(water_gal),
            float(climate["mister_water_gal"]) if climate and climate["mister_water_gal"] else 0,
            float(dp["min_margin_f"]) if dp and dp["min_margin_f"] is not None else None,
            float(dp["risk_hours"]) if dp else 0,
            compliance_pct,
            temp_compliance_pct,
            vpd_compliance_pct,
        )

    log.info(
        "Daily summary live: $%.2f, %.1f°F max, compliance %.1f%%",
        ct,
        float(climate["temp_max"]) if climate and climate["temp_max"] else 0,
        compliance_pct,
    )


# ═════════════════════════════════════════════════════════════════
# 15. PLANNING HEARTBEAT (every 60s) — Iris event-driven planner
# ═════════════════════════════════════════════════════════════════

from datetime import timedelta as _td

from astral import LocationInfo
from astral.sun import sun as _sun
from iris_planner import gather_context, send_to_iris

_LOCATION = LocationInfo("Longmont", "USA", "America/Denver", 40.1672, -105.1019)
_DENVER = ZoneInfo("America/Denver")

# Milestone state — persisted to disk across restarts
_milestones_cache: dict[str, datetime] = {}
_milestones_fired: dict[str, bool] = {}
_milestones_date: str = ""
_last_forecast_fetch: str = ""
_MILESTONE_STATE_FILE = STATE_DIR / "milestones-fired.json"


def _load_milestone_state():
    """Load fired milestones from disk (survives restarts)."""
    global _milestones_fired, _milestones_date
    try:
        if _MILESTONE_STATE_FILE.exists():
            data = json.loads(_MILESTONE_STATE_FILE.read_text())
            if data.get("date") == datetime.now(_DENVER).strftime("%Y-%m-%d"):
                _milestones_fired = data.get("fired", {})
                _milestones_date = data["date"]
                log.info("Loaded milestone state: %d fired today", len(_milestones_fired))
    except Exception as e:
        log.warning("Could not load milestone state: %s", e)


def _save_milestone_state():
    """Save fired milestones to disk."""
    try:
        data = {"date": _milestones_date, "fired": _milestones_fired}
        _MILESTONE_STATE_FILE.write_text(json.dumps(data))
    except Exception as e:
        log.warning("Could not save milestone state: %s", e)


def _compute_milestones() -> dict[str, datetime]:
    """Compute today's planning milestones from solar ephemeris. Cached per day."""
    global _milestones_cache, _milestones_fired, _milestones_date

    today_str = datetime.now(_DENVER).strftime("%Y-%m-%d")
    if _milestones_date == today_str:
        return _milestones_cache

    # New day — reset state
    _milestones_date = today_str
    _milestones_fired = {}

    today = datetime.now(_DENVER).date()
    s = _sun(_LOCATION.observer, date=today, tzinfo=_DENVER)
    noon = s["noon"]

    _milestones_cache = {
        "SUNRISE": s["sunrise"],
        "TRANSITION:peak_stress": noon + _td(hours=2),
        "TRANSITION:tree_shade": noon + _td(hours=4),
        "TRANSITION:decline": s["sunset"] - _td(hours=1),
        "SUNSET": s["sunset"],
    }

    # Load any previously fired milestones from disk (in case of restart)
    _load_milestone_state()

    return _milestones_cache


async def planning_heartbeat(pool: asyncpg.Pool) -> None:
    """Check if a planning event should fire. Triggers Iris planner session."""
    now = datetime.now(_DENVER)

    # ── 1. Compute/cache today's milestones ──
    all_milestones = _compute_milestones()
    if not _milestones_fired:
        log.info("Planning milestones: %s", ", ".join(f"{k}={v.strftime('%H:%M')}" for k, v in all_milestones.items()))

    # ── 2. Check each milestone ──
    for key, milestone_time in all_milestones.items():
        if key in _milestones_fired:
            continue

        # Fire if we're within the window after the milestone
        # Normal: 0-5 min. Catch-up: 5 min - 2 hours (handles ingestor restarts)
        delta = (now - milestone_time).total_seconds()
        is_catchup = 300 <= delta < 7200
        if 0 <= delta < 300 or is_catchup:
            _milestones_fired[key] = True
            _save_milestone_state()

            # Determine event type and label
            catchup_tag = " (catch-up)" if is_catchup else ""
            if key == "SUNRISE":
                event_type, label = "SUNRISE", f"Morning planning cycle{catchup_tag}"
            elif key == "SUNSET":
                event_type, label = "SUNSET", f"Evening planning cycle{catchup_tag}"
            else:
                event_type = "TRANSITION"
                label = key.split(":", 1)[1].replace("_", " ").title() + catchup_tag

            log.info("Planning milestone fired: %s (%s)%s", key, label, " [CATCH-UP]" if is_catchup else "")

            # Gather context and send to Iris (blocking — runs in executor)
            loop = asyncio.get_event_loop()
            context = await loop.run_in_executor(None, gather_context)
            await loop.run_in_executor(None, send_to_iris, event_type, label, context)

    # ── 3. Check for forecast changes ──
    global _last_forecast_fetch
    async with pool.acquire() as conn:
        latest_fetch = await conn.fetchval(
            "SELECT MAX(fetched_at)::text FROM weather_forecast WHERE fetched_at > now() - interval '2 hours'"
        )
        if latest_fetch and latest_fetch != _last_forecast_fetch:
            if _last_forecast_fetch:
                log.info("New forecast detected (fetched_at=%s), notifying Iris", latest_fetch)
                loop = asyncio.get_event_loop()
                context = await loop.run_in_executor(None, gather_context)
                await loop.run_in_executor(None, send_to_iris, "FORECAST", "New forecast data", context)
            _last_forecast_fetch = latest_fetch

    # ── 4. Check for deviations (route to Iris instead of trigger file) ──
    trigger_file = STATE_DIR / "replan-needed.json"
    if trigger_file.exists():
        import time as _t

        age_s = _t.time() - trigger_file.stat().st_mtime
        if age_s < 300:
            try:
                trigger_data = json.loads(trigger_file.read_text())
                deviations_str = json.dumps(trigger_data.get("deviations", []), indent=2)
                reason = trigger_data.get("reason", "Unknown deviation")

                log.info("Deviation trigger found, routing to Iris: %s", reason)
                loop = asyncio.get_event_loop()
                context = await loop.run_in_executor(None, gather_context)
                await loop.run_in_executor(None, send_to_iris, "DEVIATION", deviations_str, context)

                trigger_file.unlink(missing_ok=True)
            except Exception as e:
                log.error("Failed to process deviation trigger: %s", e)

    # ── 5. Verify plan delivery (30 min after SUNRISE/SUNSET) ──
    for key in ("SUNRISE", "SUNSET"):
        if key not in _milestones_fired:
            continue
        milestone_time = all_milestones.get(key)
        if not milestone_time:
            continue
        mins_since = (now - milestone_time).total_seconds() / 60
        verify_key = f"_verified_{key}"
        if 30 <= mins_since < 35 and verify_key not in _milestones_fired:
            _milestones_fired[verify_key] = True
            _save_milestone_state()
            # Check if a plan was written after the milestone
            async with pool.acquire() as conn:
                plan_count = await conn.fetchval(
                    "SELECT count(*) FROM plan_journal WHERE created_at > $1",
                    milestone_time,
                )
            if plan_count == 0:
                log.warning(
                    "PLAN DELIVERY FAILED: No plan_journal entry after %s (fired %s ago)", key, f"{mins_since:.0f}m"
                )
                # Post alert to Slack
                try:
                    token = _load_token(SLACK_TOKEN_FILE)
                    _post_slack(
                        token,
                        SLACK_CHANNEL,
                        f":warning: *Planning alert:* No plan written after {key} event "
                        f"({mins_since:.0f} min ago). Iris may have failed to process the event. "
                        f"<@U0A9KJHFJSU> please check `tmux attach -t agent-iris-planner`.",
                    )
                except Exception:
                    pass
            else:
                log.info("Plan delivery verified: %d plan(s) written after %s", plan_count, key)
