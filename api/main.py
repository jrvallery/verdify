"""
Verdify Crop Catalog API — FastAPI backend for crop management.

Endpoints: crops CRUD, observations, events, health trends, zones.
Runs on port 8300 (internal network only).

Usage:
    uvicorn main:app --host 0.0.0.0 --port 8300
"""

import os
import sys
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, HTTPException

# verdify_schemas is mounted at /app/verdify_schemas inside the container
# (see docker-compose.yml api.volumes). For host-side dev runs, /mnt/iris/verdify
# contains the package; Python auto-discovers either path.
for _p in ("/app", "/mnt/iris/verdify"):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from verdify_schemas import CropCreate, CropUpdate, EventCreate, ObservationCreate  # noqa: E402

# ── DB Connection ──


def get_db_dsn():
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    host = os.environ.get("DB_HOST", "localhost")
    name = os.environ.get("DB_NAME", "verdify")
    user = os.environ.get("DB_USER", "verdify")
    pw = os.environ.get("DB_PASS", "verdify")
    if host.startswith("/cloudsql/"):
        return f"postgresql://{user}:{pw}@/{name}?host={host}"
    return f"postgresql://{user}:{pw}@{host}:5432/{name}"


pool: asyncpg.Pool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await asyncpg.create_pool(get_db_dsn(), min_size=1, max_size=3, max_inactive_connection_lifetime=60)
    yield
    await pool.close()


app = FastAPI(
    title="Verdify Crop Catalog API",
    version="1.0.0",
    description="Greenhouse crop management — inventory, observations, health tracking",
    lifespan=lifespan,
)

# ── Models ──
#
# Sprint 21: request-body models moved to /mnt/iris/verdify/verdify_schemas/crops.py.
# Any change to fields or validation rules lives there now; every caller
# (API, MCP crops tool, vault-crop-writer, planner) shares the same shape.

DEFAULT_GREENHOUSE = "vallery"

# ── Setpoints (ESP32 pulls this every 5 min) ──


