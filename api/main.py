"""
Verdify Crop Catalog API — FastAPI backend for crop management.

Endpoints: crops CRUD, observations, events, health trends, zones.
Runs on port 8300 (internal network only).

Usage:
    uvicorn main:app --host 0.0.0.0 --port 8300
"""

import asyncio
import hashlib
import hmac
import ipaddress
import json
import os
import re
import smtplib
import sys
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from datetime import date
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Annotated

import asyncpg
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, ValidationError


def _coerce_jsonb(row_dict: dict, *keys: str) -> dict:
    """asyncpg returns JSONB columns as strings unless a codec is registered.
    Parse the named keys from str → list/dict so response_model validation works.
    """
    for k in keys:
        v = row_dict.get(k)
        if isinstance(v, str):
            row_dict[k] = json.loads(v)
    return row_dict


# verdify_schemas is mounted at /app/verdify_schemas inside the container
# (see docker-compose.yml api.volumes). For host-side dev runs, /mnt/iris/verdify
# contains the package; Python auto-discovers either path.
for _p in ("/app", "/mnt/iris/verdify"):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from verdify_schemas import (  # noqa: E402
    AlertEnvelope,
    APIStatus,
    CropCreate,
    CropDetail,
    CropHealthSummaryItem,
    CropHistoryEntry,
    CropLifecycle,
    CropListItem,
    CropUpdate,
    EventCreate,
    HealthTrendPoint,
    ObservationCreate,
    ObservationWithCrop,
    PositionCurrentEntry,
    PublicDataHealthCheck,
    PublicDataHealthResponse,
    PublicHomeMetrics,
    PublicPipelineHealthSource,
    ZoneDetail,
    ZoneListItem,
)
from verdify_schemas.mcp_responses import ScorecardResponse  # noqa: E402

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
    docs_url="/docs" if os.environ.get("VERDIFY_ENABLE_API_DOCS", "").lower() in {"1", "true", "yes"} else None,
    redoc_url="/redoc" if os.environ.get("VERDIFY_ENABLE_API_DOCS", "").lower() in {"1", "true", "yes"} else None,
    # Keep OpenAPI available for contract/drift tests, but noindex it at
    # Traefik/API headers and keep the interactive docs hidden by default.
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://verdify.ai", "https://www.verdify.ai", "http://localhost:8080"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def noindex_api_responses(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


# ── Models ──
#
# Sprint 21: request-body models moved to /mnt/iris/verdify/verdify_schemas/crops.py.
# Any change to fields or validation rules lives there now; every caller
# (API, MCP crops tool, vault-crop-writer, planner) shares the same shape.

DEFAULT_GREENHOUSE = "vallery"
WRITE_API_KEY_ENV = "VERDIFY_WRITE_API_KEY"
ALLOW_UNAUTHENTICATED_WRITES_ENV = "VERDIFY_ALLOW_UNAUTHENTICATED_WRITES"
CONTACT_ALLOWED_TOPICS = {"build", "control", "data", "press", "collaboration", "correction", "other"}
CONTACT_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CONTACT_URL_RE = re.compile(r"(https?://|www\.)", re.IGNORECASE)
CONTACT_NOTIFY_SUBJECT_PREFIX = "Verdify contact"


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _trim(value: str | None, max_len: int) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return trimmed[:max_len]


def _clean_email_header(value: str | None, max_len: int = 160) -> str:
    return (_trim((value or "").replace("\r", " ").replace("\n", " "), max_len) or "").strip()


def _client_ip(request: Request) -> str:
    """Prefer Cloudflare's client IP header; store only a salted hash."""
    candidates = [
        request.headers.get("CF-Connecting-IP"),
        (request.headers.get("X-Forwarded-For") or "").split(",")[0],
        request.client.host if request.client else None,
    ]
    for candidate in candidates:
        if not candidate:
            continue
        value = candidate.strip()
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            continue
    return "unknown"


def _contact_ip_hash(ip: str) -> str:
    salt = (
        os.environ.get("VERDIFY_CONTACT_HASH_SALT")
        or os.environ.get(WRITE_API_KEY_ENV)
        or os.environ.get("DB_PASS")
        or "verdify-contact-v1"
    )
    return hashlib.sha256(f"{salt}:{ip}".encode()).hexdigest()


