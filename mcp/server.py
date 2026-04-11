#!/usr/bin/env /srv/greenhouse/.venv/bin/python3
"""
Verdify MCP Server — Greenhouse control tools for Agent Iris.

Gives Iris direct access to greenhouse data, planner control,
and setpoint management through the standard MCP protocol.

Run: python mcp/server.py
Transport: streamable-http on port 8400
"""

import json
import os
import subprocess
from datetime import date, datetime
from pathlib import Path

import asyncpg

from mcp.server.fastmcp import FastMCP

# ── Config ──
# Read DB password from .env
_env_path = Path("/srv/verdify/.env")
_db_pass = "verdify"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if line.startswith("POSTGRES_PASSWORD="):
            _db_pass = line.split("=", 1)[1].strip().strip('"').strip("'")
DB_DSN = os.environ.get("DB_DSN", f"postgresql://verdify:{_db_pass}@localhost:5432/verdify")
PLANNER_SCRIPT = "/srv/verdify/scripts/planner.py"
PYTHON = "/srv/greenhouse/.venv/bin/python3"


def _json(obj):
    """JSON serialize with asyncpg/Decimal support."""
    import decimal

    def default(o):
        if isinstance(o, decimal.Decimal):
            return float(o)
        if isinstance(o, datetime | date):
            return o.isoformat()
        return str(o)

    return json.dumps(obj, default=default)


mcp = FastMCP(
    "verdify",
    instructions="""Verdify greenhouse control tools. Use these to monitor climate,
    manage setpoints, run the AI planner, and review performance.
    The greenhouse has temp/VPD bands, misters, fog, fans, heaters, and a vent.
    The planner sets 24 Tier 1 tunables that shape how the controller responds.""",
)


async def _db() -> asyncpg.Connection:
    return await asyncpg.connect(DB_DSN)


# ═══════════════════════════════════════════════════════════════
# MONITORING TOOLS
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
async def climate() -> str:
    """Get current greenhouse climate readings (temp, VPD, RH, dew point, zone sensors, outdoor)."""
    conn = await _db()
    try:
        row = await conn.fetchrow("""
            SELECT round(temp_avg::numeric,1) as temp_f,
                   round(vpd_avg::numeric,2) as vpd_kpa,
                   round(rh_avg::numeric,0) as rh_pct,
                   round(dew_point::numeric,1) as dew_point_f,
                   round((temp_avg - dew_point)::numeric,1) as dp_margin_f,
                   round(vpd_south::numeric,2) as vpd_south,
                   round(vpd_west::numeric,2) as vpd_west,
                   round(vpd_east::numeric,2) as vpd_east,
                   round(outdoor_temp_f::numeric,1) as outdoor_temp,
                   round(outdoor_rh_pct::numeric,0) as outdoor_rh,
                   round(lux::numeric,0) as lux,
                   round(solar_irradiance_w_m2::numeric,0) as solar_w,
                   extract(epoch FROM now() - ts)::int as age_seconds
            FROM climate ORDER BY ts DESC LIMIT 1
        """)
        mode = await conn.fetchval(
            "SELECT value FROM system_state WHERE entity = 'greenhouse_state' ORDER BY ts DESC LIMIT 1"
        )
        return _json({**dict(row), "mode": mode})
    finally:
        await conn.close()


@mcp.tool()
async def scorecard(target_date: str = "") -> str:
    """Get the planner scorecard (score, compliance, stress hours, cost, dew point risk).
    Pass date as YYYY-MM-DD or omit for today."""
    conn = await _db()
    try:
        d = target_date or str(date.today())
        rows = await conn.fetch("SELECT * FROM fn_planner_scorecard($1::date)", datetime.strptime(d, "%Y-%m-%d").date())
        return json.dumps({r["metric"]: r["value"] for r in rows})
    finally:
        await conn.close()