@app.get("/setpoints")
@app.get("/api/v1/greenhouses/{greenhouse_id}/setpoints")
async def get_setpoints(greenhouse_id: str = DEFAULT_GREENHOUSE):
    """Return setpoints in key=value format for ESP32 consumption."""
    # Band-driven params that fn_band_setpoints() computes from crop profiles
    BAND_COMPUTED = {"temp_high", "temp_low", "vpd_high", "vpd_low"}
    async with pool.acquire() as conn:
        # Get latest value per parameter (Tier 1 + band-driven only, no legacy params)
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (parameter) parameter, value
            FROM setpoint_changes WHERE greenhouse_id = $1
              AND parameter IN (
                'vpd_hysteresis','vpd_watch_dwell_s','mister_engage_kpa','mister_all_kpa',
                'mister_pulse_on_s','mister_pulse_gap_s','mister_vpd_weight','mister_water_budget_gal',
                'mist_vent_close_lead_s','mist_max_closed_vent_s','mist_vent_reopen_delay_s','mist_thermal_relief_s',
                'enthalpy_open','enthalpy_close','min_vent_on_s','min_vent_off_s',
                'min_fog_on_s','min_fog_off_s','fog_escalation_kpa',
                'd_cool_stage_2','bias_heat','bias_cool','min_heat_on_s','min_heat_off_s',
                'temp_high','temp_low','vpd_high','vpd_low',
                'vpd_target_south','vpd_target_west','vpd_target_east','vpd_target_center',
                'mister_engage_delay_s','mister_all_delay_s','mister_center_penalty',
                'lead_rotate_s','min_fan_on_s','min_fan_off_s',
                'east_adjacency_factor','irrig_vpd_boost_pct','irrig_vpd_boost_threshold_hrs',
                'fog_rh_ceiling_pct','fog_min_temp_f','fog_time_window_start','fog_time_window_end',
                'gl_dli_target','gl_sunrise_hour','gl_sunset_hour','gl_lux_threshold',
                'safety_min','safety_max','safety_vpd_min','safety_vpd_max',
                'site_pressure_hpa','fog_burst_min','fan_burst_min','vent_bypass_min'
              )
            ORDER BY parameter, ts DESC
        """,
            greenhouse_id,
        )
        # For band-driven params, compute from crop science + sun angle
        band_row = await conn.fetchrow("SELECT * FROM fn_band_setpoints(now())")
        zone_row = await conn.fetchrow("SELECT * FROM fn_zone_vpd_targets(now())")
        # Tier 1 #3: fail loud if band computation returned NULL.
        # Without band, ESP32 receives no temp/VPD band params and silently
        # runs whatever it cached last, which can be hours stale. Better to
        # 503 and let ESP32 retry in 5 min than return a partial response.
        if band_row is None or zone_row is None:
            existing = await conn.fetchval(
                "SELECT id FROM alert_log WHERE alert_type = 'band_fn_null' AND disposition = 'open' LIMIT 1"
            )
            if existing is None:
                await conn.execute(
                    "INSERT INTO alert_log (alert_type, severity, category, message, details, source) "
                    "VALUES ('band_fn_null', 'critical', 'system', $1, $2, 'api')",
                    "fn_band_setpoints or fn_zone_vpd_targets returned NULL — ESP32 cannot refresh band setpoints",
                    '{"band_row_null": '
                    + ("true" if band_row is None else "false")
                    + ', "zone_row_null": '
                    + ("true" if zone_row is None else "false")
                    + "}",
                )
            raise HTTPException(
                status_code=503,
                detail="band setpoint computation unavailable — check fn_band_setpoints + crop catalog",
            )
        plan_rows = await conn.fetch("SELECT parameter, value FROM v_active_plan")
        params = {r["parameter"]: r["value"] for r in rows}
        # Planner overrides for all params (band params will be clamped below)
        for r in plan_rows:
            params[r["parameter"]] = r["value"]
        # Band-driven params: always use fn_band_setpoints as the authoritative source.
        # If a planner value exists and is tighter than the band, use it (clamped).
        # Otherwise, use the band value directly.
        if band_row:
            # Collect planner values (from v_active_plan only, not stale setpoint_changes)
            planner_band = {r["parameter"]: r["value"] for r in plan_rows if r["parameter"] in BAND_COMPUTED}
            for param in BAND_COMPUTED:
                band_val = round(float(band_row[param]), 1)
                if param in planner_band:
                    pv = float(planner_band[param])
                    band_lo = float(band_row["temp_low" if param.startswith("temp") else "vpd_low"])
                    band_hi = float(band_row["temp_high" if param.startswith("temp") else "vpd_high"])
                    params[param] = round(max(band_lo, min(band_hi, pv)), 1)
                else:
                    params[param] = band_val
        # Per-zone VPD targets (from crop data per zone)
        if zone_row:
            for param in ("vpd_target_south", "vpd_target_west", "vpd_target_east", "vpd_target_center"):
                params[param] = round(float(zone_row[param]), 2)
        # Mister tuning: band provides defaults, planner can override.
        # Set band-derived values first, then planner values overwrite if present.
        if band_row:
            vpd_hi = float(band_row["vpd_high"])
            # Band defaults — will be overwritten by planner values from setpoint_changes if present
            params.setdefault("mister_engage_kpa", round(vpd_hi, 2))
            params.setdefault("mister_all_kpa", round(vpd_hi + 0.3, 2))
        outdoor = await conn.fetchrow(
            """
            SELECT outdoor_temp_f, outdoor_rh_pct FROM climate
            WHERE outdoor_temp_f IS NOT NULL AND greenhouse_id = $1
            ORDER BY ts DESC LIMIT 1
        """,
            greenhouse_id,
        )
        if outdoor:
            if outdoor["outdoor_temp_f"]:
                params["outdoor_temp"] = round(outdoor["outdoor_temp_f"], 1)
            if outdoor["outdoor_rh_pct"]:
                params["outdoor_rh"] = round(outdoor["outdoor_rh_pct"], 0)
    lines = [f"{k}={v}" for k, v in sorted(params.items())]
    lines.append("source=local")
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(content="\n".join(lines) + "\n")


# ── Lights (ESP32 grow light control via MQTT command) ──


@app.post("/api/v1/greenhouses/{greenhouse_id}/lights/{circuit}/{action}")
async def control_lights(greenhouse_id: str, circuit: str, action: str):
    """Publish light command to MQTT for the Lutron bridge to execute."""
    if circuit not in ("main", "grow") or action not in ("on", "off"):
        raise HTTPException(status_code=400, detail="Invalid circuit or action")
    # For now, record the intent in the DB. The local Lutron bridge
    # or a future MQTT subscriber handles the actual switch.
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO equipment_state (ts, equipment, state, greenhouse_id)
            VALUES (now(), $1, $2, $3)
        """,
            f"grow_light_{circuit}",
            action == "on",
            greenhouse_id,
        )
    return {"light": circuit, "action": action, "greenhouse_id": greenhouse_id, "status": "recorded"}


# ── Root + Health ──