def _turnstile_verify_sync(secret: str, token: str, remote_ip: str) -> bool:
    payload = urllib.parse.urlencode(
        {
            "secret": secret,
            "response": token,
            "remoteip": remote_ip,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            body = json.loads(response.read().decode("utf-8"))
    except Exception:
        return False
    return bool(body.get("success"))


async def _verify_turnstile_if_configured(token: str | None, remote_ip: str) -> bool:
    secret = os.environ.get("VERDIFY_TURNSTILE_SECRET", "").strip()
    if not secret:
        return False
    if not token:
        raise HTTPException(status_code=400, detail="Missing contact verification token")
    verified = await asyncio.to_thread(_turnstile_verify_sync, secret, token, remote_ip)
    if not verified:
        raise HTTPException(status_code=400, detail="Contact verification failed")
    return True


def _contact_smtp_config() -> dict[str, str | int | bool | None]:
    host = _trim(os.environ.get("VERDIFY_CONTACT_SMTP_HOST"), 255)
    port = _int_env("VERDIFY_CONTACT_SMTP_PORT", 587)
    username = _trim(os.environ.get("VERDIFY_CONTACT_SMTP_USERNAME"), 255)
    password = os.environ.get("VERDIFY_CONTACT_SMTP_PASSWORD")
    use_ssl = _truthy_env("VERDIFY_CONTACT_SMTP_SSL")
    starttls = not use_ssl and os.environ.get("VERDIFY_CONTACT_SMTP_STARTTLS", "true").lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    timeout_s = _int_env("VERDIFY_CONTACT_SMTP_TIMEOUT_S", 6)
    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "ssl": use_ssl,
        "starttls": starttls,
        "timeout_s": timeout_s,
    }


def _contact_notification_message(
    *,
    submission_id: int,
    created_at,
    notify_to: str,
    name: str,
    email: str,
    topic: str,
    affiliation: str | None,
    message: str,
    user_agent: str | None,
    referrer: str | None,
) -> EmailMessage:
    from_addr = (
        _trim(os.environ.get("VERDIFY_CONTACT_NOTIFY_FROM"), 255)
        or _trim(os.environ.get("VERDIFY_CONTACT_SMTP_USERNAME"), 255)
        or "contact@verdify.ai"
    )
    from_name = _clean_email_header(os.environ.get("VERDIFY_CONTACT_NOTIFY_FROM_NAME") or "Verdify Contact")
    subject_prefix = _clean_email_header(os.environ.get("VERDIFY_CONTACT_NOTIFY_SUBJECT_PREFIX"), 80)
    if not subject_prefix:
        subject_prefix = CONTACT_NOTIFY_SUBJECT_PREFIX

    safe_name = _clean_email_header(name, 120)
    safe_topic = _clean_email_header(topic, 40)
    msg = EmailMessage()
    msg["To"] = notify_to
    msg["From"] = formataddr((from_name, from_addr))
    msg["Reply-To"] = formataddr((safe_name, email))
    msg["Subject"] = f"[{subject_prefix}] {safe_topic}: {safe_name}"
    msg["Message-ID"] = make_msgid(domain="verdify.ai")
    msg.set_content(
        "\n".join(
            [
                f"New Verdify contact submission #{submission_id}",
                "",
                f"Submitted: {created_at}",
                f"Name: {name}",
                f"Reply email: {email}",
                f"Topic: {topic}",
                f"Affiliation: {affiliation or '-'}",
                f"Referrer: {referrer or '-'}",
                f"User agent: {user_agent or '-'}",
                "",
                "Message:",
                message,
                "",
                "Review queue:",
                "docker exec verdify-timescaledb psql -U verdify -d verdify -x -c "
                "\"SELECT * FROM public_contact_submissions WHERE status = 'new' ORDER BY created_at DESC LIMIT 20;\"",
            ]
        )
    )
    return msg


def _send_contact_notification_sync(msg: EmailMessage, smtp_config: dict[str, str | int | bool | None]) -> None:
    host = smtp_config["host"]
    if not host:
        raise RuntimeError("VERDIFY_CONTACT_SMTP_HOST is not configured")

    smtp_cls = smtplib.SMTP_SSL if smtp_config["ssl"] else smtplib.SMTP
    with smtp_cls(str(host), int(smtp_config["port"]), timeout=int(smtp_config["timeout_s"])) as smtp:
        if smtp_config["starttls"]:
            smtp.starttls()
        username = smtp_config["username"]
        password = smtp_config["password"]
        if username and password:
            smtp.login(str(username), str(password))
        smtp.send_message(msg)


async def _notify_contact_submission(
    *,
    submission_id: int,
    created_at,
    notify_to: str | None,
    name: str,
    email: str,
    topic: str,
    affiliation: str | None,
    message: str,
    user_agent: str | None,
    referrer: str | None,
) -> None:
    notify_to = _trim(os.environ.get("VERDIFY_CONTACT_NOTIFY_TO"), 254) or _trim(notify_to, 254)
    smtp_config = _contact_smtp_config()
    if not notify_to or not smtp_config["host"]:
        error = (
            "VERDIFY_CONTACT_SMTP_HOST is not configured" if notify_to else "contact notify recipient is not configured"
        )
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE public_contact_submissions
                SET notification_error = $2
                WHERE id = $1
                """,
                submission_id,
                error,
            )
        return

    msg = _contact_notification_message(
        submission_id=submission_id,
        created_at=created_at,
        notify_to=notify_to,
        name=name,
        email=email,
        topic=topic,
        affiliation=affiliation,
        message=message,
        user_agent=user_agent,
        referrer=referrer,
    )
    try:
        await asyncio.to_thread(_send_contact_notification_sync, msg, smtp_config)
    except Exception as exc:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE public_contact_submissions
                SET notification_status = 'failed',
                    notification_attempted_at = now(),
                    notification_error = $2
                WHERE id = $1
                """,
                submission_id,
                str(exc)[:500],
            )
        return

    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE public_contact_submissions
            SET notification_status = 'sent',
                notification_attempted_at = now(),
                notification_error = NULL
            WHERE id = $1
            """,
            submission_id,
        )


async def require_write_access(
    request: Request,
    x_verdify_api_key: Annotated[str | None, Header(alias="X-Verdify-API-Key")] = None,
) -> None:
    """Fail closed for mutating routes unless an operator key is configured."""
    if _truthy_env(ALLOW_UNAUTHENTICATED_WRITES_ENV):
        return
    expected = os.environ.get(WRITE_API_KEY_ENV)
    if expected and x_verdify_api_key and hmac.compare_digest(expected, x_verdify_api_key):
        return
    raise HTTPException(
        status_code=403,
        detail=f"Write API disabled for unauthenticated request to {request.url.path}",
    )


def _to_float(value) -> float | None:
    return float(value) if value is not None else None


def _overall_data_health(rows: list[asyncpg.Record]) -> str:
    statuses = {str(r["status"]).lower() for r in rows}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "ok"


class PublicContactSubmission(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=254)
    message: str = Field(min_length=20, max_length=4000)
    topic: str = Field(default="other", max_length=40)
    affiliation: str | None = Field(default=None, max_length=160)
    website: str | None = Field(default=None, max_length=200)
    turnstile_token: str | None = Field(default=None, max_length=2048)


async def _parse_contact_submission(request: Request) -> tuple[PublicContactSubmission, bool]:
    content_type = (request.headers.get("Content-Type") or "").lower()
    try:
        if "application/json" in content_type:
            return PublicContactSubmission.model_validate(await request.json()), False

        body = (await request.body()).decode("utf-8")
        form_data = {
            key: values[-1] if values else ""
            for key, values in urllib.parse.parse_qs(body, keep_blank_values=True).items()
        }
        return PublicContactSubmission.model_validate(form_data), True
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail="Invalid contact submission") from exc


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
                'site_pressure_hpa','fog_burst_min','fan_burst_min','vent_bypass_min',
                'sw_fsm_controller_enabled','mist_backoff_s'
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
                alert = AlertEnvelope.model_validate(
                    {
                        "alert_type": "band_fn_null",
                        "severity": "critical",
                        "category": "system",
                        "message": (
                            "fn_band_setpoints or fn_zone_vpd_targets returned NULL — "
                            "ESP32 cannot refresh band setpoints"
                        ),
                        "details": {
                            "band_row_null": band_row is None,
                            "zone_row_null": zone_row is None,
                        },
                    }
                )
                await conn.execute(
                    "INSERT INTO alert_log (alert_type, severity, category, message, details, source) "
                    "VALUES ('band_fn_null', 'critical', 'system', $1, $2, 'api')",
                    alert.message,
                    json.dumps(alert.details),
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
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(content="\n".join(lines) + "\n")


# ── Lights (ESP32 grow light control via MQTT command) ──


@app.post("/api/v1/greenhouses/{greenhouse_id}/lights/{circuit}/{action}")
async def control_lights(
    greenhouse_id: str,
    circuit: str,
    action: str,
    _write_access: None = Depends(require_write_access),
):
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
        "docs": "/docs" if app.docs_url else None,
        "status": "/api/v1/status",
        "public_home_metrics": "/api/v1/public/home-metrics",
        "public_data_health": "/api/v1/public/data-health",
        "public_contact": "/api/v1/public/contact",
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


@app.get("/api/v1/greenhouses/{greenhouse_id}/crops", response_model=list[CropListItem])
@app.get("/api/v1/crops", response_model=list[CropListItem])  # Legacy alias (defaults to vallery)
async def list_crops(
    greenhouse_id: str = DEFAULT_GREENHOUSE,
    zone: str | None = None,
    stage: str | None = None,
    active: bool = True,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
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
    query += f" ORDER BY c.zone, c.position LIMIT ${idx} OFFSET ${idx + 1}"
    params.extend([limit, offset])

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) for r in rows]


@app.get("/api/v1/crops/{crop_id}", response_model=CropDetail)
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
async def create_crop(
    crop: CropCreate,
    greenhouse_id: str = DEFAULT_GREENHOUSE,
    _write_access: None = Depends(require_write_access),
):
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
async def update_crop(crop_id: int, crop: CropUpdate, _write_access: None = Depends(require_write_access)):
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
async def delete_crop(crop_id: int, _write_access: None = Depends(require_write_access)):
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
async def create_observation(
    crop_id: int,
    obs: ObservationCreate,
    _write_access: None = Depends(require_write_access),
):
    async with pool.acquire() as conn:
        crop = await conn.fetchrow("SELECT zone, position, zone_id, position_id FROM crops WHERE id = $1", crop_id)
        if not crop:
            raise HTTPException(404, "Crop not found")

        row = await conn.fetchrow(
            """
            INSERT INTO observations (
                crop_id, zone, position, zone_id, position_id, obs_type, notes, severity,
                observer, health_score, species, count, affected_pct, photo_path,
                plant_height_cm, leaf_count, canopy_cover_pct, flowering_count,
                fruit_count, root_condition, mortality_count, stress_tags, source
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8,
                $9, $10, $11, $12, $13, $14,
                $15, $16, $17, $18, $19, $20, $21, $22, 'api'
            )
            RETURNING *
        """,
            crop_id,
            obs.zone or crop["zone"],
            obs.position or crop["position"],
            crop["zone_id"],
            crop["position_id"],
            obs.obs_type,
            obs.notes,
            obs.severity,
            obs.observer,
            obs.health_score,
            obs.species,
            obs.count,
            obs.affected_pct,
            obs.photo_path,
            obs.plant_height_cm,
            obs.leaf_count,
            obs.canopy_cover_pct,
            obs.flowering_count,
            obs.fruit_count,
            obs.root_condition,
            obs.mortality_count,
            obs.stress_tags,
        )
    return dict(row)


@app.get("/api/v1/observations/recent", response_model=list[ObservationWithCrop])
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
async def create_event(crop_id: int, event: EventCreate, _write_access: None = Depends(require_write_access)):
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


@app.get("/api/v1/crops/{crop_id}/health", response_model=list[HealthTrendPoint])
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


@app.get("/api/v1/greenhouses/{greenhouse_id}/health", response_model=list[CropHealthSummaryItem])
@app.get("/api/v1/health/summary", response_model=list[CropHealthSummaryItem])
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


@app.get("/api/v1/zones", response_model=list[ZoneListItem])
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


@app.get("/api/v1/zones/{zone}", response_model=ZoneDetail)
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


@app.get("/api/v1/status", response_model=APIStatus)
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


@app.get("/api/v1/scorecard", response_model=ScorecardResponse)
async def planner_scorecard(scorecard_date: Annotated[date | None, Query(alias="date")] = None):
    """Planner scorecard metrics for a given date, defaulting to today."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT metric, value FROM fn_planner_scorecard(COALESCE($1::date, CURRENT_DATE)) ORDER BY metric",
            scorecard_date,
        )
    return ScorecardResponse.from_metric_rows(rows)


