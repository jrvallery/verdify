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
# Legacy planner.py removed — planning now runs via iris_planner.py → OpenClaw hooks


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
    """Get the planner scorecard — 25 KPI metrics for a given day.
    Includes: planner_score, compliance_pct (both in band), temp_compliance_pct,
    vpd_compliance_pct, stress hours (heat/cold/vpd_high/vpd_low), utility usage
    (kwh, therms, water_gal, mister_water_gal), costs (electric/gas/water/total),
    dew point safety, and 7-day averages. Pass date as YYYY-MM-DD or omit for today."""
    conn = await _db()
    try:
        if target_date:
            d = datetime.strptime(target_date, "%Y-%m-%d").date()
        else:
            d = await conn.fetchval("SELECT (now() AT TIME ZONE 'America/Denver')::date")
        rows = await conn.fetch("SELECT * FROM fn_planner_scorecard($1::date)", d)
        return _json({r["metric"]: r["value"] for r in rows})
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
            FROM (
                SELECT DISTINCT ON (ts) ts, temp_f, rh_pct, vpd_kpa, cloud_cover_pct,
                       direct_radiation_w_m2
                FROM weather_forecast
                WHERE ts > now() AND ts < now() + interval '{hours} hours'
                ORDER BY ts, fetched_at DESC
            ) sub
            ORDER BY ts
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
                'mist_vent_reopen_delay_s',
                'vpd_watch_dwell_s','fog_escalation_kpa',
                'min_fog_on_s','min_fog_off_s',
                'min_vent_on_s','min_vent_off_s',
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
    """Trigger an ad-hoc planning cycle by sending a SUNRISE event to the Iris planner agent.
    Iris will gather context, analyze conditions, write a plan via set_plan(), and post to #greenhouse.
    This uses the same event-driven path as scheduled sunrise/sunset events."""
    import sys

    sys.path.insert(0, "/srv/verdify/ingestor")
    try:
        from iris_planner import gather_context, send_to_iris

        context = gather_context()
        ok = send_to_iris("SUNRISE", "Ad-hoc planning cycle (triggered via MCP)", context=context)
        return json.dumps({"ok": ok, "note": "SUNRISE event sent to Iris planner. Check #greenhouse for the brief."})
    except Exception as e:
        return json.dumps({"error": str(e)})


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
# PLANNING TOOLS
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
async def set_plan(
    plan_id: str, hypothesis: str, transitions: str, experiment: str = "", expected_outcome: str = ""
) -> str:
    """Write a 72-hour setpoint plan with multiple time-based waypoints.
    Deactivates all existing future waypoints, writes new ones, and logs a plan journal entry.
    The dispatcher executes these on schedule — the greenhouse follows the plan even if the planner goes offline.

    plan_id: unique ID like 'iris-YYYYMMDD-HHMM'
    hypothesis: what you expect this plan to achieve
    transitions: JSON array of objects: [{"ts": "ISO8601-with-TZ", "params": {"param": value, ...}, "reason": "..."}]
    experiment: optional one-line experiment description
    expected_outcome: optional measurable prediction"""
    try:
        waypoints = json.loads(transitions)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON in transitions: {e}"})

    if not waypoints or not isinstance(waypoints, list):
        return json.dumps({"error": "transitions must be a non-empty JSON array"})

    conn = await _db()
    try:
        # Deactivate existing future waypoints
        await conn.execute("UPDATE setpoint_plan SET is_active = false WHERE ts > now() AND is_active = true")

        # Write new waypoints
        rows_written = 0
        for wp in waypoints:
            ts_str = wp.get("ts")
            params = wp.get("params", {})
            reason = wp.get("reason", "")
            if not ts_str or not params:
                continue
            # Parse ISO timestamp string to datetime for asyncpg
            ts = datetime.fromisoformat(ts_str)
            for param, value in params.items():
                await conn.execute(
                    """INSERT INTO setpoint_plan (ts, parameter, value, plan_id, source, reason, created_at, is_active, greenhouse_id)
                       VALUES ($1, $2, $3, $4, 'iris', $5, now(), true, 'vallery')""",
                    ts,
                    param,
                    float(value),
                    plan_id,
                    reason,
                )
                rows_written += 1

        # Write journal entry
        await conn.execute(
            """INSERT INTO plan_journal (plan_id, created_at, hypothesis, experiment, expected_outcome, greenhouse_id)
               VALUES ($1, now(), $2, $3, $4, 'vallery')""",
            plan_id,
            hypothesis,
            experiment or None,
            expected_outcome or None,
        )

        return json.dumps(
            {
                "ok": True,
                "plan_id": plan_id,
                "transitions": len(waypoints),
                "rows_written": rows_written,
                "note": "Dispatcher will execute waypoints on schedule. Old future waypoints deactivated.",
            }
        )
    finally:
        await conn.close()