@app.get("/")
async def root():
    return {
        "service": "verdify-api",
        "version": "1.0.0",
        "greenhouse": DEFAULT_GREENHOUSE,
        "docs": "/docs",
        "status": "/api/v1/status",
    }


@app.get("/health")
async def health():
    """Health check endpoint for external monitoring (Prometheus, uptime checks)."""
    checks = {}
    overall = "ok"

    async with pool.acquire() as conn:
        # Climate data freshness
        age = await conn.fetchval("SELECT extract(epoch FROM now() - max(ts))::int FROM climate")
        checks["climate_age_seconds"] = age
        if age and age > 300:
            overall = "degraded"

        # Scorecard
        score_row = await conn.fetchrow(
            "SELECT compliance_pct, planner_score FROM v_planner_performance WHERE date = CURRENT_DATE"
        )
        if score_row:
            checks["compliance_pct"] = float(score_row["compliance_pct"]) if score_row["compliance_pct"] else 0
            checks["planner_score"] = float(score_row["planner_score"]) if score_row["planner_score"] else 0

        # Active alerts
        alert_count = await conn.fetchval("SELECT count(*) FROM alert_log WHERE ts > now() - interval '1 hour'")
        checks["active_alerts_1h"] = alert_count

        # Setpoint dispatch freshness
        last_dispatch = await conn.fetchval("SELECT extract(epoch FROM now() - max(ts))::int FROM setpoint_changes")
        checks["last_setpoint_change_seconds"] = last_dispatch

        # ESP32 mode
        mode = await conn.fetchval(
            "SELECT value FROM system_state WHERE entity = 'greenhouse_state' ORDER BY ts DESC LIMIT 1"
        )
        checks["greenhouse_mode"] = mode

    # Service health inferred from data freshness (API runs inside Docker — no systemctl/host access)
    climate_age = checks.get("climate_age_seconds", 999)
    checks["service_ingestor"] = "ok" if climate_age < 300 else "stale"
    # MCP server health is monitored by the ingestor (planning_heartbeat), not the API.
    # The API can't reach localhost:8000 from inside Docker (MCP binds to 127.0.0.1 on host).

    return {"status": overall, "checks": checks}


# ── Greenhouse ──


@app.get("/api/v1/greenhouses")
async def list_greenhouses():
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM greenhouses ORDER BY name")
    return [dict(r) for r in rows]


@app.get("/api/v1/greenhouses/{greenhouse_id}")
async def get_greenhouse(greenhouse_id: str):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM greenhouses WHERE id = $1", greenhouse_id)
        if not row:
            raise HTTPException(404, f"Greenhouse '{greenhouse_id}' not found")
        crops = await conn.fetchval("SELECT COUNT(*) FROM crops WHERE greenhouse_id = $1 AND is_active", greenhouse_id)
        result = dict(row)
        result["active_crops"] = crops
    return result


# ── Crops (greenhouse-scoped + legacy aliases) ──


@app.get("/api/v1/greenhouses/{greenhouse_id}/crops")
@app.get("/api/v1/crops")  # Legacy alias (defaults to vallery)
async def list_crops(
    greenhouse_id: str = DEFAULT_GREENHOUSE,
    zone: str | None = None,
    stage: str | None = None,
    active: bool = True,
):
    query = "SELECT c.*, (SELECT ROUND(AVG(o.health_score)::numeric, 2) FROM observations o WHERE o.crop_id = c.id AND o.health_score IS NOT NULL AND o.ts > now() - interval '7 days') AS latest_health FROM crops c WHERE c.is_active = $1 AND c.greenhouse_id = $2"
    params = [active, greenhouse_id]
    idx = 3
    if zone:
        query += f" AND c.zone = ${idx}"
        params.append(zone)
        idx += 1
    if stage:
        query += f" AND c.stage = ${idx}"
        params.append(stage)
        idx += 1
    query += " ORDER BY c.zone, c.position"

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) for r in rows]