@app.get("/api/v1/public/data-health", response_model=PublicDataHealthResponse)
async def public_data_health():
    """Public-safe proof freshness and trust-ledger status for launch pages."""
    async with pool.acquire() as conn:
        generated_at = await conn.fetchval("SELECT now()")
        check_rows = await conn.fetch(
            """
            SELECT check_name, lower(status) AS status, metric_value, threshold_value, details
            FROM v_data_trust_ledger
            ORDER BY
              CASE lower(status) WHEN 'fail' THEN 0 WHEN 'warn' THEN 1 ELSE 2 END,
              check_name
            """
        )
        pipeline_rows = await conn.fetch(
            """
            SELECT source, rows_1h, rows_24h, age_s, null_pct_1h
            FROM v_data_pipeline_health
            ORDER BY source
            """
        )

    checks = [
        PublicDataHealthCheck(
            name=r["check_name"],
            status=r["status"],
            metric_value=_to_float(r["metric_value"]),
            threshold_value=_to_float(r["threshold_value"]),
            details=r["details"],
        )
        for r in check_rows
    ]
    pipeline_sources = [
        PublicPipelineHealthSource(
            source=r["source"],
            rows_1h=r["rows_1h"],
            rows_24h=r["rows_24h"],
            age_s=r["age_s"],
            null_pct_1h=_to_float(r["null_pct_1h"]),
        )
        for r in pipeline_rows
    ]
    return PublicDataHealthResponse(
        generated_at=generated_at,
        overall_status=_overall_data_health(check_rows),
        checks=checks,
        pipeline_sources=pipeline_sources,
    )


