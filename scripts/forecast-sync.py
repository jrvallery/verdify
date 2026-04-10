#!/usr/bin/env /srv/greenhouse/.venv/bin/python3
"""
forecast-sync.py — Fetch 16-day hourly forecast from Open-Meteo, upsert into weather_forecast.

Uses the free Open-Meteo API (no key needed). 1km local resolution for first few days,
blending to 11km global for days 4-16. 25 parameters covering temperature, humidity, VPD,
precipitation, radiation, wind, soil, and visibility.

Runs every 6 hours via systemd timer.

Usage:
    forecast-sync.py           # run once
    forecast-sync.py --force   # skip throttle check
"""

import asyncio
import json
import logging
import urllib.error
import urllib.request
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import asyncpg

LATITUDE = 40.1672
LONGITUDE = -105.1019
DENVER = ZoneInfo("America/Denver")

# Full Open-Meteo API — 25 greenhouse-relevant parameters, 16-day horizon
FORECAST_URL = (
    f"https://api.open-meteo.com/v1/forecast"
    f"?latitude={LATITUDE}&longitude={LONGITUDE}"
    f"&hourly=temperature_2m,relative_humidity_2m,dew_point_2m,"
    f"apparent_temperature,precipitation_probability,precipitation,"
    f"rain,snowfall,weather_code,"
    f"cloud_cover,cloud_cover_low,cloud_cover_high,"
    f"wind_speed_10m,wind_direction_10m,wind_gusts_10m,"
    f"shortwave_radiation,direct_radiation,diffuse_radiation,"
    f"uv_index,sunshine_duration,"
    f"vapour_pressure_deficit,surface_pressure,"
    f"et0_fao_evapotranspiration,"
    f"soil_temperature_0cm,visibility"
    f"&temperature_unit=fahrenheit"
    f"&wind_speed_unit=mph"
    f"&precipitation_unit=inch"
    f"&forecast_days=16"
    f"&timezone=America%2FDenver"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [forecast-sync] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def get_db_url() -> str:
    pw = "verdify"
    with open("/srv/verdify/.env") as f:
        for line in f:
            if line.strip().startswith("POSTGRES_PASSWORD="):
                pw = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    return f"postgresql://verdify:{pw}@localhost:5432/verdify"


def fetch_forecast() -> list[dict] | None:
    """Fetch full forecast from Open-Meteo."""
    req = urllib.request.Request(FORECAST_URL, headers={"User-Agent": "verdify-forecast-sync/2.0"})
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


async def main():
    db_url = get_db_url()
    conn = await asyncpg.connect(db_url)
    now = datetime.now(UTC)

    try:
        rows = fetch_forecast()
        if not rows:
            log.warning("No forecast data returned")
            return

        # Delete forecasts older than 30 days (accumulation mode — keep history)
        deleted = await conn.execute("DELETE FROM weather_forecast WHERE fetched_at < now() - interval '30 days'")
        if "DELETE" in deleted and deleted != "DELETE 0":
            log.info("Cleaned up old forecasts: %s", deleted)

        # INSERT each forecast hour (accumulation mode — no overwrite)
        # Each (ts, fetched_at) pair is a unique forecast version
        inserted = 0
        for row in rows:
            ts = datetime.fromisoformat(row["ts"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=DENVER).astimezone(UTC)

            await conn.execute(
                """
                INSERT INTO weather_forecast
                    (ts, fetched_at, temp_f, rh_pct, wind_speed_mph, wind_dir_deg,
                     cloud_cover_pct, precip_prob_pct, solar_w_m2,
                     dew_point_f, feels_like_f, vpd_kpa, precip_in, rain_in, snow_in,
                     wind_gust_mph, uv_index, et0_mm, direct_radiation_w_m2, diffuse_radiation_w_m2,
                     sunshine_duration_s, weather_code, cloud_cover_low_pct, cloud_cover_high_pct,
                     surface_pressure_hpa, soil_temp_f, visibility_m)
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
            inserted += 1

        log.info("Forecast: %d rows inserted (16-day, 25 params), fetched_at=%s", inserted, now.strftime("%H:%M UTC"))

        stats = await conn.fetchrow(
            "SELECT count(*) AS cnt, MIN(ts) AS min_ts, MAX(ts) AS max_ts FROM weather_forecast"
        )
        log.info("Total: %d rows, range %s → %s", stats["cnt"], stats["min_ts"], stats["max_ts"])

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