@mcp.tool()
async def plan_evaluate(plan_id: str, outcome_score: int, actual_outcome: str, lesson_extracted: str = "") -> str:
    """Write the evaluation results for a completed plan back to plan_journal.
    This CLOSES the learning loop: Plan → Execute → Measure → Evaluate → Learn.

    plan_id: the plan to evaluate (e.g. 'iris-20260411-1346')
    outcome_score: 1-10 score for how well the plan achieved its hypothesis
    actual_outcome: what actually happened (stress hours, compliance, key observations)
    lesson_extracted: new lesson learned, or empty if none"""
    if not 1 <= outcome_score <= 10:
        return json.dumps({"error": "outcome_score must be 1-10"})

    conn = await _db()
    try:
        existing = await conn.fetchrow("SELECT plan_id FROM plan_journal WHERE plan_id = $1", plan_id)
        if not existing:
            return json.dumps({"error": f"Plan '{plan_id}' not found in plan_journal"})

        await conn.execute(
            """UPDATE plan_journal SET
                outcome_score = $2, actual_outcome = $3, lesson_extracted = $4, validated_at = now()
               WHERE plan_id = $1""",
            plan_id,
            outcome_score,
            actual_outcome,
            lesson_extracted or None,
        )
        return json.dumps({"ok": True, "plan_id": plan_id, "outcome_score": outcome_score})
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════════════════
# HISTORY TOOL
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
async def history(metric: str = "climate", hours: int = 24, resolution_min: int = 15) -> str:
    """Get historical time-bucketed data for any sensor domain.
    metric: 'climate' (temp, vpd, rh, dew_point), 'equipment' (relay state durations),
            'energy' (power watts), 'outdoor' (weather station), 'diagnostics' (ESP32 health)
    hours: lookback window (default 24)
    resolution_min: bucket size in minutes (default 15)
    Returns JSON array of time-bucketed records."""
    queries = {
        "climate": """
            SELECT time_bucket($1::interval, ts) AS time,
                   round(avg(temp_avg)::numeric, 1) AS temp_f,
                   round(avg(vpd_avg)::numeric, 2) AS vpd_kpa,
                   round(avg(rh_avg)::numeric, 0) AS rh_pct,
                   round(avg(dew_point)::numeric, 1) AS dew_point_f,
                   round(avg(outdoor_temp_f)::numeric, 1) AS outdoor_temp,
                   round(avg(outdoor_rh_pct)::numeric, 0) AS outdoor_rh
            FROM climate WHERE ts > now() - $2::interval AND temp_avg IS NOT NULL
            GROUP BY 1 ORDER BY 1""",
        "energy": """
            SELECT time_bucket($1::interval, ts) AS time,
                   round(avg(watts_total)::numeric, 0) AS watts
            FROM energy WHERE ts > now() - $2::interval
            GROUP BY 1 ORDER BY 1""",
        "outdoor": """
            SELECT time_bucket($1::interval, ts) AS time,
                   round(avg(outdoor_temp_f)::numeric, 1) AS temp_f,
                   round(avg(outdoor_rh_pct)::numeric, 0) AS rh_pct,
                   round(avg(solar_irradiance_w_m2)::numeric, 0) AS solar_w
            FROM climate WHERE ts > now() - $2::interval AND outdoor_temp_f IS NOT NULL
            GROUP BY 1 ORDER BY 1""",
        "equipment": """
            SELECT time_bucket($1::interval, e.ts) AS time,
                   e.equipment,
                   round(sum(CASE WHEN e.state THEN 1.0 ELSE 0.0 END) / count(*)::numeric * 100, 0) AS on_pct
            FROM equipment_state e
            WHERE e.ts > now() - $2::interval
              AND e.equipment IN ('fan1','fan2','vent','fog','heat1','heat2','mister_south','mister_west','mister_center')
            GROUP BY 1, 2 ORDER BY 1, 2""",
        "diagnostics": """
            SELECT time_bucket($1::interval, ts) AS time,
                   round(avg(wifi_rssi)::numeric, 0) AS wifi_rssi,
                   round(avg(heap_bytes)::numeric, 0) AS heap_bytes,
                   round(max(uptime_s)::numeric, 0) AS uptime_s
            FROM diagnostics WHERE ts > now() - $2::interval
            GROUP BY 1 ORDER BY 1""",
    }

    template = queries.get(metric)
    if not template:
        return json.dumps({"error": f"Unknown metric '{metric}'. Use: {', '.join(queries.keys())}"})

    # Inline interval values (asyncpg needs timedelta for interval params)
    sql = template.replace("$1::interval", f"'{resolution_min} minutes'::interval").replace(
        "$2::interval", f"'{hours} hours'::interval"
    )

    conn = await _db()
    try:
        rows = await conn.fetch(sql)
        return _json([dict(r) for r in rows[:500]])
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════════════════
# CROP MANAGEMENT TOOLS
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
async def crops(action: str, crop_id: int = 0, data: str = "") -> str:
    """Manage greenhouse crops. Actions: list, get, create, update, deactivate.
    list: all active crops with zone, stage, recent health
    get: full detail for one crop including observations and events
    create: data = {"name", "variety", "zone", "position", "planted_date", "stage", ...}
    update: data = {"name"?, "stage"?, "zone"?, "expected_harvest"?, "notes"?, ...}
    deactivate: soft-delete by crop_id"""
    d = json.loads(data) if data else {}
    conn = await _db()
    try:
        if action == "list":
            rows = await conn.fetch("""
                SELECT c.id, c.name, c.variety, c.zone, c.position, c.stage, c.planted_date,
                       c.expected_harvest, c.is_active,
                       (SELECT round(avg(health_score)::numeric, 2) FROM observations o
                        WHERE o.crop_id = c.id AND o.health_score IS NOT NULL
                        AND o.ts > now() - interval '7 days') AS health_7d
                FROM crops c WHERE c.is_active = true AND c.greenhouse_id = 'vallery'
                ORDER BY c.zone, c.position""")
            return _json([dict(r) for r in rows])

        elif action == "get" and crop_id:
            row = await conn.fetchrow("SELECT * FROM crops WHERE id = $1", crop_id)
            if not row:
                return json.dumps({"error": f"Crop {crop_id} not found"})
            obs = await conn.fetch(
                "SELECT ts, obs_type, notes, health_score FROM observations WHERE crop_id = $1 ORDER BY ts DESC LIMIT 10",
                crop_id,
            )
            events = await conn.fetch(
                "SELECT ts, event_type, old_stage, new_stage, notes FROM crop_events WHERE crop_id = $1 ORDER BY ts DESC LIMIT 10",
                crop_id,
            )
            return _json(
                {
                    "crop": dict(row),
                    "recent_observations": [dict(o) for o in obs],
                    "recent_events": [dict(e) for e in events],
                }
            )

        elif action == "create":
            row = await conn.fetchrow(
                """
                INSERT INTO crops (name, variety, zone, position, planted_date, expected_harvest, stage,
                                   count, notes, greenhouse_id)
                VALUES ($1, $2, $3, $4, $5::date, $6::date, $7, $8, $9, 'vallery') RETURNING *""",
                d.get("name"),
                d.get("variety"),
                d.get("zone"),
                d.get("position"),
                d.get("planted_date"),
                d.get("expected_harvest"),
                d.get("stage", "seedling"),
                d.get("count", 1),
                d.get("notes"),
            )
            return _json(dict(row))

        elif action == "update" and crop_id:
            sets = []
            vals = [crop_id]
            i = 2
            for col in (
                "name",
                "variety",
                "zone",
                "position",
                "stage",
                "expected_harvest",
                "count",
                "notes",
                "target_vpd_low",
                "target_vpd_high",
                "target_dli",
                "base_temp_f",
            ):
                if col in d:
                    sets.append(f"{col} = ${i}")
                    vals.append(d[col])
                    i += 1
            if not sets:
                return json.dumps({"error": "No fields to update"})
            sets.append("updated_at = now()")
            row = await conn.fetchrow(f"UPDATE crops SET {', '.join(sets)} WHERE id = $1 RETURNING *", *vals)
            return _json(dict(row)) if row else json.dumps({"error": "Crop not found"})

        elif action == "deactivate" and crop_id:
            await conn.execute("UPDATE crops SET is_active = false, updated_at = now() WHERE id = $1", crop_id)
            return json.dumps({"ok": True, "crop_id": crop_id, "action": "deactivated"})

        return json.dumps({"error": f"Unknown action '{action}'. Use: list, get, create, update, deactivate"})
    finally:
        await conn.close()