@app.post("/api/v1/public/contact", status_code=202)
async def public_contact_submission(request: Request):
    """Accept public project contact without publishing a personal email address."""
    payload, is_form_submission = await _parse_contact_submission(request)

    if _trim(payload.website, 200):
        if is_form_submission:
            return RedirectResponse("https://verdify.ai/contact/?sent=1", status_code=303)
        return {"ok": True, "status": "received"}

    name = _trim(payload.name, 120)
    email = _trim(payload.email, 254)
    message = _trim(payload.message, 4000)
    affiliation = _trim(payload.affiliation, 160)
    topic = (payload.topic or "other").strip().lower()

    if not name or len(name) < 2:
        raise HTTPException(status_code=422, detail="Name must be at least 2 characters")
    if not email or not CONTACT_EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="A valid reply email is required")
    if not message or len(message) < 20:
        raise HTTPException(status_code=422, detail="Message must be at least 20 characters")
    if topic not in CONTACT_ALLOWED_TOPICS:
        topic = "other"
    if len(CONTACT_URL_RE.findall(message)) > 3:
        raise HTTPException(status_code=422, detail="Message contains too many links")

    remote_ip = _client_ip(request)
    ip_hash = _contact_ip_hash(remote_ip)
    turnstile_verified = await _verify_turnstile_if_configured(payload.turnstile_token, remote_ip)
    max_per_ip_hour = _int_env("VERDIFY_CONTACT_MAX_PER_IP_HOUR", 5)
    max_per_email_day = _int_env("VERDIFY_CONTACT_MAX_PER_EMAIL_DAY", 4)

    user_agent = _trim(request.headers.get("User-Agent"), 500)
    referrer = _trim(request.headers.get("Referer"), 500)
    metadata = {
        "source": "verdify.ai/contact",
        "cf_ray": _trim(request.headers.get("CF-Ray"), 120),
        "turnstile_configured": bool(os.environ.get("VERDIFY_TURNSTILE_SECRET", "").strip()),
    }

    async with pool.acquire() as conn:
        recent_ip = await conn.fetchval(
            """
            SELECT count(*)::int
            FROM public_contact_submissions
            WHERE ip_hash = $1
              AND created_at > now() - interval '1 hour'
              AND status <> 'spam'
            """,
            ip_hash,
        )
        if recent_ip is not None and recent_ip >= max_per_ip_hour:
            raise HTTPException(status_code=429, detail="Too many contact submissions from this network")

        recent_email = await conn.fetchval(
            """
            SELECT count(*)::int
            FROM public_contact_submissions
            WHERE lower(email) = lower($1)
              AND created_at > now() - interval '1 day'
              AND status <> 'spam'
            """,
            email,
        )
        if recent_email is not None and recent_email >= max_per_email_day:
            raise HTTPException(status_code=429, detail="Too many contact submissions from this address")

        submission = await conn.fetchrow(
            """
            INSERT INTO public_contact_submissions (
              name, email, topic, affiliation, message, ip_hash,
              user_agent, referrer, turnstile_verified, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
            RETURNING id, created_at
            """,
            name,
            email,
            topic,
            affiliation,
            message,
            ip_hash,
            user_agent,
            referrer,
            turnstile_verified,
            json.dumps(metadata),
        )
        notify_to = await conn.fetchval(
            "SELECT owner_email FROM greenhouses WHERE id = $1",
            DEFAULT_GREENHOUSE,
        )

    await _notify_contact_submission(
        submission_id=submission["id"],
        created_at=submission["created_at"],
        notify_to=notify_to,
        name=name,
        email=email,
        topic=topic,
        affiliation=affiliation,
        message=message,
        user_agent=user_agent,
        referrer=referrer,
    )

    if is_form_submission:
        return RedirectResponse("https://verdify.ai/contact/?sent=1", status_code=303)
    return {"ok": True, "status": "received"}


