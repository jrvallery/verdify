"""
tasks.py — Periodic background tasks absorbed from standalone cron scripts.

Each function is an async coroutine that takes an asyncpg.Pool and runs one
unit of work. Called by task_loop() in ingestor.py on defined intervals.

Replaces 10 cron jobs with a single in-process task scheduler.
"""

import asyncio
import json
import logging
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from datetime import timedelta as _td
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import asyncpg
import shared
from esp32_push import push_to_esp32
from pydantic import ValidationError

from verdify_schemas import (
    AlertEnvelope,
    ClimateRow,
    EnergySample,
    EquipmentStateEvent,
    HAEntityState,
    OpenMeteoForecastResponse,
    PlanDeliveryLogRow,
    SetpointChange,
    SystemStateRow,
)

log = logging.getLogger("tasks")

# ── Shared config (from config.py / environment) ────────────────
from config import (
    EXPECTED_FIRMWARE_VERSION,
    EXPECTED_FIRMWARE_VERSION_FILE,
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

# Crop-band params are not planner-owned waypoints. The dispatcher derives all
# four from fn_band_setpoints(now()) every cycle and pushes them to firmware.
# A missing setpoint_plan row for vpd_low is therefore not a firmware fallback:
# vpd_low is explicit in the band contract here.
BAND_DRIVEN_PARAMS = frozenset(
    {
        "temp_high",
        "temp_low",
        "vpd_high",
        "vpd_low",
        "vpd_target_south",
        "vpd_target_west",
        "vpd_target_east",
        "vpd_target_center",
    }
)


def _expected_firmware_version() -> str | None:
    """Return the firmware version pin alert_monitor should enforce."""
    if EXPECTED_FIRMWARE_VERSION.strip():
        return EXPECTED_FIRMWARE_VERSION.strip()
    path = Path(EXPECTED_FIRMWARE_VERSION_FILE)
    try:
        if path.exists():
            value = path.read_text().strip()
            return value or None
    except OSError as exc:
        log.warning("Could not read expected firmware version pin %s: %s", path, exc)
    return None


def _ha_state(states: dict[str, dict], eid: str) -> HAEntityState | None:
    """Validate a raw HA /api/states/{eid} payload into an HAEntityState.

    Returns None if the entity isn't in the batch or the payload fails schema
    validation (so callers can short-circuit rather than crashing the sync).
    """
    raw = states.get(eid)
    if not raw:
        return None
    try:
        return HAEntityState.model_validate(raw)
    except ValidationError as e:
        log.warning("HA entity %s failed schema validation: %s", eid, e)
        return None


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
# IN-5 (Sprint 19): 10-minute dwell + reset hysteresis to kill the 68-flap/46h
# storm from the 96 h review. Hysteresis stops flow-noise-driven cycling between
# trigger (0.10 GPM) and clear; once fired, flow must drop below 0.08 GPM to
# clear. Dwell 10 ticks × 60 s = 10 min of sustained "flow with no valve open"
# before the state flips true.
LEAK_TRIGGER_GPM = 0.10
LEAK_CLEAR_GPM = 0.08  # 20% below trigger — reset hysteresis
LEAK_DWELL_TICKS = 10

_leak_counter = 0
_leak_state = False  # in-memory mirror of equipment_state.leak_detected


async def water_flowing_sync(pool: asyncpg.Pool) -> None:
    global _leak_counter, _leak_state
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

        # leak_detected — hysteresis: use tighter clear threshold while latched
        effective_threshold = LEAK_CLEAR_GPM if _leak_state else LEAK_TRIGGER_GPM
        leak_candidate = False
        if flow > effective_threshold:
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
        leak = _leak_counter >= LEAK_DWELL_TICKS

        current_leak = await conn.fetchval(
            "SELECT state FROM equipment_state WHERE equipment = 'leak_detected' ORDER BY ts DESC LIMIT 1"
        )
        if current_leak is None or leak != current_leak:
            await conn.execute(
                "INSERT INTO equipment_state (ts, equipment, state) VALUES (NOW(), 'leak_detected', $1)", leak
            )
        _leak_state = leak


# ═════════════════════════════════════════════════════════════════
# 2. MATERIALIZED VIEW REFRESH (every 300s)
# ═════════════════════════════════════════════════════════════════
async def matview_refresh(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute("SELECT refresh_relay_stuck(0, '{}'::jsonb)")
        await conn.execute("SELECT refresh_climate_merged(0, '{}'::jsonb)")
        await conn.execute("SELECT refresh_greenhouse_state(0, '{}'::jsonb)")
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
        ha = _ha_state(states, eid)
        if ha is None:
            continue
        v = ha.as_float()
        if v is not None:
            vals[col] = conv(v) if conv else v
    if not vals:
        return

    ts = datetime.now(UTC)
    watts_total = vals.get("ch0_power_w", 0) + vals.get("ch1_power_w", 0)
    kwh_total = vals.get("ch0_energy_kwh") or 0
    try:
        sample = EnergySample(
            ts=ts,
            watts_total=watts_total,
            watts_heat=vals.get("ch1_power_w", 0),
            watts_fans=0,
            watts_other=vals.get("ch0_power_w", 0),
            kwh_today=kwh_total,
        )
    except ValidationError as e:
        log.error("Shelly sample failed schema validation: %s", e)
        return
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO energy (ts, watts_total, watts_heat, watts_fans, watts_other, kwh_today) VALUES ($1,$2,$3,$4,$5,$6)",
            sample.ts,
            sample.watts_total,
            sample.watts_heat,
            sample.watts_fans,
            sample.watts_other,
            sample.kwh_today,
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
        ha = _ha_state(states, eid)
        if ha is None:
            continue
        val = ha.as_float()
        if val is not None:
            outdoor_cols[col] = conv(val) if conv else val
    if not outdoor_cols:
        return

    # Validate ranges on the outdoor columns before any DB write. ClimateRow
    # tolerates missing/extra columns (extra="ignore") and just enforces the
    # ge/le bounds on what it knows.
    try:
        ClimateRow.model_validate({"ts": now, **outdoor_cols})
    except ValidationError as e:
        log.error("Tempest outdoor_cols failed schema validation: %s", e)
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
    # Read from HA template sensors that apply empirical scaling corrections
    # for the YINMIK meter's non-standard Tuya DP encoding (pH × 400, TDS × ½,
    # EC × 0.565). Corrections are defined in HA's
    # /config/packages/greenhouse/hydroponic_calibration.yaml — see the
    # haos agent if values drift or scaling needs adjustment. Temp + ORP +
    # battery DPs are unaffected and still read raw.
    "sensor.greenhouse_hydroponic_ec_corrected": ("hydro_ec_us_cm", None),
    "sensor.greenhouse_hydroponic_orp": ("hydro_orp_mv", None),
    "sensor.greenhouse_hydroponic_ph_corrected": ("hydro_ph", None),
    "sensor.greenhouse_hydroponic_tds_corrected": ("hydro_tds_ppm", None),
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
            ha = _ha_state(states, eid)
            if ha is None:
                continue
            val = ha.as_float()
            if val is not None:
                hydro_cols[col] = conv(val) if conv else val
        if hydro_cols:
            try:
                ClimateRow.model_validate({"ts": now, **hydro_cols})
            except ValidationError as e:
                log.error("Hydro cols failed schema validation: %s", e)
                hydro_cols = {}
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
            ha = _ha_state(states, eid)
            if ha is None:
                continue
            is_on = ha.state == "on"
            if new_state.get(eid) != is_on:
                try:
                    EquipmentStateEvent(ts=now, equipment=equip, state=is_on)
                except ValidationError as e:
                    log.error("Light event skipped (validation failed: %s)", e)
                    continue
                await conn.execute(
                    "INSERT INTO equipment_state (ts, equipment, state) VALUES ($1, $2, $3)", now, equip, is_on
                )
                log.info("Light: %s → %s", equip, "ON" if is_on else "OFF")
            new_state[eid] = is_on

        # Config switches → equipment_state (on-change)
        for eid, equip in _HA_SWITCHES.items():
            ha = _ha_state(states, eid)
            if ha is None:
                continue
            is_on = ha.state == "on"
            key = f"switch_{equip}"
            if new_state.get(key) != is_on:
                try:
                    EquipmentStateEvent(ts=now, equipment=equip, state=is_on)
                except ValidationError as e:
                    log.error("Switch event skipped (validation failed: %s)", e)
                    continue
                await conn.execute(
                    "INSERT INTO equipment_state (ts, equipment, state) VALUES ($1, $2, $3)", now, equip, is_on
                )
            new_state[key] = is_on

        # Occupancy → system_state (on-change)
        for eid, entity in _OCCUPANCY_ENTITIES.items():
            ha = _ha_state(states, eid)
            if ha is None or not ha.is_available:
                continue
            val = "occupied" if ha.state == "on" else "empty"
            key = f"occupancy_{entity}"
            if new_state.get(key) != val:
                try:
                    SystemStateRow(ts=now, entity=entity, value=val)
                except ValidationError as e:
                    log.error("Occupancy transition skipped (validation failed: %s)", e)
                    continue
                await conn.execute("INSERT INTO system_state (ts, entity, value) VALUES ($1, $2, $3)", now, entity, val)
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
        # Daily cumulative stress belongs in the scorecard; an open alert
        # should represent a condition that is still active. Gate the daily
        # >2h threshold by the last 15 minutes so recovered VPD auto-resolves.
        row = await conn.fetchrow(
            """
            WITH daily AS (
                SELECT vpd_stress_hours::float AS vpd_stress_hours
                  FROM v_stress_hours_today
                 WHERE date >= date_trunc('day', now() AT TIME ZONE 'America/Denver')
                 ORDER BY date DESC
                 LIMIT 1
            ),
            recent AS (
                SELECT count(*)::int AS samples,
                       count(*) FILTER (WHERE vpd_avg > fn_setpoint_at('vpd_high', ts))::int AS high_samples,
                       avg(vpd_avg)::float AS avg_vpd,
                       avg(fn_setpoint_at('vpd_high', ts))::float AS avg_vpd_high
                  FROM climate
                 WHERE ts >= now() - interval '15 minutes'
                   AND vpd_avg IS NOT NULL
            )
            SELECT daily.vpd_stress_hours,
                   recent.samples,
                   recent.high_samples,
                   recent.avg_vpd,
                   recent.avg_vpd_high,
                   CASE WHEN recent.samples > 0
                        THEN recent.high_samples::float / recent.samples
                        ELSE 0.0
                   END AS recent_high_fraction
              FROM daily CROSS JOIN recent
            """
        )
        if (
            row
            and row["vpd_stress_hours"]
            and float(row["vpd_stress_hours"]) > 2.0
            and int(row["samples"] or 0) >= 3
            and float(row["recent_high_fraction"] or 0.0) >= 0.5
        ):
            hrs = float(row["vpd_stress_hours"])
            high_fraction = float(row["recent_high_fraction"] or 0.0)
            alerts.append(
                {
                    "alert_type": "vpd_stress",
                    "severity": "warning",
                    "category": "climate",
                    "sensor_id": "climate.vpd_avg",
                    "zone": None,
                    "message": f"VPD stress active: {hrs:.1f} hours today, {high_fraction:.0%} high in last 15m",
                    "details": {
                        "vpd_stress_hours": hrs,
                        "recent_samples": int(row["samples"] or 0),
                        "recent_high_samples": int(row["high_samples"] or 0),
                        "recent_high_fraction": high_fraction,
                        "avg_vpd_15m": float(row["avg_vpd"]) if row["avg_vpd"] is not None else None,
                        "avg_vpd_high_15m": float(row["avg_vpd_high"]) if row["avg_vpd_high"] is not None else None,
                    },
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
        # Sprint 19 followup: suppress the alert when uptime_s < 600 s because
        # an OTA is the expected reboot path and the alert auto-resolves anyway.
        # Only fires for unexpected reboots where the ESP32 is still rebooting
        # frequently (uptime < 300 s, which means a crash-loop scenario).
        row = await conn.fetchrow(
            "SELECT uptime_s, reset_reason FROM diagnostics WHERE ts >= now() - interval '10 minutes' AND uptime_s IS NOT NULL ORDER BY ts DESC LIMIT 1"
        )
        if row and row["uptime_s"] < 300:
            # Check if this is likely an OTA-induced reboot (reset_reason or recent deploy)
            reason = (row["reset_reason"] or "").lower()
            if "ota" in reason or "software" in reason:
                pass  # expected post-OTA reboot — no alert
            else:
                alerts.append(
                    {
                        "alert_type": "esp32_reboot",
                        "severity": "info",
                        "category": "system",
                        "sensor_id": "diag.uptime_s",
                        "zone": None,
                        "message": f"ESP32 rebooted — uptime {row['uptime_s']:.0f}s (reset_reason={reason or 'unknown'})",
                        "details": {"uptime_s": row["uptime_s"], "reset_reason": reason},
                        "metric_value": None,
                        "threshold_value": None,
                    }
                )

        # 7. Planner stale. Threshold 14h = SUNSET→SUNRISE gap (~12.7h) + 1.3h slack.
        # Iris emits full plans at SUNRISE and SUNSET only; interim TRANSITION /
        # FORECAST / DEVIATION events adjust tunables or trigger replans. An 8h
        # threshold (pre-sprint-2) guaranteed a daily false-positive mid-afternoon;
        # 14h fires only when a SUNRISE has genuinely missed. F14's severity
        # ladder (≥12h critical, else warning) is kept for AlertEnvelope dedup
        # structure but degenerates to always-critical at this threshold. This
        # rule will be superseded by contract v1.4's per-(type,instance) SLAs
        # in ingestor sprint-25; treat as an interim fix.
        plan_age = await conn.fetchval("SELECT EXTRACT(EPOCH FROM now() - MAX(created_at))::int FROM setpoint_plan")
        if plan_age and plan_age > 50400:
            age_h = plan_age / 3600.0
            severity = "critical" if age_h >= 12 else "warning"
            alerts.append(
                {
                    "alert_type": "planner_stale",
                    "severity": severity,
                    "category": "system",
                    "sensor_id": "system.planner",
                    "zone": None,
                    "message": f"No plan in {plan_age // 3600}h",
                    "details": {"age_s": plan_age, "age_h": round(age_h, 1)},
                    "metric_value": round(age_h, 1),
                    "threshold_value": 14.0,
                }
            )

        # 7a. Planner gateway delivery failures. A failed OpenClaw POST is a
        # first-class outage, not a pending planner action. Keep the lookback
        # short so transient restarts auto-resolve once deliveries recover.
        gateway_failures = await conn.fetch(
            """
            WITH last_success AS (
                SELECT max(delivered_at) AS ts
                  FROM plan_delivery_log
                 WHERE delivered_at > now() - interval '2 hours'
                   AND gateway_status BETWEEN 200 AND 299
            )
            SELECT id, event_type, event_label, instance, gateway_status, delivered_at, gateway_body
              FROM plan_delivery_log, last_success
             WHERE delivered_at > now() - interval '2 hours'
               AND (last_success.ts IS NULL OR delivered_at > last_success.ts)
               AND (
                    status = 'delivery_failed'
                    OR gateway_status = 0
                    OR gateway_status >= 400
               )
             ORDER BY delivered_at DESC
             LIMIT 10
            """
        )
        if gateway_failures:
            failures = [
                {
                    "id": int(r["id"]),
                    "event_type": r["event_type"],
                    "event_label": r["event_label"],
                    "instance": r["instance"],
                    "gateway_status": int(r["gateway_status"]) if r["gateway_status"] is not None else None,
                    "delivered_at": r["delivered_at"].isoformat(),
                    "gateway_body": (r["gateway_body"] or "")[:300],
                }
                for r in gateway_failures
            ]
            required_failed = any(f["event_type"] in ("SUNRISE", "SUNSET", "MIDNIGHT") for f in failures)
            host_down = any(f["gateway_status"] == 0 for f in failures)
            severity = "critical" if required_failed or host_down or len(failures) >= 3 else "warning"
            first = failures[0]
            alerts.append(
                {
                    "alert_type": "planner_gateway_delivery_failed",
                    "severity": severity,
                    "category": "system",
                    "sensor_id": "system.openclaw",
                    "zone": None,
                    "message": (
                        f"{len(failures)} planner gateway delivery failure(s) in 2h; "
                        f"latest {first['event_type']}/{first['event_label']} "
                        f"status={first['gateway_status']}"
                    ),
                    "details": {"failures": failures},
                    "metric_value": float(len(failures)),
                    "threshold_value": 0.0,
                }
            )

        # 7b. Required SUNRISE/SUNSET plans. These triggers must produce a
        # plan_journal row within their SLA; otherwise the prior plan governs
        # across a new diurnal period with no explicit planner review.
        required_misses = await conn.fetch(
            """
            WITH latest_required AS (
                SELECT id, event_type, event_label, instance, status, gateway_status, delivered_at, gateway_body,
                       row_number() OVER (PARTITION BY event_type ORDER BY delivered_at DESC) AS rn
                  FROM plan_delivery_log
                 WHERE event_type IN ('SUNRISE', 'SUNSET')
                   AND delivered_at > now() - interval '18 hours'
            )
            SELECT id, event_type, event_label, instance, status, gateway_status, delivered_at, gateway_body
              FROM latest_required
             WHERE rn = 1
               AND delivered_at < now() - interval '15 minutes'
               AND status <> 'plan_written'
             ORDER BY delivered_at DESC
            """
        )
        if required_misses:
            misses = [
                {
                    "id": int(r["id"]),
                    "event_type": r["event_type"],
                    "event_label": r["event_label"],
                    "instance": r["instance"],
                    "status": r["status"],
                    "gateway_status": int(r["gateway_status"]) if r["gateway_status"] is not None else None,
                    "delivered_at": r["delivered_at"].isoformat(),
                    "gateway_body": (r["gateway_body"] or "")[:300],
                }
                for r in required_misses
            ]
            latest = misses[0]
            alerts.append(
                {
                    "alert_type": "planner_required_plan_missed",
                    "severity": "critical",
                    "category": "system",
                    "sensor_id": "system.planner_required_plan",
                    "zone": None,
                    "message": (
                        f"{latest['event_type']} did not produce a plan within 15 minutes "
                        f"(status={latest['status']}, gateway={latest['gateway_status']})"
                    ),
                    "details": {"misses": misses},
                    "metric_value": float(len(misses)),
                    "threshold_value": 0.0,
                }
            )

        # 7c. Planner band ownership drift. Crop-band params are dispatcher-
        # owned read-only context; active rows in setpoint_plan can outrank the
        # crop-profile band function and create repeated clamp storms.
        band_owned_rows = await conn.fetch(
            """
            SELECT parameter,
                   coalesce(plan_id, '<null>') AS plan_id,
                   coalesce(source, '<null>') AS source,
                   count(*)::int AS rows
              FROM setpoint_plan
             WHERE is_active = true
               AND parameter IN ('temp_low', 'temp_high', 'vpd_low', 'vpd_high')
             GROUP BY parameter, coalesce(plan_id, '<null>'), coalesce(source, '<null>')
             ORDER BY parameter, plan_id, source
            """
        )
        if band_owned_rows:
            offenders = [
                {
                    "parameter": r["parameter"],
                    "plan_id": r["plan_id"],
                    "source": r["source"],
                    "rows": int(r["rows"]),
                }
                for r in band_owned_rows
            ]
            total_rows = sum(r["rows"] for r in offenders)
            sample = ", ".join(f"{r['parameter']}:{r['plan_id']}({r['rows']})" for r in offenders[:4])
            alerts.append(
                {
                    "alert_type": "planner_band_ownership_drift",
                    "severity": "critical",
                    "category": "system",
                    "sensor_id": "system.planner_band_ownership",
                    "zone": None,
                    "message": (
                        f"{total_rows} active planner row(s) contain dispatcher-owned crop-band params: {sample}"
                    ),
                    "details": {
                        "band_owned_params": ["temp_low", "temp_high", "vpd_low", "vpd_high"],
                        "offenders": offenders,
                    },
                    "metric_value": float(total_rows),
                    "threshold_value": 0.0,
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
                        # "system" per AlertCategory literal; semantic
                        # "safety" subtype is Sprint 25's discriminated union.
                        "category": "system",
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

        # 10. Heating staging inversion (heat2 ON without heat1)
        staging_row = await conn.fetchrow("SELECT * FROM fn_heat_staging_inversion()")
        if staging_row:
            dur = staging_row["duration_s"]
            alerts.append(
                {
                    "alert_type": "heat_staging_inversion",
                    "severity": "warning",
                    "category": "equipment",
                    "sensor_id": "equipment.heat2",
                    "zone": None,
                    "message": (
                        f"STAGING INVERSION: heat2 (gas) ON for {dur:.0f}s while heat1 (electric) OFF. "
                        f"Temp={staging_row['temp_avg']:.1f}°F, "
                        f"Tlow={staging_row['temp_low']:.1f}°F"
                    ),
                    "details": {
                        "heat2_on_since": staging_row["heat2_on_since"].isoformat(),
                        "duration_s": dur,
                        "temp_avg": float(staging_row["temp_avg"]) if staging_row["temp_avg"] else None,
                        "temp_low": float(staging_row["temp_low"]) if staging_row["temp_low"] else None,
                        "d_heat_stage_2": float(staging_row["d_heat_stage_2"])
                        if staging_row["d_heat_stage_2"]
                        else None,
                    },
                    "metric_value": dur,
                    "threshold_value": 60.0,
                }
            )

        # 11. OBS-3 coverage (Sprint 25-omnibus): firmware breaker state.
        # Sprint 18 added relief_cycle_count + vent_latch_timer_s to
        # diagnostics but alert_monitor didn't read them, so the planner had
        # no warning before firmware force-latched VENTILATE. Thresholds
        # chosen against the firmware default max_relief_cycles=3 (range 1–10
        # per greenhouse_types.h:171); if the planner raises the cap, these
        # warn a touch early but don't misfire.
        obs3_row = await conn.fetchrow(
            """
            SELECT relief_cycle_count, vent_latch_timer_s, ts
              FROM diagnostics
             WHERE ts >= now() - interval '5 minutes'
               AND (relief_cycle_count IS NOT NULL OR vent_latch_timer_s IS NOT NULL)
             ORDER BY ts DESC LIMIT 1
            """
        )
        # OBS-3 cooldown (Tier 2b): firmware_relief_ceiling and
        # firmware_vent_latched flap rapidly when the metric oscillates near
        # threshold during stress windows. After a recent auto-resolve, hold
        # off re-firing for 10 min so the alert log + Slack don't accumulate
        # the same incident as 17+ separate rows/day. The auto-resolve loop
        # below still clears genuinely-cleared alerts on the same monitor pass.
        relief_recent_resolve = await conn.fetchval(
            """
            SELECT 1 FROM alert_log
             WHERE alert_type = 'firmware_relief_ceiling'
               AND disposition = 'resolved'
               AND resolved_at > now() - interval '10 minutes'
             LIMIT 1
            """
        )
        latch_recent_resolve = await conn.fetchval(
            """
            SELECT 1 FROM alert_log
             WHERE alert_type = 'firmware_vent_latched'
               AND disposition = 'resolved'
               AND resolved_at > now() - interval '10 minutes'
             LIMIT 1
            """
        )
        if obs3_row:
            relief = obs3_row["relief_cycle_count"]
            if relief is not None and relief >= 2 and not relief_recent_resolve:
                # Warning at ceiling-1 (nearing); critical at ceiling (3) or beyond.
                severity = "critical" if relief >= 3 else "warning"
                alerts.append(
                    {
                        "alert_type": "firmware_relief_ceiling",
                        "severity": severity,
                        "category": "equipment",
                        "sensor_id": "diag.relief_cycle_count",
                        "zone": None,
                        "message": (
                            f"Firmware relief_cycle_count={relief} "
                            f"({'at/past' if relief >= 3 else 'nearing'} default ceiling=3; "
                            f"VENTILATE force-latch {'active' if relief >= 3 else 'imminent'})"
                        ),
                        "details": {"relief_cycle_count": int(relief), "ceiling_default": 3},
                        "metric_value": float(relief),
                        "threshold_value": 3.0,
                    }
                )
            latch = obs3_row["vent_latch_timer_s"]
            if latch is not None and latch >= 600 and not latch_recent_resolve:
                # Warning at 10 min latched; critical at 20 min (schema max 1800s).
                severity = "critical" if latch >= 1200 else "warning"
                alerts.append(
                    {
                        "alert_type": "firmware_vent_latched",
                        "severity": severity,
                        "category": "equipment",
                        "sensor_id": "diag.vent_latch_timer_s",
                        "zone": None,
                        "message": (
                            f"Firmware vent latched for {latch}s "
                            f"({'critical' if latch >= 1200 else 'prolonged'}; "
                            f"planner hasn't resolved the stress that triggered it)"
                        ),
                        "details": {"vent_latch_timer_s": int(latch)},
                        "metric_value": float(latch),
                        "threshold_value": 600.0,
                    }
                )

        # 12. Firmware version mismatch. The deploy path writes
        # STATE_DIR/expected-firmware-version only after sensor-health accepts
        # an OTA. If diagnostics later report a different build, the operator
        # may be validating the wrong binary or an out-of-band OTA happened.
        expected_fw = _expected_firmware_version()
        if expected_fw:
            latest_fw = await conn.fetchrow(
                """
                SELECT firmware_version, ts
                  FROM diagnostics
                 WHERE ts >= now() - interval '10 minutes'
                   AND firmware_version IS NOT NULL
                 ORDER BY ts DESC
                 LIMIT 1
                """
            )
            live_fw = latest_fw["firmware_version"] if latest_fw else None
            if live_fw and live_fw != expected_fw:
                alerts.append(
                    {
                        "alert_type": "firmware_version_mismatch",
                        "severity": "high",
                        "category": "system",
                        "sensor_id": "diag.firmware_version",
                        "zone": None,
                        "message": (f"ESP32 firmware_version={live_fw} does not match expected pin {expected_fw}"),
                        "details": {
                            "expected_firmware_version": expected_fw,
                            "live_firmware_version": live_fw,
                            "diagnostics_ts": latest_fw["ts"].isoformat() if latest_fw else None,
                            "pin_source": EXPECTED_FIRMWARE_VERSION_FILE
                            if not EXPECTED_FIRMWARE_VERSION.strip()
                            else "EXPECTED_FIRMWARE_VERSION",
                        },
                        "metric_value": None,
                        "threshold_value": None,
                    }
                )

        # 13. ESP32 heap pressure watchdogs. Firmware publishes debounced
        # binary sensors; route them into alert_log so heap exhaustion has the
        # same lifecycle and Slack path as the other system-owned alerts.
        heap_rows = await conn.fetch(
            """
            SELECT equipment,
                   (array_agg(state ORDER BY ts DESC, state ASC))[1] AS latest_state,
                   max(ts) AS latest_ts,
                   bool_or(state) FILTER (WHERE ts > now() - interval '30 minutes') AS recent_true,
                   max(ts) FILTER (WHERE state) AS last_true_ts
              FROM equipment_state
             WHERE equipment IN ('heap_pressure_warning', 'heap_pressure_critical')
             GROUP BY equipment
            """
        )
        heap_log = await conn.fetchrow(
            """
            SELECT count(*) FILTER (
                       WHERE message ILIKE '%Heap pressure CRITICAL%'
                   ) AS critical_logs,
                   max(ts) FILTER (
                       WHERE message ILIKE '%Heap pressure CRITICAL%'
                   ) AS last_critical_ts,
                   (array_agg(message ORDER BY ts DESC) FILTER (
                       WHERE message ILIKE '%Heap pressure CRITICAL%'
                   ))[1] AS last_critical_message,
                   count(*) FILTER (
                       WHERE message ILIKE '%Heap pressure WARNING%'
                   ) AS warning_logs,
                   max(ts) FILTER (
                       WHERE message ILIKE '%Heap pressure WARNING%'
                   ) AS last_warning_ts,
                   (array_agg(message ORDER BY ts DESC) FILTER (
                       WHERE message ILIKE '%Heap pressure WARNING%'
                   ))[1] AS last_warning_message
              FROM esp32_logs
             WHERE ts > now() - interval '30 minutes'
               AND message ILIKE '%Heap pressure%'
            """
        )
        heap_diag = await conn.fetchrow(
            """
            SELECT heap_bytes, ts
              FROM diagnostics
             WHERE heap_bytes IS NOT NULL
             ORDER BY ts DESC
             LIMIT 1
            """
        )
        heap_state = {r["equipment"]: r for r in heap_rows}
        heap_critical = heap_state.get("heap_pressure_critical")
        heap_warning = heap_state.get("heap_pressure_warning")
        heap_bytes = float(heap_diag["heap_bytes"]) if heap_diag and heap_diag["heap_bytes"] is not None else None
        critical_logs = int(heap_log["critical_logs"] or 0) if heap_log else 0
        warning_logs = int(heap_log["warning_logs"] or 0) if heap_log else 0
        last_critical_event_ts = max(
            [
                ts
                for ts in (
                    heap_critical["last_true_ts"] if heap_critical else None,
                    heap_log["last_critical_ts"] if heap_log else None,
                )
                if ts is not None
            ],
            default=None,
        )
        last_warning_event_ts = max(
            [
                ts
                for ts in (
                    heap_warning["last_true_ts"] if heap_warning else None,
                    heap_log["last_warning_ts"] if heap_log else None,
                )
                if ts is not None
            ],
            default=None,
        )
        healthy_after_critical = 0
        healthy_after_warning = 0
        if last_critical_event_ts:
            healthy_after_critical = await conn.fetchval(
                """
                SELECT count(*)
                  FROM diagnostics
                 WHERE ts > $1
                   AND heap_bytes >= 35.0
                """,
                last_critical_event_ts,
            )
        if last_warning_event_ts:
            healthy_after_warning = await conn.fetchval(
                """
                SELECT count(*)
                  FROM diagnostics
                 WHERE ts > $1
                   AND heap_bytes >= 35.0
                """,
                last_warning_event_ts,
            )
        critical_active = bool((heap_critical and heap_critical["recent_true"]) or critical_logs > 0)
        warning_active = bool((heap_warning and heap_warning["recent_true"]) or warning_logs > 0)
        if heap_bytes is not None:
            # The binary sensors and diagnostics can arrive at the same second;
            # a recent true event still matters even if a same-second false
            # event or later diagnostic sample recovered. Alert on the
            # transient for 30 min, then let the normal lifecycle resolve it.
            if heap_bytes < 15.0:
                critical_active = True
                warning_active = False
            elif heap_bytes < 30.0 and not critical_active:
                critical_active = False
                warning_active = True
            elif heap_bytes >= 35.0 and heap_diag:
                # Recovery is explicit once firmware publishes a false binary
                # event after the last true/log event and the numeric heap
                # sample is healthy after that false. This preserves real
                # transients while preventing stale log lines from holding a
                # critical alert open after observed recovery.
                if (
                    critical_active
                    and last_critical_event_ts
                    and heap_diag["ts"] > last_critical_event_ts
                    and healthy_after_critical >= 2
                    and not (
                        heap_critical
                        and heap_critical["latest_state"] is True
                        and heap_critical["latest_ts"] >= last_critical_event_ts
                    )
                ):
                    critical_active = False
                if (
                    warning_active
                    and last_warning_event_ts
                    and heap_diag["ts"] > last_warning_event_ts
                    and healthy_after_warning >= 2
                    and not (
                        heap_warning
                        and heap_warning["latest_state"] is True
                        and heap_warning["latest_ts"] >= last_warning_event_ts
                    )
                ):
                    warning_active = False
        if critical_active:
            alerts.append(
                {
                    "alert_type": "heap_pressure_critical",
                    "severity": "critical",
                    "category": "system",
                    "sensor_id": "equipment.heap_pressure_critical",
                    "zone": None,
                    "message": "ESP32 heap pressure critical: free heap dropped below firmware critical threshold",
                    "details": {
                        "equipment": "heap_pressure_critical",
                        "equipment_ts": heap_critical["latest_ts"].isoformat() if heap_critical else None,
                        "last_true_ts": heap_critical["last_true_ts"].isoformat()
                        if heap_critical and heap_critical["last_true_ts"]
                        else None,
                        "heap_free_kb": round(heap_bytes, 1) if heap_bytes is not None else None,
                        "heap_diag_ts": heap_diag["ts"].isoformat() if heap_diag else None,
                        "critical_logs_30m": critical_logs,
                        "healthy_heap_samples_after_event": healthy_after_critical,
                        "last_critical_log_ts": heap_log["last_critical_ts"].isoformat()
                        if heap_log and heap_log["last_critical_ts"]
                        else None,
                        "last_critical_log_message": heap_log["last_critical_message"] if heap_log else None,
                    },
                    "metric_value": heap_bytes,
                    "threshold_value": 15.0,
                }
            )
        elif warning_active:
            alerts.append(
                {
                    "alert_type": "heap_pressure_warning",
                    "severity": "warning",
                    "category": "system",
                    "sensor_id": "equipment.heap_pressure_warning",
                    "zone": None,
                    "message": "ESP32 heap pressure warning: free heap stayed below firmware warning threshold",
                    "details": {
                        "equipment": "heap_pressure_warning",
                        "equipment_ts": heap_warning["latest_ts"].isoformat() if heap_warning else None,
                        "last_true_ts": heap_warning["last_true_ts"].isoformat()
                        if heap_warning and heap_warning["last_true_ts"]
                        else None,
                        "heap_free_kb": round(heap_bytes, 1) if heap_bytes is not None else None,
                        "heap_diag_ts": heap_diag["ts"].isoformat() if heap_diag else None,
                        "warning_logs_30m": warning_logs,
                        "healthy_heap_samples_after_event": healthy_after_warning,
                        "last_warning_log_ts": heap_log["last_warning_ts"].isoformat()
                        if heap_log and heap_log["last_warning_ts"]
                        else None,
                        "last_warning_log_message": heap_log["last_warning_message"] if heap_log else None,
                    },
                    "metric_value": heap_bytes,
                    "threshold_value": 30.0,
                }
            )

        # 14. Tunable zero-variance detection (Sprint 24.9, G-9).
        # Firmware sprint-13 30-day scan flagged vpd_target_west pinned at
        # 1.2 kPa across 33k samples — either fn_zone_vpd_targets has a
        # west-zone default/bug or the west zone has no active crop. Catching
        # this class of issue automatically (any dispatcher-owned tunable with
        # stddev=0 over 7 days) surfaces the condition without waiting for
        # an operator to notice.
        active_crop_zones = {
            str(r["zone"])
            for r in await conn.fetch("SELECT DISTINCT zone FROM crops WHERE is_active = true AND zone IS NOT NULL")
        }
        zone_target_params = {
            "vpd_target_south": "south",
            "vpd_target_west": "west",
            "vpd_target_east": "east",
            "vpd_target_center": "center",
        }
        zero_var_params = [
            "temp_low",
            "temp_high",
            "vpd_low",
            "vpd_high",
            *[param for param, zone in zone_target_params.items() if zone in active_crop_zones],
        ]
        for r in await conn.fetch(
            """
            SELECT parameter, count(*) AS n, stddev(value) AS sd, avg(value) AS mean
              FROM setpoint_snapshot
             WHERE parameter = ANY($1::text[])
               AND ts > now() - interval '7 days'
             GROUP BY parameter
            HAVING count(*) > 100 AND (stddev(value) IS NULL OR stddev(value) = 0)
            """,
            list(zero_var_params),
        ):
            alerts.append(
                {
                    "alert_type": "tunable_zero_variance",
                    "severity": "warning",
                    "category": "system",
                    "sensor_id": f"setpoint.{r['parameter']}",
                    "zone": None,
                    "message": (
                        f"Tunable `{r['parameter']}` has zero variance over 7 days "
                        f"(n={r['n']}, pinned at {float(r['mean']):.3f}). "
                        "Check dispatcher source (band / zone function / crop profile)."
                    ),
                    "details": {
                        "parameter": r["parameter"],
                        "sample_count": int(r["n"]),
                        "pinned_value": float(r["mean"]),
                    },
                    "metric_value": 0.0,
                    "threshold_value": None,
                }
            )

        # Reactive trigger marker removed in Sprint 5 P6 — deviation monitor handles replans

        # ── Deduplicate + insert + resolve ──
        active_keys = {(a["alert_type"], a["sensor_id"]) for a in alerts}
        # Sprint 25-omnibus (setpoint_unconfirmed lifecycle fix): only
        # consider alerts THIS monitor owns (source='system') for auto-resolve.
        # Alerts inserted by other monitors (setpoint_confirmation_monitor
        # writes source='ingestor'; iris_planner writes source='iris_planner';
        # dispatcher writes source='dispatcher') have their own lifecycle
        # — auto-resolving them here caused setpoint_unconfirmed to flap
        # open↔resolved every alert_monitor cycle.
        open_rows = await conn.fetch(
            "SELECT id, alert_type, severity, sensor_id, slack_ts FROM alert_log "
            "WHERE disposition IN ('open', 'acknowledged') AND resolved_at IS NULL AND source = 'system'"
        )
        open_keys = {(r["alert_type"], r["sensor_id"]): r for r in open_rows}

        slack_token = None
        new_count = 0
        escalated_count = 0
        for a in alerts:
            key = (a["alert_type"], a["sensor_id"])
            if key in open_keys:
                existing = open_keys[key]
                try:
                    env = AlertEnvelope.model_validate(a)
                except ValidationError as e:
                    log.error("alert refresh skipped (validation failed: %s): %r", e, a)
                    continue
                is_escalation = env.severity == "critical" and existing["severity"] != "critical"
                await conn.execute(
                    """
                    UPDATE alert_log
                       SET severity=$1,
                           message=$2,
                           details=$3,
                           metric_value=$4,
                           threshold_value=$5
                     WHERE id=$6
                    """,
                    env.severity,
                    env.message,
                    json.dumps(env.details) if env.details else None,
                    env.metric_value,
                    env.threshold_value,
                    existing["id"],
                )
                # F14 (Sprint 24.6): escalate severity in place and re-notify.
                # Same-severity updates intentionally stay quiet but keep DB
                # context fresh for dashboards and deploy preflights.
                if is_escalation:
                    if slack_token is None:
                        try:
                            slack_token = _load_token(SLACK_TOKEN_FILE)
                        except Exception:
                            slack_token = ""
                    if slack_token:
                        _post_slack(
                            slack_token,
                            SLACK_CHANNEL,
                            f"\U0001f534 *[ESCALATED→CRITICAL]* `{env.alert_type}` — {env.message}",
                            thread_ts=existing["slack_ts"],
                        )
                    escalated_count += 1
                continue
            try:
                env = AlertEnvelope.model_validate(a)
            except ValidationError as e:
                log.error("alert skipped (envelope validation failed: %s): %r", e, a)
                continue
            should_slack = env.alert_type not in ("sensor_offline", "esp32_reboot")
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
                    }.get(env.severity, "")
                    slack_ts = _post_slack(
                        slack_token,
                        SLACK_CHANNEL,
                        f"{emoji} *[{env.severity.upper()}]* `{env.alert_type}` — {env.message}",
                    )

            await conn.execute(
                "INSERT INTO alert_log (alert_type, severity, category, sensor_id, zone, message, details, source, slack_ts, metric_value, threshold_value) VALUES ($1,$2,$3,$4,$5,$6,$7,'system',$8,$9,$10)",
                env.alert_type,
                env.severity,
                env.category,
                env.sensor_id,
                env.zone,
                env.message,
                json.dumps(env.details) if env.details else None,
                slack_ts,
                env.metric_value,
                env.threshold_value,
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

        if new_count or resolved or escalated_count:
            log.info("Alerts: %d new, %d resolved, %d escalated", new_count, resolved, escalated_count)


# Reactive planner REMOVED in Sprint 5 P6 — replaced by forecast deviation monitor (P4)


# ═════════════════════════════════════════════════════════════════
# 8. SETPOINT DISPATCHER (every 300s)
# ═════════════════════════════════════════════════════════════════
from entity_map import PARAM_TO_ENTITY, SWITCH_TO_ENTITY

# In-memory cache of last pushed values — prevents re-pushing unchanged setpoints
_last_pushed: dict[str, float] = {}


# FW-3 (Sprint 18): physics sanity invariants. Planner values outside
# these bounds are clamped before dispatch and logged to setpoint_clamps
# with reason='invariant_violation'. Every key must be a canonical
# ALL_TUNABLES entry — see test_physics_invariants_are_canonical.
#
# Format: param → (min, max). None means no bound on that side.
_PHYSICS_INVARIANTS: dict[str, tuple[float | None, float | None]] = {
    # Time-of-day windows (hour of day)
    "fog_time_window_start": (0, 23),
    "fog_time_window_end": (1, 24),
    "gl_sunrise_hour": (0, 23),
    "gl_sunset_hour": (1, 24),
    # Integer counters (seconds)
    "mister_engage_delay_s": (5, 300),
    "mister_all_delay_s": (10, 600),
    "vpd_watch_dwell_s": (10, 600),
    # Resource budgets
    "mister_water_budget_gal": (100, 5000),
    # Temperature bounds (°F)
    "fog_min_temp_f": (32, 90),
    "safety_min": (30, 60),
    "safety_max": (80, 120),
    # Percentages
    "fog_rh_ceiling_pct": (50, 100),
    # VPD (kPa) safety rails
    "safety_vpd_min": (0.1, 1.0),
    "safety_vpd_max": (1.5, 5.0),
    # Hysteresis (kPa)
    "vpd_hysteresis": (0.05, 1.0),
    # Biases (°F)
    "bias_cool": (-5, 5),
    "bias_heat": (-5, 5),
}


def _validate_physics(param: str, val: float) -> tuple[float, str | None]:
    """FW-3 (Sprint 18): clamp val to physical bounds if invariant violated.

    Returns (clamped_val, reason). reason is None when no clamp applied.
    Only clamps for parameters with invariants defined in _PHYSICS_INVARIANTS.
    Unknown params pass through unchanged (the band / dispatcher layers
    handle those).
    """
    bounds = _PHYSICS_INVARIANTS.get(param)
    if bounds is None:
        return val, None
    lo, hi = bounds
    if lo is not None and val < lo:
        return float(lo), f"invariant_violation:below_{lo}"
    if hi is not None and val > hi:
        return float(hi), f"invariant_violation:above_{hi}"
    return val, None


def _should_skip(last: float | None, val: float, rel: float = 0.01, abs_floor: float = 1e-3) -> bool:
    """DI-1 (Sprint 18): proportional dead-band for dispatcher.

    Return True if `val` is within `rel` (default 1%) of the previously-pushed
    value, relative to the magnitude of `val`. An `abs_floor` protects against
    setpoints at or near zero where any absolute threshold would be arbitrary.

    Replaces the previous absolute 0.1/0.05/0.02/0.01 thresholds that were
    scale-inappropriate — 0.05 on a 0.8 kPa VPD setpoint was 6% (too coarse),
    while the same 0.05 on a 75°F temp setpoint was 0.07% (fine). 1% relative
    is the right choice across the whole setpoint range.
    """
    if last is None:
        return False
    return abs(last - val) / max(abs(val), abs_floor) < rel


async def setpoint_dispatcher(pool: asyncpg.Pool) -> None:
    global _last_pushed
    # On ESP32 reconnect, rebuild the cache from firmware cfg_* readbacks.
    # Values already confirmed by the device do not need to be pushed again;
    # params without a readback still flow through as a conservative fallback.
    if shared.force_setpoint_push.is_set():
        shared.force_setpoint_push.clear()
        _last_pushed.clear()
        seeded = 0
        for param, val in shared.cfg_readback.items():
            _last_pushed[param] = float(val)
            seeded += 1
        log.info(
            "Dispatcher: reconnect reconcile — seeded %d cfg readbacks; pushing drift/missing setpoints",
            seeded,
        )
    async with pool.acquire() as conn:
        # Compute crop-science band (outer envelope) + per-zone VPD targets
        band_row = await conn.fetchrow("SELECT * FROM fn_band_setpoints(now())")
        zone_row = await conn.fetchrow("SELECT * FROM fn_zone_vpd_targets(now())")

        planned = await conn.fetch("SELECT parameter, value, ts, plan_id, reason FROM v_active_plan")
        raw_planner_params = {r["parameter"]: r["value"] for r in (planned or [])}

        # FW-3 (Sprint 18): enforce physics invariants BEFORE any downstream
        # use. Clamped values replace the planner's originals; violations
        # get logged alongside band-clamps in setpoint_clamps for audit.
        changes = []
        clamps_to_log: list[tuple[str, float, float, float, float, str]] = []
        planner_params: dict[str, float] = {}
        for param, raw_val in raw_planner_params.items():
            clean_val, violation = _validate_physics(param, float(raw_val))
            if violation is not None:
                clamps_to_log.append((param, float(raw_val), clean_val, 0.0, 0.0, violation))
                log.warning(
                    "FW-3 invariant: %s=%s clamped to %s (%s)",
                    param,
                    raw_val,
                    clean_val,
                    violation,
                )
            planner_params[param] = clean_val

        # Band-driven params: planner can tighten within band, clamped to edges
        if band_row:
            for param in ("temp_low", "temp_high", "vpd_low", "vpd_high"):
                band_lo = float(band_row["temp_low" if param.startswith("temp") else "vpd_low"])
                band_hi = float(band_row["temp_high" if param.startswith("temp") else "vpd_high"])
                planner_val = planner_params.get(param)
                if planner_val is not None:
                    planner_f = float(planner_val)
                    val = max(band_lo, min(band_hi, planner_f))
                    # Tier 1 #2: audit clamp when planner request was modified
                    if abs(val - planner_f) > 1e-6:
                        clamps_to_log.append(
                            (
                                param,
                                planner_f,
                                val,
                                band_lo,
                                band_hi,
                                "band_lo" if planner_f < band_lo else "band_hi",
                            )
                        )
                else:
                    val = float(band_row[param])
                val = round(val, 1)
                if _should_skip(_last_pushed.get(param), val):
                    continue
                changes.append((param, val))

        # Per-zone VPD targets (from crop data per zone)
        if zone_row:
            for param in ("vpd_target_south", "vpd_target_west", "vpd_target_east", "vpd_target_center"):
                val = round(float(zone_row[param]), 2)
                if _should_skip(_last_pushed.get(param), val):
                    continue
                changes.append((param, val))

        # Safety limits: always dispatched, planner can override within range
        safety_defaults = {
            "safety_max": 100.0,
            "safety_min": 40.0,
        }
        for param, val in safety_defaults.items():
            planner_val = planner_params.get(param)
            if planner_val is not None:
                val = float(planner_val)
            if _should_skip(_last_pushed.get(param), val):
                continue
            changes.append((param, val))

        # Mister tuning defaults: band-derived fallbacks, planner can override
        # engage/all_kpa default to band ceiling; planner may set different values
        if band_row:
            vpd_hi = float(band_row["vpd_high"])
            mister_defaults = {
                "mister_engage_kpa": round(vpd_hi, 2),
                "mister_all_kpa": round(vpd_hi + 0.3, 2),
                "mister_engage_delay_s": 30,
                "mister_all_delay_s": 60,
                "mister_center_penalty": 0.5,
            }
            # Only set defaults if planner hasn't specified a value
            for param, val in mister_defaults.items():
                if param in planner_params:
                    continue  # Planner owns this — don't override
                if _should_skip(_last_pushed.get(param), val):
                    continue
                changes.append((param, val))

        # Process planner setpoints (tactical knobs — skip band params already handled)
        for row in planned or []:
            param, planned_val = row["parameter"], row["value"]
            if param.startswith("plan_") or param in BAND_DRIVEN_PARAMS:
                continue

            last = _last_pushed.get(param)
            if param.startswith("sw_"):
                planned_bool = planned_val > 0.5
                if last is not None and ((last > 0.5) == planned_bool):
                    continue
                changes.append((param, 1.0 if planned_bool else 0.0))
            else:
                if _should_skip(last, planned_val):
                    continue
                changes.append((param, planned_val))

        if not changes:
            (STATE_DIR / "setpoint-dispatcher.log").touch()
            return

        SAFETY_PARAMS = {"safety_max", "safety_min"}
        MISTER_DEFAULTS = {
            "mister_engage_kpa",
            "mister_all_kpa",
            "mister_engage_delay_s",
            "mister_all_delay_s",
            "mister_center_penalty",
        }
        for param, val in changes:
            if param in BAND_DRIVEN_PARAMS:
                source = "band"
            elif param in SAFETY_PARAMS and param not in planner_params:
                source = "band"
            elif param in MISTER_DEFAULTS and param not in planner_params:
                source = "band"
            else:
                source = "plan"
            # Sprint 24.9 (G-2): validate through SetpointChange before INSERT.
            # Defense-in-depth: MCP's PlanTransition.params already validates
            # at write time, but a regression there would silently corrupt
            # setpoint_changes. Drift-surface the mismatch here where it's
            # cheap (one row at a time) vs. downstream where it blows up a
            # grafana panel or planner scorecard.
            try:
                SetpointChange(ts=datetime.now(UTC), parameter=param, value=float(val), source=source)
            except ValidationError as e:
                log.error(
                    "dispatcher setpoint_change skipped (validation failed: %s): param=%s value=%s source=%s",
                    e,
                    param,
                    val,
                    source,
                )
                continue
            # Mark before INSERT so the LISTEN/NOTIFY real-time listener
            # suppresses this dispatcher-origin row. The dispatcher performs
            # its own retried batch push below; without this pre-mark, reconnect
            # force-pushes duplicate every command and can drive ESP32 heap
            # into critical-pressure transients.
            shared.recently_pushed[param] = time.time()
            shared.recently_pushed_values[param] = float(val)
            await conn.execute(
                "INSERT INTO setpoint_changes (ts, parameter, value, source) VALUES (now(), $1, $2, $3)",
                param,
                val,
                source,
            )
            _last_pushed[param] = val
        # Tier 1 #2: persist clamp audit
        for param, requested, applied, b_lo, b_hi, reason in clamps_to_log:
            await conn.execute(
                "INSERT INTO setpoint_clamps (parameter, requested, applied, band_lo, band_hi, reason) "
                "VALUES ($1, $2, $3, $4, $5, $6)",
                param,
                requested,
                applied,
                b_lo,
                b_hi,
                reason,
            )
        if clamps_to_log:
            log.info(
                "Dispatcher: clamped %d planner value(s) to band (%s)",
                len(clamps_to_log),
                ", ".join(f"{p}={req}->{app}" for p, req, app, *_ in clamps_to_log),
            )
        log.info(
            "Dispatcher: pushed %d setpoint changes (%d band, %d plan)",
            len(changes),
            sum(1 for p, _ in changes if p in BAND_DRIVEN_PARAMS),
            sum(1 for p, _ in changes if p not in BAND_DRIVEN_PARAMS),
        )

    # Direct ESP32 push via shared ingestor connection (non-blocking optimization)
    # Tier 1 #4: retry on failure, escalate to alert_log after exhausted attempts.
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
        last_err: Exception | None = None
        for attempt in (1, 2, 3):
            try:
                pushed = await push_to_esp32(esp32_changes)
                log.info(
                    "Dispatcher: direct-pushed %d/%d to ESP32 (attempt %d)",
                    pushed,
                    len(esp32_changes),
                    attempt,
                )
                last_err = None
                break
            except Exception as e:
                last_err = e
                log.warning("ESP32 direct push failed (attempt %d/3): %s", attempt, e)
                if attempt < 3:
                    await asyncio.sleep(0.5 * attempt)
        if last_err is not None:
            async with pool.acquire() as conn:
                existing = await conn.fetchval(
                    "SELECT id FROM alert_log WHERE alert_type = 'esp32_push_failed' AND disposition = 'open' LIMIT 1"
                )
                if existing is None:
                    await conn.execute(
                        "INSERT INTO alert_log (alert_type, severity, category, message, details, source) "
                        "VALUES ('esp32_push_failed', 'warning', 'system', $1, $2, 'dispatcher')",
                        f"ESP32 direct push failed after 3 attempts: {last_err}",
                        json.dumps(
                            {
                                "error": str(last_err),
                                "change_count": len(esp32_changes),
                            }
                        ),
                    )

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
    """Fetch 16-day hourly forecast from Open-Meteo. Validated via
    OpenMeteoForecastResponse — parallel-array length mismatch fails loud
    instead of silently index-truncating like the old hand-zipped loop."""
    req = urllib.request.Request(_FORECAST_URL, headers={"User-Agent": "verdify-ingestor/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.loads(resp.read())
    except Exception as e:
        log.warning("Forecast fetch failed: %s", e)
        return None

    try:
        response = OpenMeteoForecastResponse.model_validate(raw)
    except ValidationError as e:
        log.warning("Open-Meteo response failed schema validation: %s", e)
        return None

    hourly = response.hourly
    times = hourly.time
    if not times:
        return None
    n = len(times)

    def col(name: str) -> list:
        arr = getattr(hourly, name, None)
        return arr if arr is not None else [None] * n

    rows = []
    for i in range(n):
        rows.append(
            {
                "ts": times[i],
                "temp_f": col("temperature_2m")[i],
                "rh_pct": col("relative_humidity_2m")[i],
                "dew_point_f": col("dew_point_2m")[i],
                "feels_like_f": col("apparent_temperature")[i],
                "vpd_kpa": col("vapour_pressure_deficit")[i],
                "precip_prob_pct": col("precipitation_probability")[i],
                "precip_in": col("precipitation")[i],
                "rain_in": col("rain")[i],
                "snow_in": col("snowfall")[i],
                "weather_code": col("weather_code")[i],
                "cloud_cover_pct": col("cloud_cover")[i],
                "cloud_cover_low_pct": col("cloud_cover_low")[i],
                "cloud_cover_high_pct": col("cloud_cover_high")[i],
                "wind_speed_mph": col("wind_speed_10m")[i],
                "wind_dir_deg": col("wind_direction_10m")[i],
                "wind_gust_mph": col("wind_gusts_10m")[i],
                "solar_w_m2": col("shortwave_radiation")[i],
                "direct_radiation_w_m2": col("direct_radiation")[i],
                "diffuse_radiation_w_m2": col("diffuse_radiation")[i],
                "uv_index": col("uv_index")[i],
                "sunshine_duration_s": col("sunshine_duration")[i],
                "surface_pressure_hpa": col("surface_pressure")[i],
                "et0_mm": col("et0_fao_evapotranspiration")[i],
                "soil_temp_f": col("soil_temperature_0cm")[i],
                "visibility_m": col("visibility")[i],
            }
        )
    return rows


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
                cycles_mister_south=$21, cycles_mister_west=$22, cycles_mister_center=$23,
                cycles_drip_wall=$24, cycles_drip_center=$25,
                kwh_estimated=$26, therms_estimated=$27,
                cost_electric=$28, cost_gas=$29, cost_water=$30, cost_total=$31
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
            rt.get("mister_south", (0, 0))[1],
            rt.get("mister_west", (0, 0))[1],
            rt.get("mister_center", (0, 0))[1],
            rt.get("drip_wall", (0, 0))[1],
            rt.get("drip_center", (0, 0))[1],
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
_last_deviation_trigger_ts: float = 0.0


async def forecast_deviation_check(pool: asyncpg.Pool) -> None:
    """Compare outdoor observed conditions to outdoor forecast. Write trigger file if deviation exceeds threshold.

    Guards against false triggers:
    - Only runs during daytime (sunrise to sunset+1h) — nighttime RH divergence is normal
    - Cooldown tracked in-memory (not via trigger file which gets consumed by heartbeat)
    - Only logs to deviation_log when outside cooldown (prevents log pollution)
    """
    global _last_deviation_trigger_ts
    trigger_file = STATE_DIR / "replan-needed.json"

    # Time-of-day gate: only check during daytime + 1h buffer after sunset
    # Nighttime RH/temp deviations are climatologically normal and not actionable
    from astral import LocationInfo
    from astral.sun import sun as _astral_sun

    now = datetime.now(ZoneInfo("America/Denver"))
    loc = LocationInfo("Longmont", "USA", "America/Denver", 40.1672, -105.1019)
    s = _astral_sun(loc.observer, date=now.date(), tzinfo=ZoneInfo("America/Denver"))
    sunrise = s["sunrise"]
    sunset_buffer = s["sunset"] + _td(hours=2)  # Extended to cover evening VPD cycling

    if now < sunrise or now > sunset_buffer:
        return  # Night — skip deviation check entirely

    # In-memory cooldown (survives trigger file consumption by heartbeat)
    import time as _t

    cooldown_s = 3600  # 1 hour minimum between triggers
    if _t.time() - _last_deviation_trigger_ts < cooldown_s:
        return

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
            FROM (SELECT DISTINCT ON (ts) * FROM weather_forecast
                  WHERE ts >= date_trunc('hour', now()) AND ts < date_trunc('hour', now()) + interval '1 hour'
                  ORDER BY ts, fetched_at DESC) sub
        """)
        if not forecast:
            return

        thresholds = await conn.fetch("SELECT * FROM forecast_deviation_thresholds WHERE enabled")

        param_map = {
            "temp_f": ("outdoor_temp_f", "temp_f"),
            "rh_pct": ("outdoor_rh_pct", "rh_pct"),
            "solar_w_m2": ("solar_w_m2", "solar_w_m2"),
        }

        # PL-5 (Sprint 18): σ-gate. Log every threshold-exceeding deviation
        # so history remains complete, but only trigger a replan when the
        # deviation magnitude is at least 1.5σ above typical recent history.
        # Benign oscillations around typical values no longer thrash the
        # planner. The 96h review showed 23 replans / 96 h — most were
        # single-σ wobbles the planner couldn't actually respond to faster
        # than the env was changing.
        SIGMA_MULTIPLIER = 1.5
        SIGMA_HISTORY_DAYS = 7

        logged = []
        triggering = []
        for t in thresholds:
            obs_col, fc_col = param_map.get(t["parameter"], (None, None))
            if not obs_col:
                continue
            observed = current[obs_col]
            forecasted = forecast[fc_col]
            if observed is None or forecasted is None:
                continue
            delta = abs(float(observed) - float(forecasted))
            if delta <= t["threshold"]:
                continue
            dev = {
                "parameter": t["parameter"],
                "observed": round(float(observed), 1),
                "forecasted": round(float(forecasted), 1),
                "delta": round(delta, 1),
                "threshold": t["threshold"],
            }
            logged.append(dev)

            stats = await conn.fetchrow(
                f"""
                SELECT AVG(delta) AS mean, COALESCE(STDDEV(delta), 0.0) AS stddev
                FROM forecast_deviation_log
                WHERE parameter = $1 AND ts > now() - interval '{SIGMA_HISTORY_DAYS} days'
                """,
                t["parameter"],
            )
            if stats and stats["mean"] is not None:
                sigma_gate = float(stats["mean"]) + SIGMA_MULTIPLIER * float(stats["stddev"])
                if delta < sigma_gate:
                    log.info(
                        "PL-5 σ-gate: %s delta=%.1f below %.1f (mean + %sσ of 7d history) — logging but not triggering replan",
                        t["parameter"],
                        delta,
                        sigma_gate,
                        SIGMA_MULTIPLIER,
                    )
                    continue
            triggering.append(dev)

        if not logged:
            return

        # Always persist every threshold-exceeding deviation so historical
        # stats stay representative.
        for d in logged:
            await conn.execute(
                "INSERT INTO forecast_deviation_log (parameter, observed, forecasted, delta, threshold) VALUES ($1,$2,$3,$4,$5)",
                d["parameter"],
                d["observed"],
                d["forecasted"],
                d["delta"],
                d["threshold"],
            )

        if not triggering:
            return

    # Write trigger file and update cooldown
    _last_deviation_trigger_ts = _t.time()
    trigger = {
        "ts": datetime.now(UTC).isoformat(),
        "deviations": triggering,
        "reason": f"Forecast deviation: {', '.join(d['parameter'] for d in triggering)}",
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
    """Update daily_summary for today with live running aggregates.

    Two-writer contract (paired with ingestor.py::write_daily_summary):
      - `write_daily_summary` owns the midnight UPSERT of raw ESP32 accumulators.
      - This function owns the 30-min UPDATE of derived aggregates:
        climate min/max/avg, stress_hours_*, compliance_pct (temp/vpd/both),
        min_dp_margin_f, dp_risk_hours, kwh_estimated, therms_estimated,
        cost_electric/gas/water/total. It also rewrites cycles/runtimes
        computed from equipment_state transitions — which overrides the
        midnight ESP32-accumulator values for the current day (intentional:
        equipment-state-derived is the higher-fidelity source).
    """
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
            WHERE ts >= $1::date::timestamp AT TIME ZONE 'America/Denver'
              AND ts < ($1::date + 1)::timestamp AT TIME ZONE 'America/Denver'
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
              AND ts <= ($1::date + 1)::timestamp AT TIME ZONE 'America/Denver'
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
            WHERE ts >= $1::date::timestamp AT TIME ZONE 'America/Denver'
              AND ts < ($1::date + 1)::timestamp AT TIME ZONE 'America/Denver'
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
                SELECT $1::date::timestamp AT TIME ZONE 'America/Denver' AS day_start,
                       ($1::date + 1)::timestamp AT TIME ZONE 'America/Denver' AS day_end
            ),
            transitions AS (
                SELECT equipment, ts, state,
                       lag(state) OVER (PARTITION BY equipment ORDER BY ts) AS prev_state,
                       lead(ts) OVER (PARTITION BY equipment ORDER BY ts) AS next_ts
                FROM equipment_state, day_bounds
                WHERE ts >= day_bounds.day_start AND ts < day_bounds.day_end
                  AND equipment = ANY($2::text[])
            )
            SELECT equipment,
                   round(sum(extract(epoch FROM
                       coalesce(next_ts, (SELECT day_end FROM day_bounds)) - ts
                   ) / 60.0) FILTER (WHERE state = true), 1) AS on_minutes,
                   count(*) FILTER (
                       WHERE state IS TRUE
                         AND COALESCE(prev_state, FALSE) IS FALSE
                   ) AS cycles
            FROM transitions
            GROUP BY equipment
        """,
            today,
            list(_RT_EQUIP),
        )
        rt = {r["equipment"]: float(r["on_minutes"] or 0) for r in rt_rows}
        cycles = {r["equipment"]: int(r["cycles"] or 0) for r in rt_rows}

        # Energy from runtimes
        kwh = sum(rt.get(e, 0) / 60.0 * w / 1000.0 for e, w in _DS_WATTAGES.items())
        therms = rt.get("heat2", 0) / 60.0 * 75000 / 100000

        # Water
        water_gal = (
            await conn.fetchval(
                """
            SELECT COALESCE(MAX(water_total_gal) - MIN(water_total_gal), 0)
            FROM climate WHERE ts >= $1::date::timestamp AT TIME ZONE 'America/Denver'
              AND ts < ($1::date + 1)::timestamp AT TIME ZONE 'America/Denver'
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
                vpd_compliance_pct=$40,
                cycles_mister_south=$41,
                cycles_mister_west=$42,
                cycles_mister_center=$43,
                cycles_drip_wall=$44,
                cycles_drip_center=$45
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
            cycles.get("mister_south", 0),
            cycles.get("mister_west", 0),
            cycles.get("mister_center", 0),
            cycles.get("drip_wall", 0),
            cycles.get("drip_center", 0),
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

from astral import LocationInfo
from astral.sun import sun as _sun
from iris_planner import CONTEXT_GATHER_FAILED_SENTINEL, gather_context, send_to_iris
from planner_routing import (
    SeverityContext,
    classify_severity,
    pick_instance,
)

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
    # Sprint 24.8 hotfix: midnight must be TODAY's 00:00, not tomorrow's.
    # The old `today + _td(days=1)` form set the milestone to tomorrow's
    # midnight, but the cache-per-day pattern rebuilds at date rollover
    # — the exact moment the milestone would fire. Result: midnight_posture
    # was perpetually 24h in the future and never dispatched. Today's 00:00
    # is in the past by the time we observe it, but the firing window is
    # `0 ≤ delta < 7200` so the task_loop's first tick past 00:00 MDT
    # catches it via the normal window [0, 300s).
    midnight = datetime.combine(today, datetime.min.time(), tzinfo=_DENVER)

    _milestones_cache = {
        "SUNRISE": s["sunrise"],
        "TRANSITION:peak_stress": noon + _td(hours=2),
        "TRANSITION:tree_shade": noon + _td(hours=4),
        "TRANSITION:decline": s["sunset"] - _td(hours=1),
        "SUNSET": s["sunset"],
        # Evening + overnight (closes the 10h blind spot after SUNSET)
        "TRANSITION:evening_settle": s["sunset"] + _td(hours=1),
        "TRANSITION:midnight_posture": midnight,
        "TRANSITION:pre_dawn": s["sunrise"] - _td(hours=1),
    }

    # Load any previously fired milestones from disk (in case of restart)
    _load_milestone_state()

    return _milestones_cache


async def _log_plan_delivery(pool: asyncpg.Pool, result: dict) -> None:
    """F14 (Sprint 24.6): persist a send_to_iris result to plan_delivery_log
    for later delivery→plan correlation. Validated through PlanDeliveryLogRow
    before INSERT; a ValidationError here means an unexpected event_type
    (not in the Literal) or wake_mode — safer to drop than bleed bad data.

    Sprint 24.9 (G-7): honor an explicit `status` in the result dict when
    present (e.g., 'delivery_failed' from the context-gather stub path).
    When absent, the DB default 'pending' applies — unchanged from before.
    """
    row = {
        "event_type": result["event_type"],
        "event_label": result.get("event_label"),
        "session_key": result.get("session_key"),
        "wake_mode": result.get("wake_mode"),
        "gateway_status": result.get("gateway_status"),
        "gateway_body": result.get("gateway_body"),
    }
    try:
        PlanDeliveryLogRow.model_validate(row)
    except ValidationError as e:
        log.error("plan_delivery_log skipped (validation failed: %s): %r", e, row)
        return
    explicit_status = result.get("status")
    if explicit_status is None and result.get("delivered") is False:
        explicit_status = "delivery_failed"
    # Contract v1.4 §2.D — both columns now populated on every INSERT so
    # correlation queries can match deliveries to plans by uuid (not
    # just the 2h time-window fallback in _resolve_delivery_log).
    trigger_id = result.get("trigger_id")
    instance = result.get("instance")
    async with pool.acquire() as conn:
        if explicit_status:
            await conn.execute(
                """
                INSERT INTO plan_delivery_log
                  (event_type, event_label, session_key, wake_mode, gateway_status, gateway_body, status, trigger_id, instance)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::uuid, $9)
                """,
                row["event_type"],
                row["event_label"],
                row["session_key"],
                row["wake_mode"],
                row["gateway_status"],
                row["gateway_body"],
                explicit_status,
                trigger_id,
                instance,
            )
        else:
            await conn.execute(
                """
                INSERT INTO plan_delivery_log
                  (event_type, event_label, session_key, wake_mode, gateway_status, gateway_body, trigger_id, instance)
                VALUES ($1, $2, $3, $4, $5, $6, $7::uuid, $8)
                """,
                row["event_type"],
                row["event_label"],
                row["session_key"],
                row["wake_mode"],
                row["gateway_status"],
                row["gateway_body"],
                trigger_id,
                instance,
            )


async def _deliver_and_log(
    pool: asyncpg.Pool,
    event_type: str,
    label: str,
    context: str,
    instance: str = "opus",
) -> None:
    """Call send_to_iris in the executor and persist the outcome to
    plan_delivery_log. Called from every milestone/forecast/deviation path
    so F14 correlation is complete regardless of trigger source.

    Sprint 24.9 (G-7): if context gathering failed upstream, skip the POST
    entirely and log a plan_delivery_log row with status='delivery_failed'.
    Previously the failure string was spliced into the prompt and Iris
    received gibberish context — the 2026-04-19 incident had gather failures
    that still produced 200 OK dispatches but no useful plan.
    """
    if context == CONTEXT_GATHER_FAILED_SENTINEL:
        log.warning(
            "Skipping %s/%s dispatch: context gathering failed (see alert_log plan_context_failed)",
            event_type,
            label,
        )
        # Write a stub plan_delivery_log row so the outage is visible in
        # operational queries alongside successful deliveries. Generate a
        # trigger_id even for the sentinel path so context-gather failures
        # are countable and individually traceable.
        stub_result = {
            "delivered": False,
            "event_type": event_type,
            "event_label": label,
            "session_key": None,
            "wake_mode": None,
            "gateway_status": None,
            "gateway_body": "context_gather_failed",
            "status": "delivery_failed",
            "trigger_id": str(uuid.uuid4()),
            "instance": instance,
        }
        await _log_plan_delivery(pool, stub_result)
        return

    loop = asyncio.get_event_loop()
    # Threaded executor + kwargs: use a lambda so `instance` propagates
    # through to send_to_iris cleanly (run_in_executor doesn't accept
    # kwargs directly).
    result = await loop.run_in_executor(
        None,
        lambda: send_to_iris(event_type, label, context, instance=instance),
    )
    await _log_plan_delivery(pool, result)


async def _resolve_delivery_log(pool: asyncpg.Pool) -> None:
    """F14 (Sprint 24.6): for each unresolved plan_delivery_log row, look for
    a plan_journal entry created after it and within a 2-hour window. Updates
    `resulting_plan_id` + `plan_written_at`. Bounded to the last 6 hours and
    events that can produce plans (SUNRISE/SUNSET/DEVIATION always do;
    TRANSITION/FORECAST only when Iris chooses to update).

    Sprint 24.9 (G-3): also set status='plan_written' so consumers querying
    `SELECT status, count(*)` see consistent state. Contract v1.4 §2.D
    defines status as the authoritative lifecycle column; resulting_plan_id
    is the join key. Keep them in sync.
    """
    async with pool.acquire() as conn:
        # Contract v1.4 primary path: exact UUID correlation. This is the
        # only reliable join when local/opus may both receive routine
        # triggers inside the old 2h fallback window.
        await conn.execute(
            """
            UPDATE plan_delivery_log pdl
               SET resulting_plan_id = pj.plan_id,
                   plan_written_at   = pj.created_at,
                   status            = 'plan_written'
              FROM plan_journal pj
             WHERE pdl.resulting_plan_id IS NULL
               AND pdl.status = 'pending'
               AND pdl.gateway_status BETWEEN 200 AND 299
               AND pdl.trigger_id IS NOT NULL
               AND pj.trigger_id = pdl.trigger_id
            """,
        )
        # Legacy fallback for pre-v1.4 rows or planner cycles where Iris did
        # not pass the audit kwargs through to set_plan().
        await conn.execute(
            """
            UPDATE plan_delivery_log pdl
               SET resulting_plan_id = pj.plan_id,
                   plan_written_at   = pj.created_at,
                   status            = 'plan_written'
              FROM plan_journal pj
             WHERE pdl.resulting_plan_id IS NULL
               AND pdl.status = 'pending'
               AND pdl.gateway_status BETWEEN 200 AND 299
               AND pdl.delivered_at > now() - interval '6 hours'
               AND pj.created_at BETWEEN pdl.delivered_at AND pdl.delivered_at + interval '2 hours'
               AND pj.created_at = (
                   SELECT MIN(p2.created_at) FROM plan_journal p2
                    WHERE p2.created_at BETWEEN pdl.delivered_at AND pdl.delivered_at + interval '2 hours'
               )
            """,
        )


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

            # Gather context and send to Iris (blocking — runs in executor).
            # SUNRISE/SUNSET/MIDNIGHT always route to opus per contract;
            # TRANSITION routes to local. classify_severity is a no-op for
            # those types so SeverityContext stays default.
            loop = asyncio.get_event_loop()
            context = await loop.run_in_executor(None, gather_context)
            severity = classify_severity(event_type, SeverityContext())
            instance = pick_instance(event_type, severity)
            await _deliver_and_log(pool, event_type, label, context, instance=instance)

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
                # Severity inputs from latest forecast vs previous (Δvpd, Δtemp).
                # Until those deltas are wired in here, classify_severity returns
                # 'minor' so FORECAST routes to local — the cheap peer handles
                # routine forecast refreshes; opus only fires on majors.
                severity = classify_severity("FORECAST", SeverityContext())
                instance = pick_instance("FORECAST", severity)
                await _deliver_and_log(
                    pool,
                    "FORECAST",
                    "New forecast data",
                    context,
                    instance=instance,
                )
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
                # Pull severity hints from the trigger payload if present.
                # max_abs_deviation comes from alert_monitor's deviation
                # writer (alert_monitor stamps it on the trigger when the
                # band excursion exceeds 0.15 normalized). Falling back to
                # 'minor' routes to local; majors escalate to opus.
                severity_ctx = SeverityContext(
                    max_abs_deviation=trigger_data.get("max_abs_deviation"),
                    consecutive_deviation_cycles=trigger_data.get("consecutive_cycles"),
                )
                severity = classify_severity("DEVIATION", severity_ctx)
                instance = pick_instance("DEVIATION", severity)
                await _deliver_and_log(
                    pool,
                    "DEVIATION",
                    deviations_str,
                    context,
                    instance=instance,
                )

                trigger_file.unlink(missing_ok=True)
            except Exception as e:
                log.error("Failed to process deviation trigger: %s", e)

    # ── 4b. Resolve plan_delivery_log entries (F14): update any unresolved
    # rows where a plan landed within 2h of delivery. Runs every heartbeat
    # so the correlation updates in near-real-time, not just at the 30-min
    # verify check below.
    try:
        await _resolve_delivery_log(pool)
    except Exception as e:
        log.warning("plan_delivery_log resolve failed: %s", e)

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

    # ── 6. MCP server health check (every heartbeat = 60s) ──
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: urllib.request.urlopen("http://127.0.0.1:8000/mcp", timeout=5),
        )
        # Any response (even 405 Method Not Allowed) means the server is alive
    except urllib.error.HTTPError:
        pass  # Server is alive, just doesn't accept GET on /mcp — that's fine
    except Exception as e:
        log.error("MCP server unreachable: %s", e)
        # Try to restart it
        try:
            import subprocess as _sp_mcp

            _sp_mcp.Popen(
                ["/srv/greenhouse/.venv/bin/python", "mcp/server.py"],
                cwd="/srv/verdify",
                stdout=open("/srv/verdify/state/mcp-server.log", "a"),
                stderr=open("/srv/verdify/state/mcp-server.log", "a"),
            )
            log.warning("MCP server restarted")
            try:
                token = _load_token(SLACK_TOKEN_FILE)
                _post_slack(token, SLACK_CHANNEL, ":warning: MCP server was unreachable — auto-restarted.")
            except Exception:
                pass
        except Exception as restart_err:
            log.error("MCP server restart failed: %s", restart_err)


# ═════════════════════════════════════════════════════════════════
# 16. SETPOINT CONFIRMATION MONITOR (FB-1, Sprint 20 — every 300s)
#
# Closes Milestone A4 feedback loop: every push the dispatcher makes must
# be confirmed by the ESP32's cfg_* readback within 5 minutes, or we open
# a `setpoint_unconfirmed` alert. Confirmation itself happens in
# ingestor.py's setpoint_snapshot pass — this task just fires alerts for
# the rows that stayed NULL.
#
# Only checks params that have a cfg_* readback route (CFG_READBACK_MAP
# values). Params without readback are not monitored — their confirmation
# remains perpetually NULL by design. The 52-param readback gap is
# tracked as a Sprint 21 firmware follow-up.
# ═════════════════════════════════════════════════════════════════
from entity_map import CFG_READBACK_MAP  # noqa: E402

_READBACKABLE_PARAMS: list[str] = sorted(set(CFG_READBACK_MAP.values()))


async def setpoint_confirmation_monitor(pool: asyncpg.Pool) -> None:
    """FB-1: alert on setpoint_changes rows that never confirmed.

    Severity:
      - warning: 5 min < age < 15 min
      - critical: age >= 15 min (escalation)

    Sprint 25-omnibus (setpoint_unconfirmed lifecycle fix): this monitor
    now owns the full lifecycle of setpoint_unconfirmed alerts — both
    creation (below) AND auto-resolution (first pass, next). alert_monitor
    no longer touches source='ingestor' alerts; without this self-resolve
    pass, confirmed setpoints would leave zombie open alerts forever.
    """
    async with pool.acquire() as conn:
        # Pass 1: auto-resolve unresolved alerts whose underlying
        # setpoint_changes row is now confirmed_at NOT NULL. Acknowledged
        # alerts still block deploy preflight until resolved_at is set.
        # Matches on sensor_id's `setpoint.*` suffix back to the parameter.
        resolved = await conn.fetch(
            """
            UPDATE alert_log al
               SET disposition = 'resolved',
                   resolved_at = now(),
                   resolved_by = 'system',
                   resolution  = 'auto-resolved: confirmation landed'
              FROM (
                  SELECT DISTINCT ON (sc.parameter)
                         sc.parameter, sc.ts, sc.confirmed_at
                    FROM setpoint_changes sc
                   WHERE sc.confirmed_at IS NOT NULL
                   ORDER BY sc.parameter, sc.ts DESC
             ) confirmed
             WHERE al.alert_type = 'setpoint_unconfirmed'
               AND al.resolved_at IS NULL
               AND al.disposition IN ('open', 'acknowledged')
               AND al.source = 'ingestor'
               AND al.sensor_id = 'setpoint.' || confirmed.parameter
               AND confirmed.ts >= COALESCE(NULLIF(al.details->>'pushed_at', '')::timestamptz, al.ts)
            RETURNING al.id
            """,
        )
        if resolved:
            log.info("setpoint_unconfirmed: auto-resolved %d alert(s) after confirmation", len(resolved))

        superseded = await conn.fetch(
            """
            UPDATE alert_log al
               SET disposition = 'resolved',
                   resolved_at = now(),
                   resolved_by = 'system',
                   resolution  = 'auto-resolved: superseded by newer setpoint'
             WHERE al.alert_type = 'setpoint_unconfirmed'
               AND al.resolved_at IS NULL
               AND al.disposition IN ('open', 'acknowledged')
               AND al.source = 'ingestor'
               AND EXISTS (
                   SELECT 1
                     FROM setpoint_changes newer
                   WHERE newer.parameter = replace(al.sensor_id, 'setpoint.', '')
                      AND newer.ts > COALESCE(NULLIF(al.details->>'pushed_at', '')::timestamptz, al.ts)
               )
            RETURNING al.id
            """,
        )
        if superseded:
            log.info("setpoint_unconfirmed: auto-resolved %d superseded alert(s)", len(superseded))

        # Pass 2: scan for still-unconfirmed rows that need alerting.
        rows = await conn.fetch(
            """
            SELECT sc.parameter,
                   sc.value,
                   sc.ts,
                   EXTRACT(EPOCH FROM (now() - sc.ts))::int AS age_s
              FROM setpoint_changes sc
             WHERE sc.confirmed_at IS NULL
               AND sc.ts < now() - interval '5 minutes'
               AND sc.ts > now() - interval '1 hour'
               AND sc.parameter = ANY($1::text[])
               AND NOT EXISTS (
                   SELECT 1
                     FROM setpoint_changes newer
                    WHERE newer.parameter = sc.parameter
                      AND COALESCE(newer.greenhouse_id, '') = COALESCE(sc.greenhouse_id, '')
                      AND newer.ts > sc.ts
               )
             ORDER BY sc.ts DESC
            """,
            _READBACKABLE_PARAMS,
        )
        if not rows:
            return

        for r in rows:
            age_s = int(r["age_s"])
            severity = "critical" if age_s >= 900 else "warning"

            # last cfg readback for that param (best-effort context)
            snap = await conn.fetchrow(
                "SELECT value, ts FROM setpoint_snapshot WHERE parameter=$1 ORDER BY ts DESC LIMIT 1",
                r["parameter"],
            )
            last_cfg = float(snap["value"]) if snap and snap["value"] is not None else None

            # Skip duplicate alerts: one open alert per (parameter, ts) pair.
            existing = await conn.fetchval(
                "SELECT id FROM alert_log "
                "WHERE alert_type='setpoint_unconfirmed' "
                "  AND resolved_at IS NULL "
                "  AND sensor_id=$1",
                f"setpoint.{r['parameter']}",
            )
            if existing is not None:
                # Already alerted — escalate severity only if crossed the 15-min threshold
                if severity == "critical":
                    await conn.execute(
                        "UPDATE alert_log SET severity='critical', message=$2, details=$3 WHERE id=$1",
                        existing,
                        (
                            f"Setpoint unconfirmed >15 min: {r['parameter']}={float(r['value']):.3f} "
                            f"pushed at {r['ts']:%H:%M:%S} UTC, last cfg readback "
                            f"{last_cfg if last_cfg is not None else '(none)'}"
                        ),
                        json.dumps(
                            {
                                "parameter": r["parameter"],
                                "requested_value": float(r["value"]),
                                "last_cfg_readback": last_cfg,
                                "age_s": age_s,
                                "pushed_at": r["ts"].isoformat(),
                            }
                        ),
                    )
                continue

            await conn.execute(
                "INSERT INTO alert_log "
                "(alert_type, severity, category, sensor_id, message, details, source) "
                "VALUES ('setpoint_unconfirmed', $1, 'system', $2, $3, $4::jsonb, 'ingestor')",
                severity,
                f"setpoint.{r['parameter']}",
                (
                    f"Setpoint unconfirmed >5 min: {r['parameter']}={float(r['value']):.3f} "
                    f"pushed at {r['ts']:%H:%M:%S} UTC, last cfg readback "
                    f"{last_cfg if last_cfg is not None else '(none)'}"
                ),
                json.dumps(
                    {
                        "parameter": r["parameter"],
                        "requested_value": float(r["value"]),
                        "last_cfg_readback": last_cfg,
                        "age_s": age_s,
                        "pushed_at": r["ts"].isoformat(),
                    }
                ),
            )

        log.info("Setpoint confirmation monitor: %d unconfirmed row(s)", len(rows))


# ═════════════════════════════════════════════════════════════════
# 17. MIDNIGHT WATCH (Sprint 24.7 — ops stopgap until contract v1.4 SLA rule)
#
# At 00:05 MDT each day, check whether tonight's MIDNIGHT opus trigger
# fired and produced a plan. Posts ONE Slack message per night with the
# outcome so operators know without scraping journalctl. Retires once
# Sprint 25's alert_monitor rule 7 rewrite (per-pair SLA over
# plan_delivery_log) lands — that's the structural fix; this is the
# visibility gap-closer until then.
#
# Matches both future-canonical (event_type='MIDNIGHT' after Sprint 25
# splits it out) and today's form (event_type='TRANSITION' with
# event_label containing "Midnight").
# ═════════════════════════════════════════════════════════════════

_midnight_watch_last_date: str = ""


async def midnight_watch(pool: asyncpg.Pool) -> None:
    """Daily 00:05 MDT check that the midnight opus trigger ran.

    Three Slack outcomes (per iris-dev's ops-stopgap spec):
      - resulting_plan_id populated  → ✅ "Iris wrote plan X"
      - row exists, plan NULL        → ⚠️ "delivered but no plan yet" (+ 2h-cover note)
      - no row in the 30-min window  → 🔴 "trigger was not delivered" (escalation)
    """
    global _midnight_watch_last_date
    now_mt = datetime.now(ZoneInfo("America/Denver"))

    # Fire only in the 00:05-00:10 MDT window; dedupe by date so a ~60s
    # task_loop that sees the window 5 times only posts once.
    if now_mt.hour != 0 or not (5 <= now_mt.minute < 10):
        return
    today_str = str(now_mt.date())
    if _midnight_watch_last_date == today_str:
        return

    async with pool.acquire() as conn:
        # Match both v1.4 MIDNIGHT event_type and today's TRANSITION:midnight_posture label.
        row = await conn.fetchrow(
            """
            SELECT event_type, event_label, delivered_at, resulting_plan_id
              FROM plan_delivery_log
             WHERE (event_type = 'MIDNIGHT'
                    OR (event_type = 'TRANSITION' AND event_label ILIKE '%midnight%'))
               AND delivered_at > now() - interval '30 minutes'
             ORDER BY delivered_at DESC
             LIMIT 1
            """,
        )

        if row is None:
            msg = "\U0001f534 *Midnight watch:* trigger was not delivered in the last 30 min (escalation)"
        elif row["resulting_plan_id"]:
            msg = (
                f"\u2705 *Midnight watch:* Iris wrote plan `{row['resulting_plan_id']}` "
                f"(trigger `{row['event_type']}/{row['event_label'] or ''}` at {row['delivered_at']:%H:%M UTC})"
            )
        else:
            # Delivered but no plan — note if an earlier plan within 2h covers the window.
            recent_plan = await conn.fetchval(
                "SELECT plan_id FROM plan_journal WHERE created_at > now() - interval '2 hours' "
                "ORDER BY created_at DESC LIMIT 1"
            )
            covers = f" (prior plan `{recent_plan}` within 2h may cover)" if recent_plan else ""
            msg = (
                f"\U0001f7e1 *Midnight watch:* trigger delivered at {row['delivered_at']:%H:%M UTC} "
                f"but no plan yet{covers}"
            )

    _midnight_watch_last_date = today_str
    try:
        token = _load_token(SLACK_TOKEN_FILE)
        _post_slack(token, SLACK_CHANNEL, msg)
        log.info("midnight_watch: %s", msg)
    except Exception as e:
        log.error("midnight_watch Slack post failed: %s", e)