@mcp.tool()
async def equipment_state() -> str:
    """Get current state of all greenhouse equipment (relays, misters, heaters, fans, vent)."""
    conn = await _db()
    try:
        rows = await conn.fetch("""
            SELECT equipment, state, to_char(ts AT TIME ZONE 'America/Denver', 'HH24:MI:SS') as since
            FROM (SELECT DISTINCT ON (equipment) equipment, state, ts
                  FROM equipment_state ORDER BY equipment, ts DESC) sub
            WHERE equipment IN ('fan1','fan2','vent','fog','heat1','heat2',
                'mister_south','mister_west','mister_center')
            ORDER BY equipment
        """)
        return _json([dict(r) for r in rows])
    finally:
        await conn.close()


@mcp.tool()
async def forecast(hours: int = 72) -> str:
    """Get weather forecast summary for the next N hours (default 72).
    Returns hourly temp, RH, VPD, cloud cover, solar radiation."""
    conn = await _db()
    try:
        rows = await conn.fetch(f"""
            SELECT to_char(ts AT TIME ZONE 'America/Denver', 'Dy HH24:MI') as time,
                   round(temp_f::numeric,0) as temp, round(rh_pct::numeric,0) as rh,
                   round(vpd_kpa::numeric,2) as vpd, round(cloud_cover_pct::numeric,0) as cloud,
                   round(GREATEST(COALESCE(direct_radiation_w_m2,0),0)::numeric,0) as solar
            FROM weather_forecast
            WHERE ts > now() AND ts < now() + interval '{hours} hours'
            ORDER BY ts, fetched_at DESC
            LIMIT {hours}
        """)
        return _json([dict(r) for r in rows])
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════════════════
# SETPOINT TOOLS
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
async def get_setpoints() -> str:
    """Get all current active setpoints (band values + planner tunables)."""
    conn = await _db()
    try:
        rows = await conn.fetch("""
            SELECT parameter, round(value::numeric,3) as value, source,
                   to_char(ts AT TIME ZONE 'America/Denver', 'HH24:MI') as updated
            FROM (SELECT DISTINCT ON (parameter) parameter, value, source, ts
                  FROM setpoint_changes ORDER BY parameter, ts DESC) sub
            WHERE parameter IN (
                'temp_high','temp_low','vpd_high','vpd_low',
                'bias_cool','bias_heat','vpd_hysteresis',
                'mister_engage_kpa','mister_all_kpa',
                'mister_pulse_on_s','mister_pulse_gap_s','mister_vpd_weight',
                'mister_water_budget_gal','mister_engage_delay_s','mister_all_delay_s',
                'mist_max_closed_vent_s','mist_thermal_relief_s','mist_vent_close_lead_s',
                'vpd_watch_dwell_s','fog_escalation_kpa',
                'd_cool_stage_2','min_heat_on_s','min_heat_off_s',
                'enthalpy_open','enthalpy_close'
            ) ORDER BY parameter
        """)
        return _json([dict(r) for r in rows])
    finally:
        await conn.close()