@app.post("/api/v1/admin/contact-notifications/retry")
async def retry_contact_notifications(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    _write_access: None = Depends(require_write_access),
):
    """Retry email notifications for queued contact submissions."""
    async with pool.acquire() as conn:
        notify_to = await conn.fetchval(
            "SELECT owner_email FROM greenhouses WHERE id = $1",
            DEFAULT_GREENHOUSE,
        )
        rows = await conn.fetch(
            """
            SELECT id, created_at, name, email, topic, affiliation, message, user_agent, referrer
            FROM public_contact_submissions
            WHERE notification_status IN ('pending', 'failed')
              AND status <> 'spam'
            ORDER BY created_at
            LIMIT $1
            """,
            limit,
        )

    results = []
    for row in rows:
        await _notify_contact_submission(
            submission_id=row["id"],
            created_at=row["created_at"],
            notify_to=notify_to,
            name=row["name"],
            email=row["email"],
            topic=row["topic"],
            affiliation=row["affiliation"],
            message=row["message"],
            user_agent=row["user_agent"],
            referrer=row["referrer"],
        )
        async with pool.acquire() as conn:
            updated = await conn.fetchrow(
                """
                SELECT id, notification_status, notification_error
                FROM public_contact_submissions
                WHERE id = $1
                """,
                row["id"],
            )
        results.append(dict(updated))

    return {"ok": True, "attempted": len(results), "results": results}


@app.get("/api/v1/public/home-metrics", response_model=PublicHomeMetrics)
async def public_home_metrics(greenhouse_id: str = DEFAULT_GREENHOUSE):
    """Launch-safe live metrics for verdify.ai proof cards."""
    async with pool.acquire() as conn:
        generated_at = await conn.fetchval("SELECT now()")
        climate_summary = await conn.fetchrow(
            """
            SELECT count(*)::int AS climate_rows,
                   COALESCE(
                     round((extract(epoch FROM max(ts) - min(ts)) / 86400.0)::numeric, 1),
                     0
                   )::float AS climate_days
            FROM climate
            WHERE greenhouse_id = $1
            """,
            greenhouse_id,
        )
        latest_climate = await conn.fetchrow(
            """
            SELECT ts,
                   extract(epoch FROM now() - ts)::int AS age_s,
                   round(temp_avg::numeric, 1)::float AS indoor_temp_f,
                   round(vpd_avg::numeric, 2)::float AS indoor_vpd_kpa,
                   round(outdoor_temp_f::numeric, 1)::float AS outdoor_temp_f,
                   round(outdoor_rh_pct::numeric, 1)::float AS outdoor_rh_pct
            FROM climate
            WHERE greenhouse_id = $1
            ORDER BY ts DESC
            LIMIT 1
            """,
            greenhouse_id,
        )
        active_crops = await conn.fetchval(
            "SELECT count(*)::int FROM crops WHERE greenhouse_id = $1 AND is_active",
            greenhouse_id,
        )
        plan_count = await conn.fetchval(
            """
            SELECT count(*)::int
            FROM plan_journal
            WHERE greenhouse_id = $1
              AND plan_id LIKE 'iris-%'
              AND plan_id NOT LIKE 'iris-reactive%'
              AND plan_id NOT LIKE 'iris-fix%'
            """,
            greenhouse_id,
        )
        lesson_count = await conn.fetchval(
            "SELECT count(*)::int FROM planner_lessons WHERE greenhouse_id = $1 AND is_active",
            greenhouse_id,
        )
        last_plan = await conn.fetchrow(
            """
            SELECT plan_id, created_at, extract(epoch FROM now() - created_at)::int AS age_s
            FROM plan_journal
            WHERE greenhouse_id = $1
              AND plan_id LIKE 'iris-%'
              AND plan_id NOT LIKE 'iris-reactive%'
              AND plan_id NOT LIKE 'iris-fix%'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            greenhouse_id,
        )
        score_rows = await conn.fetch(
            "SELECT metric, value FROM fn_planner_scorecard((now() AT TIME ZONE 'America/Denver')::date)"
        )
        scorecard = {r["metric"]: _to_float(r["value"]) for r in score_rows}
        open_critical_high = await conn.fetchval(
            """
            SELECT count(*)::int
            FROM alert_log
            WHERE greenhouse_id = $1
              AND disposition = 'open'
              AND severity IN ('critical', 'high')
            """,
            greenhouse_id,
        )
        data_checks = await conn.fetch(
            """
            SELECT check_name, lower(status) AS status, metric_value, threshold_value, details
            FROM v_data_trust_ledger
            ORDER BY
              CASE lower(status) WHEN 'fail' THEN 0 WHEN 'warn' THEN 1 ELSE 2 END,
              check_name
            """
        )

    warning_checks = [
        PublicDataHealthCheck(
            name=r["check_name"],
            status=r["status"],
            metric_value=_to_float(r["metric_value"]),
            threshold_value=_to_float(r["threshold_value"]),
            details=r["details"],
        )
        for r in data_checks
        if r["status"] != "ok"
    ]
    return PublicHomeMetrics(
        generated_at=generated_at,
        greenhouse_id=greenhouse_id,
        climate_rows=climate_summary["climate_rows"] if climate_summary else 0,
        climate_days=climate_summary["climate_days"] if climate_summary else 0,
        active_crops=active_crops or 0,
        plan_count=plan_count or 0,
        lesson_count=lesson_count or 0,
        latest_climate_ts=latest_climate["ts"] if latest_climate else None,
        latest_climate_age_s=latest_climate["age_s"] if latest_climate else None,
        indoor_temp_f=latest_climate["indoor_temp_f"] if latest_climate else None,
        indoor_vpd_kpa=latest_climate["indoor_vpd_kpa"] if latest_climate else None,
        outdoor_temp_f=latest_climate["outdoor_temp_f"] if latest_climate else None,
        outdoor_rh_pct=latest_climate["outdoor_rh_pct"] if latest_climate else None,
        last_plan_id=last_plan["plan_id"] if last_plan else None,
        last_plan_created_at=last_plan["created_at"] if last_plan else None,
        last_plan_age_s=last_plan["age_s"] if last_plan else None,
        planner_score_today=scorecard.get("planner_score"),
        compliance_pct_today=scorecard.get("compliance_pct"),
        cost_today_usd=scorecard.get("cost_total"),
        water_today_gal=scorecard.get("water_used_gal"),
        open_critical_high_alerts=open_critical_high or 0,
        data_health_status=_overall_data_health(data_checks),
        data_health_warnings=warning_checks[:8],
    )


# ═══════════════════════════════════════════════════════════════════════
# Sprint 23 — Topology + crop-history endpoints
# ═══════════════════════════════════════════════════════════════════════
#
# These endpoints consume the Sprint 22 topology tables and the Sprint 23
# history views (v_position_current, v_crop_history, v_crop_lifecycle).
# The legacy zone:str / position:str-based endpoints above remain in place
# until callers migrate; Phase 4d drops them.


# ── Topology tree (website nav, full-system debug) ────────────────────


@app.get("/api/v1/topology")
async def get_topology(greenhouse_id: str = DEFAULT_GREENHOUSE):
    """Full greenhouse → zone → shelf → position tree as JSONB."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT greenhouse_id, greenhouse_name, zones FROM v_topology_tree WHERE greenhouse_id = $1",
            greenhouse_id,
        )
        if row is None:
            raise HTTPException(404, f"Greenhouse '{greenhouse_id}' not found")
    return _coerce_jsonb(dict(row), "zones")