@app.get("/api/v1/crops/{crop_id}")
async def get_crop(crop_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM crops WHERE id = $1", crop_id)
        if not row:
            raise HTTPException(404, "Crop not found")

        health = await conn.fetchval(
            "SELECT ROUND(AVG(health_score)::numeric, 2) FROM observations WHERE crop_id = $1 AND health_score IS NOT NULL AND ts > now() - interval '7 days'",
            crop_id,
        )

        recent_obs = await conn.fetch(
            "SELECT ts, obs_type, notes, health_score, observer FROM observations WHERE crop_id = $1 ORDER BY ts DESC LIMIT 5",
            crop_id,
        )

        result = dict(row)
        result["latest_health"] = float(health) if health else None
        result["recent_observations"] = [dict(o) for o in recent_obs]
    return result


@app.post("/api/v1/greenhouses/{greenhouse_id}/crops", status_code=201)
@app.post("/api/v1/crops", status_code=201)
async def create_crop(crop: CropCreate, greenhouse_id: str = DEFAULT_GREENHOUSE):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO crops (name, variety, position, zone, planted_date, expected_harvest,
                stage, count, seed_lot_id, supplier, base_temp_f, target_dli,
                target_vpd_low, target_vpd_high, notes, greenhouse_id)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
            RETURNING *
        """,
            crop.name,
            crop.variety,
            crop.position,
            crop.zone,
            crop.planted_date,
            crop.expected_harvest,
            crop.stage,
            crop.count,
            crop.seed_lot_id,
            crop.supplier,
            crop.base_temp_f,
            crop.target_dli,
            crop.target_vpd_low,
            crop.target_vpd_high,
            crop.notes,
            greenhouse_id,
        )

        # Record the planting event
        await conn.execute(
            "INSERT INTO crop_events (crop_id, event_type, new_stage, source, notes) VALUES ($1, 'planted', $2, 'api', $3)",
            row["id"],
            crop.stage,
            f"Created via API: {crop.name} at {crop.position}",
        )

    return dict(row)


@app.put("/api/v1/crops/{crop_id}")
async def update_crop(crop_id: int, crop: CropUpdate):
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT * FROM crops WHERE id = $1", crop_id)
        if not existing:
            raise HTTPException(404, "Crop not found")

        ALLOWED_COLUMNS = {
            "name",
            "variety",
            "zone",
            "position",
            "stage",
            "planted_date",
            "expected_harvest",
            "notes",
            "is_active",
            "vpd_min",
            "vpd_max",
            "temp_min_f",
            "temp_max_f",
            "dli_target",
        }
        updates = {k: v for k, v in crop.model_dump().items() if v is not None and k in ALLOWED_COLUMNS}
        if not updates:
            return dict(existing)

        set_parts = []
        vals = []
        for i, (k, v) in enumerate(updates.items()):
            set_parts.append(f"{k} = ${i + 1}")
            vals.append(v)
        vals.append(crop_id)
        set_sql = ", ".join(set_parts)

        row = await conn.fetchrow(
            f"UPDATE crops SET {set_sql}, updated_at = now() WHERE id = ${len(vals)} RETURNING *", *vals
        )

        # Record stage change event if stage changed
        if "stage" in updates and updates["stage"] != existing["stage"]:
            await conn.execute(
                "INSERT INTO crop_events (crop_id, event_type, old_stage, new_stage, source) VALUES ($1, 'stage_change', $2, $3, 'api')",
                crop_id,
                existing["stage"],
                updates["stage"],
            )

    return dict(row)


@app.delete("/api/v1/crops/{crop_id}")
async def delete_crop(crop_id: int):
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE crops SET is_active = false, updated_at = now() WHERE id = $1 AND is_active = true", crop_id
        )
        if result == "UPDATE 0":
            raise HTTPException(404, "Crop not found or already inactive")

        await conn.execute(
            "INSERT INTO crop_events (crop_id, event_type, source, notes) VALUES ($1, 'removed', 'api', 'Deactivated via API')",
            crop_id,
        )

    return {"status": "deactivated", "id": crop_id}


# ── Observations ──


@app.get("/api/v1/crops/{crop_id}/observations")
async def list_observations(crop_id: int, limit: int = 20):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM observations WHERE crop_id = $1 ORDER BY ts DESC LIMIT $2", crop_id, limit
        )
    return [dict(r) for r in rows]


@app.post("/api/v1/crops/{crop_id}/observations", status_code=201)
async def create_observation(crop_id: int, obs: ObservationCreate):
    async with pool.acquire() as conn:
        crop = await conn.fetchrow("SELECT zone, position FROM crops WHERE id = $1", crop_id)
        if not crop:
            raise HTTPException(404, "Crop not found")

        row = await conn.fetchrow(
            """
            INSERT INTO observations (crop_id, zone, position, obs_type, notes, severity, observer, health_score, source)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'api')
            RETURNING *
        """,
            crop_id,
            crop["zone"],
            crop["position"],
            obs.obs_type,
            obs.notes,
            obs.severity,
            obs.observer,
            obs.health_score,
        )
    return dict(row)


@app.get("/api/v1/observations/recent")
async def recent_observations(limit: int = 20):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT o.*, c.name AS crop_name, c.zone AS crop_zone
            FROM observations o
            LEFT JOIN crops c ON o.crop_id = c.id
            ORDER BY o.ts DESC LIMIT $1
        """,
            limit,
        )
    return [dict(r) for r in rows]