@mcp.tool()
async def observations(action: str, crop_id: int = 0, data: str = "") -> str:
    """Record and query crop observations, events, harvests, and treatments.
    Actions: list_observations, record_observation, list_events, record_event,
             record_harvest, list_harvests, record_treatment, list_treatments.
    data: JSON with fields appropriate to the action."""
    d = json.loads(data) if data else {}
    conn = await _db()
    try:
        if action == "list_observations":
            rows = await conn.fetch(
                """
                SELECT o.id, o.ts, o.crop_id, c.name, o.zone, o.obs_type, o.notes, o.health_score, o.severity, o.observer
                FROM observations o JOIN crops c ON o.crop_id = c.id
                WHERE ($1::int = 0 OR o.crop_id = $1) ORDER BY o.ts DESC LIMIT 50""",
                crop_id,
            )
            return _json([dict(r) for r in rows])

        elif action == "record_observation" and crop_id:
            crop = await conn.fetchrow("SELECT zone, position FROM crops WHERE id = $1", crop_id)
            if not crop:
                return json.dumps({"error": f"Crop {crop_id} not found"})
            row = await conn.fetchrow(
                """
                INSERT INTO observations (crop_id, zone, position, obs_type, notes, severity, observer, health_score, source)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'iris') RETURNING *""",
                crop_id,
                crop["zone"],
                crop["position"],
                d.get("obs_type", "health_check"),
                d.get("notes"),
                d.get("severity"),
                d.get("observer", "Iris"),
                d.get("health_score"),
            )
            return _json(dict(row))

        elif action == "list_events":
            rows = await conn.fetch(
                """
                SELECT e.id, e.ts, e.crop_id, c.name, e.event_type, e.old_stage, e.new_stage, e.count, e.notes
                FROM crop_events e JOIN crops c ON e.crop_id = c.id
                WHERE ($1::int = 0 OR e.crop_id = $1) ORDER BY e.ts DESC LIMIT 50""",
                crop_id,
            )
            return _json([dict(r) for r in rows])

        elif action == "record_event" and crop_id:
            row = await conn.fetchrow(
                """
                INSERT INTO crop_events (crop_id, event_type, old_stage, new_stage, count, operator, source, notes)
                VALUES ($1, $2, $3, $4, $5, $6, 'iris', $7) RETURNING *""",
                crop_id,
                d.get("event_type"),
                d.get("old_stage"),
                d.get("new_stage"),
                d.get("count"),
                d.get("operator", "Iris"),
                d.get("notes"),
            )
            return _json(dict(row))

        elif action == "record_harvest" and crop_id:
            row = await conn.fetchrow(
                """
                INSERT INTO harvests (crop_id, weight_kg, unit_count, quality_grade, unit_price_usd, notes, harvested_by, greenhouse_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'vallery') RETURNING *""",
                crop_id,
                d.get("weight_kg"),
                d.get("unit_count"),
                d.get("quality_grade"),
                d.get("unit_price_usd"),
                d.get("notes"),
                d.get("harvested_by", "Iris"),
            )
            return _json(dict(row))

        elif action == "list_harvests":
            rows = await conn.fetch(
                """
                SELECT h.id, h.ts, h.crop_id, c.name, h.weight_kg, h.unit_count, h.quality_grade, h.notes
                FROM harvests h JOIN crops c ON h.crop_id = c.id
                WHERE ($1::int = 0 OR h.crop_id = $1) ORDER BY h.ts DESC LIMIT 50""",
                crop_id,
            )
            return _json([dict(r) for r in rows])

        elif action == "record_treatment" and crop_id:
            row = await conn.fetchrow(
                """
                INSERT INTO treatments (crop_id, product, rate, rate_unit, method, zone, target_pest,
                                        phi_days, rei_hours, applied_by, notes, greenhouse_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 'vallery') RETURNING *""",
                crop_id,
                d.get("product"),
                d.get("rate"),
                d.get("rate_unit"),
                d.get("method"),
                d.get("zone"),
                d.get("target_pest"),
                d.get("phi_days"),
                d.get("rei_hours"),
                d.get("applied_by", "Iris"),
                d.get("notes"),
            )
            return _json(dict(row))

        elif action == "list_treatments":
            rows = await conn.fetch(
                """
                SELECT t.id, t.ts, t.crop_id, c.name, t.product, t.method, t.zone, t.target_pest, t.phi_days, t.notes
                FROM treatments t JOIN crops c ON t.crop_id = c.id
                WHERE ($1::int = 0 OR t.crop_id = $1) ORDER BY t.ts DESC LIMIT 50""",
                crop_id,
            )
            return _json([dict(r) for r in rows])

        return json.dumps({"error": f"Unknown action '{action}'"})
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════════════════
# ALERT MANAGEMENT
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
async def alerts(action: str = "list", alert_id: int = 0, data: str = "") -> str:
    """Manage greenhouse alerts. Actions: list, acknowledge, resolve.
    list: active/recent alerts (last 24h by default)
    acknowledge: mark as seen by Iris
    resolve: close with resolution notes (data can be JSON or plain text)"""
    if data:
        try:
            d = json.loads(data)
        except (json.JSONDecodeError, ValueError):
            d = {"resolution": data}
    else:
        d = {}
    conn = await _db()
    try:
        if action == "list":
            hours = d.get("hours", 24)
            rows = await conn.fetch(
                """
                SELECT id, to_char(ts AT TIME ZONE 'America/Denver', 'MM-DD HH24:MI') AS time,
                       alert_type, severity, message, disposition,
                       acknowledged_at IS NOT NULL AS acknowledged,
                       resolved_at IS NOT NULL AS resolved
                FROM alert_log WHERE ts > now() - ($1::int || ' hours')::interval
                ORDER BY ts DESC LIMIT 50""",
                hours,
            )
            return _json([dict(r) for r in rows])

        elif action == "acknowledge" and alert_id:
            await conn.execute(
                "UPDATE alert_log SET acknowledged_at = now(), acknowledged_by = 'iris', disposition = 'acknowledged' WHERE id = $1",
                alert_id,
            )
            return json.dumps({"ok": True, "alert_id": alert_id, "action": "acknowledged"})

        elif action == "resolve" and alert_id:
            await conn.execute(
                "UPDATE alert_log SET resolved_at = now(), resolved_by = 'iris', resolution = $2, disposition = 'resolved' WHERE id = $1",
                alert_id,
                d.get("resolution", "Resolved by Iris"),
            )
            return json.dumps({"ok": True, "alert_id": alert_id, "action": "resolved"})

        return json.dumps({"error": f"Unknown action '{action}'. Use: list, acknowledge, resolve"})
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════════════════
# LESSON MANAGEMENT
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
async def lessons_manage(action: str, lesson_id: int = 0, data: str = "") -> str:
    """Manage planner lessons (accumulated operational knowledge).
    Actions: create, update, deactivate, validate.
    create: data = {"category", "condition", "lesson", "confidence": "low|medium|high"}
    update: data = {"lesson"?, "condition"?, "confidence"?}
    deactivate: mark lesson as inactive
    validate: increment times_validated, optionally upgrade confidence"""
    d = json.loads(data) if data else {}
    conn = await _db()
    try:
        if action == "create":
            row = await conn.fetchrow(
                """
                INSERT INTO planner_lessons (category, condition, lesson, confidence, times_validated, is_active, greenhouse_id)
                VALUES ($1, $2, $3, $4, 1, true, 'vallery') RETURNING *""",
                d.get("category"),
                d.get("condition"),
                d.get("lesson"),
                d.get("confidence", "low"),
            )
            return _json(dict(row))

        elif action == "update" and lesson_id:
            sets = []
            vals = [lesson_id]
            i = 2
            for col in ("category", "condition", "lesson", "confidence"):
                if col in d:
                    sets.append(f"{col} = ${i}")
                    vals.append(d[col])
                    i += 1
            if not sets:
                return json.dumps({"error": "No fields to update"})
            row = await conn.fetchrow(f"UPDATE planner_lessons SET {', '.join(sets)} WHERE id = $1 RETURNING *", *vals)
            return _json(dict(row)) if row else json.dumps({"error": "Lesson not found"})

        elif action == "deactivate" and lesson_id:
            await conn.execute("UPDATE planner_lessons SET is_active = false WHERE id = $1", lesson_id)
            return json.dumps({"ok": True, "lesson_id": lesson_id, "action": "deactivated"})

        elif action == "validate" and lesson_id:
            new_conf = d.get("confidence")
            if new_conf:
                await conn.execute(
                    "UPDATE planner_lessons SET times_validated = times_validated + 1, last_validated = now(), confidence = $2 WHERE id = $1",
                    lesson_id,
                    new_conf,
                )
            else:
                await conn.execute(
                    "UPDATE planner_lessons SET times_validated = times_validated + 1, last_validated = now() WHERE id = $1",
                    lesson_id,
                )
            return json.dumps({"ok": True, "lesson_id": lesson_id, "action": "validated"})

        return json.dumps({"error": f"Unknown action '{action}'. Use: create, update, deactivate, validate"})
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    os.environ.setdefault("MCP_HTTP_HOST", "127.0.0.1")
    os.environ.setdefault("MCP_HTTP_PORT", "8000")
    mcp.run(transport="streamable-http")