# ── Zone full detail ──────────────────────────────────────────────────


@app.get("/api/v1/zones/{zone_slug}/full")
async def get_zone_full(zone_slug: str, greenhouse_id: str = DEFAULT_GREENHOUSE):
    """Zone detail: shelves[], sensors[], equipment[], water_systems[] (from v_zone_full)."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM v_zone_full
            WHERE greenhouse_id = $1 AND zone_slug = $2
            """,
            greenhouse_id,
            zone_slug,
        )
        if row is None:
            raise HTTPException(404, f"Zone '{zone_slug}' not found in '{greenhouse_id}'")
    return _coerce_jsonb(dict(row), "shelves", "sensors", "equipment", "water_systems")


# ── Positions (current state + history) ───────────────────────────────


@app.get("/api/v1/positions", response_model=list[PositionCurrentEntry])
async def list_positions(
    zone_slug: str | None = None,
    occupied_only: bool = False,
    greenhouse_id: str = DEFAULT_GREENHOUSE,
):
    """Every active position + current crop (if any). Empty slots included unless occupied_only=true."""
    sql = "SELECT * FROM v_position_current WHERE greenhouse_id = $1"
    params: list = [greenhouse_id]
    if zone_slug is not None:
        sql += " AND zone_slug = $2"
        params.append(zone_slug)
    if occupied_only:
        sql += " AND is_occupied"
    sql += " ORDER BY zone_slug, shelf_slug, position_label"
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return [PositionCurrentEntry.model_validate(dict(r)) for r in rows]


@app.get("/api/v1/positions/{position_id}")
async def get_position(position_id: int, greenhouse_id: str = DEFAULT_GREENHOUSE):
    """Position detail: current occupancy + full crop history at this slot."""
    async with pool.acquire() as conn:
        current = await conn.fetchrow(
            "SELECT * FROM v_position_current WHERE position_id = $1 AND greenhouse_id = $2",
            position_id,
            greenhouse_id,
        )
        if current is None:
            raise HTTPException(404, f"Position {position_id} not found")
        history_rows = await conn.fetch(
            "SELECT * FROM v_crop_history WHERE position_id = $1 AND greenhouse_id = $2 ORDER BY planted_date DESC",
            position_id,
            greenhouse_id,
        )
    return {
        "current": dict(current),
        "history": [CropHistoryEntry.model_validate(dict(r)).model_dump() for r in history_rows],
    }