@mcp.tool()
async def set_tunable(parameter: str, value: float, reason: str = "iris-manual") -> str:
    """Push a single Tier 1 tunable to the ESP32 immediately.
    The dispatcher will apply it within 5 minutes.
    Example: set_tunable('fog_escalation_kpa', 0.15, 'fog is 7x more effective than misters')"""
    TIER1 = {
        "vpd_hysteresis",
        "vpd_watch_dwell_s",
        "mister_engage_kpa",
        "mister_all_kpa",
        "mister_pulse_on_s",
        "mister_pulse_gap_s",
        "mister_vpd_weight",
        "mister_water_budget_gal",
        "mist_vent_close_lead_s",
        "mist_max_closed_vent_s",
        "mist_vent_reopen_delay_s",
        "mist_thermal_relief_s",
        "enthalpy_open",
        "enthalpy_close",
        "min_vent_on_s",
        "min_vent_off_s",
        "min_fog_on_s",
        "min_fog_off_s",
        "fog_escalation_kpa",
        "d_cool_stage_2",
        "bias_heat",
        "bias_cool",
        "min_heat_on_s",
        "min_heat_off_s",
        "mister_engage_delay_s",
        "mister_all_delay_s",
    }
    if parameter not in TIER1:
        return json.dumps({"error": f"'{parameter}' is not a Tier 1 tunable", "allowed": sorted(TIER1)})

    conn = await _db()
    try:
        await conn.execute(
            "INSERT INTO setpoint_changes (ts, parameter, value, source) VALUES (now(), $1, $2, $3)",
            parameter,
            value,
            "iris",
        )
        return json.dumps(
            {
                "ok": True,
                "parameter": parameter,
                "value": value,
                "reason": reason,
                "note": "Dispatcher will push to ESP32 within 5 minutes",
            }
        )
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════════════════
# PLANNER TOOLS
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
async def plan_run(mode: str = "normal") -> str:
    """Trigger a planning cycle. Mode: 'normal' or 'dry-run'.
    Returns plan summary (plan_id, transitions, hypothesis).
    Takes ~2-3 minutes for a full cycle."""
    args = [PYTHON, PLANNER_SCRIPT]
    if mode == "dry-run":
        args.append("--dry-run")

    result = subprocess.run(args, capture_output=True, text=True, timeout=300)

    if mode == "dry-run":
        # Dry run outputs the prompt to stdout
        return json.dumps(
            {"mode": "dry-run", "prompt_length": len(result.stdout), "prompt_preview": result.stdout[:500]}
        )

    # Parse the log for plan summary
    lines = result.stderr.strip().split("\n") if result.stderr else []
    summary = [line for line in lines if "Plan iris-" in line or "DB writes" in line or "ERROR" in line]
    return json.dumps(
        {"mode": mode, "exit_code": result.returncode, "summary": summary, "stderr_tail": lines[-5:] if lines else []}
    )


@mcp.tool()
async def plan_status() -> str:
    """Get the current active plan — waypoints, plan_id, hypothesis, compliance."""
    conn = await _db()
    try:
        journal = await conn.fetchrow("""
            SELECT plan_id, to_char(created_at AT TIME ZONE 'America/Denver', 'MM-DD HH24:MI') as created,
                   hypothesis, experiment, expected_outcome
            FROM plan_journal WHERE plan_id NOT LIKE 'iris-reactive%'
            ORDER BY created_at DESC LIMIT 1
        """)
        waypoints = await conn.fetch("""
            SELECT to_char(ts AT TIME ZONE 'America/Denver', 'Dy HH24:MI') as time, count(*) as params
            FROM setpoint_plan WHERE is_active = true AND ts > now()
            GROUP BY ts ORDER BY ts LIMIT 15
        """)
        return json.dumps(
            {"plan": dict(journal) if journal else None, "future_waypoints": [dict(w) for w in waypoints]}, default=str
        )
    finally:
        await conn.close()


@mcp.tool()
async def lessons() -> str:
    """Get active planner lessons (accumulated operational knowledge)."""
    conn = await _db()
    try:
        rows = await conn.fetch("""
            SELECT category, condition, lesson, confidence, times_validated
            FROM planner_lessons WHERE is_active = true AND superseded_by IS NULL
            ORDER BY CASE confidence WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                     times_validated DESC
            LIMIT 10
        """)
        return _json([dict(r) for r in rows])
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════════════════
# DATA QUERY TOOL
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
async def query(sql: str) -> str:
    """Run a read-only SQL query against the Verdify database.
    Returns up to 100 rows as JSON. Only SELECT queries allowed."""
    sql_stripped = sql.strip().upper()
    if not sql_stripped.startswith("SELECT"):
        return json.dumps({"error": "Only SELECT queries are allowed"})

    conn = await _db()
    try:
        rows = await conn.fetch(sql)
        return _json([dict(r) for r in rows[:100]])
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    os.environ.setdefault("MCP_HTTP_HOST", "127.0.0.1")
    os.environ.setdefault("MCP_HTTP_PORT", "8400")
    mcp.run(transport="streamable-http")