# ── Events ──


@app.get("/api/v1/crops/{crop_id}/events")
async def list_events(crop_id: int, limit: int = 20):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM crop_events WHERE crop_id = $1 ORDER BY ts DESC LIMIT $2", crop_id, limit
        )
    return [dict(r) for r in rows]


@app.post("/api/v1/crops/{crop_id}/events", status_code=201)
async def create_event(crop_id: int, event: EventCreate):
    async with pool.acquire() as conn:
        crop = await conn.fetchrow("SELECT id FROM crops WHERE id = $1", crop_id)
        if not crop:
            raise HTTPException(404, "Crop not found")

        row = await conn.fetchrow(
            """
            INSERT INTO crop_events (crop_id, event_type, old_stage, new_stage, count, operator, source, notes)
            VALUES ($1, $2, $3, $4, $5, $6, 'api', $7)
            RETURNING *
        """,
            crop_id,
            event.event_type,
            event.old_stage,
            event.new_stage,
            event.count,
            event.operator,
            event.notes,
        )

        # Auto-update crop stage if new_stage provided
        if event.new_stage:
            await conn.execute(
                "UPDATE crops SET stage = $1, updated_at = now() WHERE id = $2", event.new_stage, crop_id
            )

    return dict(row)


# ── Health ──


@app.get("/api/v1/crops/{crop_id}/health")
async def crop_health(crop_id: int, days: int = 30):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ts, health_score, obs_type, notes, source
            FROM observations
            WHERE crop_id = $1 AND health_score IS NOT NULL AND ts > now() - ($2 || ' days')::interval
            ORDER BY ts
        """,
            crop_id,
            str(days),
        )
    return [dict(r) for r in rows]


@app.get("/api/v1/greenhouses/{greenhouse_id}/health")
@app.get("/api/v1/health/summary")
async def health_summary(greenhouse_id: str = DEFAULT_GREENHOUSE):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.name, c.zone, c.position, c.stage,
                ROUND(AVG(o.health_score)::numeric, 2) AS avg_health,
                COUNT(o.id) AS obs_count,
                MAX(o.ts) AS last_observed
            FROM crops c
            LEFT JOIN observations o ON c.id = o.crop_id AND o.health_score IS NOT NULL AND o.ts > now() - interval '7 days'
            WHERE c.is_active = true AND c.greenhouse_id = $1
            GROUP BY c.id, c.name, c.zone, c.position, c.stage
            ORDER BY c.zone, c.position
        """,
            greenhouse_id,
        )
    return [dict(r) for r in rows]


# ── Zones ──


@app.get("/api/v1/zones")
async def list_zones():
    async with pool.acquire() as conn:
        zones = await conn.fetch("""
            SELECT zone,
                COUNT(*) FILTER (WHERE is_active) AS active_crops,
                (SELECT ROUND(temp_avg::numeric, 1) FROM climate
                 WHERE ts > now() - interval '5 minutes' ORDER BY ts DESC LIMIT 1) AS current_temp
            FROM crops GROUP BY zone ORDER BY zone
        """)
    return [dict(z) for z in zones]


@app.get("/api/v1/zones/{zone}")
async def get_zone(zone: str):
    async with pool.acquire() as conn:
        crops = await conn.fetch("SELECT * FROM crops WHERE zone = $1 AND is_active ORDER BY position", zone)
        if not crops:
            raise HTTPException(404, f"No crops in zone '{zone}'")

        observations = await conn.fetch(
            """
            SELECT o.*, c.name AS crop_name
            FROM observations o JOIN crops c ON o.crop_id = c.id
            WHERE c.zone = $1 AND o.ts > now() - interval '7 days'
            ORDER BY o.ts DESC LIMIT 10
        """,
            zone,
        )

    return {
        "zone": zone,
        "crops": [dict(c) for c in crops],
        "recent_observations": [dict(o) for o in observations],
    }


# ── System ──


@app.get("/api/v1/status")
async def status():
    async with pool.acquire() as conn:
        crop_count = await conn.fetchval("SELECT COUNT(*) FROM crops WHERE is_active")
        obs_count = await conn.fetchval("SELECT COUNT(*) FROM observations")
        latest = await conn.fetchval("SELECT MAX(ts) FROM climate")
    return {
        "status": "ok",
        "active_crops": crop_count,
        "observations": obs_count,
        "latest_climate_ts": latest,
    }

    # (duplicate /health removed — defined at line 233)