@app.post("/api/v1/positions/{position_id}/plant", status_code=201)
async def plant_at_position(
    position_id: int,
    body: CropCreate,
    greenhouse_id: str = DEFAULT_GREENHOUSE,
    _write_access: None = Depends(require_write_access),
):
    """Create a new crop at a specific position. Validates slot is unoccupied.

    The unique-active-per-position partial index (migration 088) prevents
    double-booking; a collision raises a 409.
    """
    async with pool.acquire() as conn:
        pos = await conn.fetchrow(
            """
            SELECT p.id AS position_id, p.label, sh.zone_id, z.slug AS zone_slug
            FROM positions p JOIN shelves sh ON sh.id = p.shelf_id JOIN zones z ON z.id = sh.zone_id
            WHERE p.id = $1 AND p.greenhouse_id = $2
            """,
            position_id,
            greenhouse_id,
        )
        if pos is None:
            raise HTTPException(404, f"Position {position_id} not found")
        # Resolve crop_catalog_id via slug / name
        catalog_id = None
        if body.crop_catalog_slug:
            catalog_id = await conn.fetchval("SELECT id FROM crop_catalog WHERE slug = $1", body.crop_catalog_slug)
        if catalog_id is None:
            catalog_id = await conn.fetchval(
                "SELECT id FROM crop_catalog WHERE lower(common_name) = lower($1) OR slug = lower($1)",
                body.name,
            )
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO crops (
                    name, variety, position, zone, planted_date, expected_harvest, stage,
                    count, seed_lot_id, supplier, base_temp_f, target_dli, target_vpd_low,
                    target_vpd_high, notes, greenhouse_id,
                    position_id, zone_id, crop_catalog_id
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16,
                        $17, $18, $19)
                RETURNING *
                """,
                body.name,
                body.variety,
                pos["label"],
                pos["zone_slug"],
                body.planted_date,
                body.expected_harvest,
                body.stage,
                body.count,
                body.seed_lot_id,
                body.supplier,
                body.base_temp_f,
                body.target_dli,
                body.target_vpd_low,
                body.target_vpd_high,
                body.notes,
                greenhouse_id,
                position_id,
                pos["zone_id"],
                catalog_id,
            )
        except asyncpg.exceptions.UniqueViolationError:
            raise HTTPException(409, f"Position {position_id} ({pos['label']}) is already occupied by an active crop")
    return dict(row)


# ── Crop lifecycle (clear, transplant, harvest) + full timeline ───────


@app.get("/api/v1/crops/{crop_id}/lifecycle", response_model=CropLifecycle)
async def get_crop_lifecycle(crop_id: int, greenhouse_id: str = DEFAULT_GREENHOUSE):
    """Full crop timeline: events array, harvest totals, observations summary."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM v_crop_lifecycle WHERE crop_id = $1 AND greenhouse_id = $2",
            crop_id,
            greenhouse_id,
        )
        if row is None:
            raise HTTPException(404, f"Crop {crop_id} not found")
    return CropLifecycle.model_validate(_coerce_jsonb(dict(row), "events"))


@app.post("/api/v1/crops/{crop_id}/clear")
async def clear_crop(
    crop_id: int,
    operator: str | None = None,
    _write_access: None = Depends(require_write_access),
):
    """Mark a crop as inactive (cleared/removed). Trigger auto-sets cleared_at
    and logs a 'removed' crop_events row."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE crops SET is_active = FALSE WHERE id = $1 AND is_active RETURNING id, cleared_at",
            crop_id,
        )
        if row is None:
            raise HTTPException(404, f"Crop {crop_id} not found or already cleared")
        if operator:
            await conn.execute(
                "UPDATE crop_events SET operator = $1 WHERE crop_id = $2 AND event_type = 'removed' AND operator IS NULL",
                operator,
                crop_id,
            )
    return {"crop_id": crop_id, "is_active": False, "cleared_at": row["cleared_at"]}


class TransplantBody(BaseModel):
    new_position_id: int
    operator: str | None = None
    notes: str | None = None


@app.post("/api/v1/crops/{crop_id}/transplant")
async def transplant_crop(
    crop_id: int,
    body: TransplantBody,
    greenhouse_id: str = DEFAULT_GREENHOUSE,
    _write_access: None = Depends(require_write_access),
):
    """Move a crop to a new position. Logs a 'transplanted' event with old/new position_ids."""
    async with pool.acquire() as conn:
        crop = await conn.fetchrow(
            "SELECT id, position_id, stage, greenhouse_id FROM crops WHERE id = $1 AND is_active",
            crop_id,
        )
        if crop is None:
            raise HTTPException(404, f"Active crop {crop_id} not found")
        target = await conn.fetchrow(
            "SELECT p.id, p.label, sh.zone_id FROM positions p JOIN shelves sh ON sh.id = p.shelf_id WHERE p.id = $1 AND p.greenhouse_id = $2",
            body.new_position_id,
            greenhouse_id,
        )
        if target is None:
            raise HTTPException(404, f"Target position {body.new_position_id} not found")
        try:
            await conn.execute(
                "UPDATE crops SET position_id = $1, zone_id = $2, position = $3 WHERE id = $4",
                body.new_position_id,
                target["zone_id"],
                target["label"],
                crop_id,
            )
        except asyncpg.exceptions.UniqueViolationError:
            raise HTTPException(409, f"Target position {body.new_position_id} is occupied")
        await conn.execute(
            """
            INSERT INTO crop_events (ts, crop_id, event_type, source, operator, notes, greenhouse_id, position_id)
            VALUES (now(), $1, 'transplanted', 'api', $2, $3, $4, $5)
            """,
            crop_id,
            body.operator,
            body.notes or f"Transplanted to position {body.new_position_id}",
            crop["greenhouse_id"],
            body.new_position_id,
        )
    return {"crop_id": crop_id, "new_position_id": body.new_position_id, "new_position_label": target["label"]}


class HarvestBody(BaseModel):
    weight_kg: float | None = None
    unit_count: int | None = None
    quality_grade: str | None = None
    salable_weight_kg: float | None = None
    cull_weight_kg: float | None = None
    cull_reason: str | None = None
    quality_reason: str | None = None
    unit_price: float | None = None
    revenue: float | None = None
    destination: str | None = None
    labor_minutes: int | None = None
    advance_stage: str | None = None  # optional: also update crops.stage
    operator: str | None = None
    notes: str | None = None


@app.post("/api/v1/crops/{crop_id}/harvest", status_code=201)
async def harvest_crop(
    crop_id: int,
    body: HarvestBody,
    greenhouse_id: str = DEFAULT_GREENHOUSE,
    _write_access: None = Depends(require_write_access),
):
    """Record a harvest against this crop. Optionally advance stage."""
    async with pool.acquire() as conn:
        crop = await conn.fetchrow(
            "SELECT id, position_id, zone, stage FROM crops WHERE id = $1 AND greenhouse_id = $2",
            crop_id,
            greenhouse_id,
        )
        if crop is None:
            raise HTTPException(404, f"Crop {crop_id} not found")
        row = await conn.fetchrow(
            """
            INSERT INTO harvests (
                ts, crop_id, weight_kg, unit_count, quality_grade,
                salable_weight_kg, cull_weight_kg, cull_reason, quality_reason,
                unit_price, revenue, destination, labor_minutes,
                zone, operator, notes, greenhouse_id, position_id
            )
            VALUES (now(), $1, $2, $3, $4, $5, $6, $7, $8, $9,
                    $10, $11, $12, $13, $14, $15, $16, $17)
            RETURNING *
            """,
            crop_id,
            body.weight_kg,
            body.unit_count,
            body.quality_grade,
            body.salable_weight_kg,
            body.cull_weight_kg,
            body.cull_reason,
            body.quality_reason,
            body.unit_price,
            body.revenue,
            body.destination,
            body.labor_minutes,
            crop["zone"],
            body.operator,
            body.notes,
            greenhouse_id,
            crop["position_id"],
        )
        if body.advance_stage and body.advance_stage != crop["stage"]:
            await conn.execute("UPDATE crops SET stage = $1 WHERE id = $2", body.advance_stage, crop_id)
    return dict(row)


# ── Crop catalog ──────────────────────────────────────────────────────


@app.get("/api/v1/crop-catalog")
async def list_crop_catalog():
    """All crop types in the catalog (with aggregated stage/season profiles)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM v_crop_catalog_with_profiles ORDER BY slug")
    return [_coerce_jsonb(dict(r), "stage_season_profiles") for r in rows]


@app.get("/api/v1/crop-catalog/{slug}")
async def get_crop_catalog_entry(slug: str):
    """Single catalog entry + hourly profile detail."""
    async with pool.acquire() as conn:
        entry = await conn.fetchrow("SELECT * FROM v_crop_catalog_with_profiles WHERE slug = $1", slug)
        if entry is None:
            raise HTTPException(404, f"Crop catalog entry '{slug}' not found")
        hours = await conn.fetch(
            """
            SELECT * FROM crop_target_profiles
            WHERE crop_catalog_id = (SELECT id FROM crop_catalog WHERE slug = $1)
            ORDER BY growth_stage, season, hour_of_day
            """,
            slug,
        )
    return {"entry": _coerce_jsonb(dict(entry), "stage_season_profiles"), "hourly_profiles": [dict(h) for h in hours]}


# ── Equipment, switches, sensors (read-only for now) ──────────────────


@app.get("/api/v1/equipment")
async def list_equipment(zone_slug: str | None = None, greenhouse_id: str = DEFAULT_GREENHOUSE):
    sql = """
        SELECT e.*, z.slug AS zone_slug
        FROM equipment e LEFT JOIN zones z ON z.id = e.zone_id
        WHERE e.greenhouse_id = $1 AND e.is_active
    """
    params: list = [greenhouse_id]
    if zone_slug is not None:
        sql += " AND z.slug = $2"
        params.append(zone_slug)
    sql += " ORDER BY e.kind, e.slug"
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return [_coerce_jsonb(dict(r), "specs") for r in rows]


@app.get("/api/v1/switches")
async def list_switches(greenhouse_id: str = DEFAULT_GREENHOUSE):
    """Full relay map — v_equipment_relay_map."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM v_equipment_relay_map WHERE greenhouse_id = $1 ORDER BY board, pin",
            greenhouse_id,
        )
    return [dict(r) for r in rows]


@app.get("/api/v1/sensors")
async def list_sensors(zone_slug: str | None = None, greenhouse_id: str = DEFAULT_GREENHOUSE):
    sql = """
        SELECT s.*, z.slug AS zone_slug
        FROM sensors s LEFT JOIN zones z ON z.id = s.zone_id
        WHERE s.greenhouse_id = $1 AND s.is_active
    """
    params: list = [greenhouse_id]
    if zone_slug is not None:
        sql += " AND z.slug = $2"
        params.append(zone_slug)
    sql += " ORDER BY s.kind, s.slug"
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]


@app.get("/api/v1/pressure-groups/status")
async def pressure_group_status(greenhouse_id: str = DEFAULT_GREENHOUSE):
    """Current mister/drip activity per pressure group (v_pressure_group_status)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM v_pressure_group_status WHERE greenhouse_id = $1 ORDER BY group_slug",
            greenhouse_id,
        )
    return [_coerce_jsonb(dict(r), "systems") for r in rows]
