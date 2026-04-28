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
import sys
from datetime import date, datetime
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import asyncpg
from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

# verdify_schemas lives one level up at /mnt/iris/verdify/verdify_schemas
sys.path.insert(0, "/mnt/iris/verdify")
from verdify_schemas import (  # noqa: E402
    ALL_TUNABLES,
    AlertAckPayload,
    AlertResolvePayload,
    ClimateSnapshot,
    CropCreate,
    CropUpdate,
    EquipmentStateRow,
    EventCreate,
    ForecastSummaryRow,
    HarvestCreate,
    LessonCreate,
    LessonSummary,
    LessonUpdate,
    LessonValidate,
    ObservationCreate,
    Plan,
    PlanEvaluation,
    PlanHypothesisStructured,
    PlanRunResponse,
    PlanStatusJournal,
    PlanStatusResponse,
    PlanStatusWaypoint,
    ScorecardResponse,
    SetpointSummary,
    TreatmentCreate,
)
from verdify_schemas.tunable_registry import PLANNER_PUSHABLE_REG  # noqa: E402

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
BAND_OWNED_PARAMS = {"temp_low", "temp_high", "vpd_low", "vpd_high"}
TIER1_TUNABLES = frozenset(
    {
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
        "d_heat_stage_2",
        "d_cool_stage_2",
        "temp_hysteresis",
        "heat_hysteresis",
        "bias_heat",
        "bias_cool",
        "min_heat_on_s",
        "min_heat_off_s",
        "mister_engage_delay_s",
        "mister_all_delay_s",
        "sw_summer_vent_enabled",
        "vent_prefer_temp_delta_f",
        "vent_prefer_dp_delta_f",
        "outdoor_staleness_max_s",
        "summer_vent_min_runtime_s",
        "sw_fog_closes_vent",
        "sw_mister_closes_vent",
        "sw_dwell_gate_enabled",
        "dwell_gate_ms",
        "sw_fsm_controller_enabled",
        "mist_backoff_s",
    }
)


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
    The planner sets registry-approved tunables that shape how the controller responds.
    Crop-band params (temp_low, temp_high, vpd_low, vpd_high) are dispatcher-owned
    read-only context in routine plans; use direct tunable pushes only for explicit overrides.""",
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
        # Sprint 23+: validate-on-emit through ClimateSnapshot. Schema drift
        # in the SELECT (e.g. a renamed column) fails here, not silently in
        # Iris's downstream parse.
        snap = ClimateSnapshot.model_validate({**dict(row), "mode": mode})
        return snap.model_dump_json()
    finally:
        await conn.close()


@mcp.tool()
async def scorecard(target_date: str = "") -> str:
    """Get the planner scorecard — 25 KPI metrics for a given day.
    Includes: planner_score, compliance_pct (both in band), temp_compliance_pct,
    vpd_compliance_pct, stress hours (heat/cold/vpd_high/vpd_low), utility usage
    (kwh, therms, water_gal, mister_water_gal), costs (electric/gas/water/total),
    dew point safety, and 7-day averages. Pass date as YYYY-MM-DD or omit for today.

    Response is validated through verdify_schemas.ScorecardResponse — partial
    days emit a subset of metrics as null. DB drift (new metric) surfaces as a
    validation error with the raw values preserved so Iris can still read the card."""
    conn = await _db()
    try:
        if target_date:
            d = datetime.strptime(target_date, "%Y-%m-%d").date()
        else:
            d = await conn.fetchval("SELECT (now() AT TIME ZONE 'America/Denver')::date")
        rows = await conn.fetch("SELECT * FROM fn_planner_scorecard($1::date)", d)
        try:
            sc = ScorecardResponse.from_metric_rows(rows)
        except ValidationError as e:
            return _json(
                {
                    "error": "ScorecardResponse validation failed — DB may have new metrics",
                    "details": json.loads(e.json()),
                    "raw": {r["metric"]: (float(r["value"]) if r["value"] is not None else None) for r in rows},
                }
            )
        return sc.model_dump_json(by_alias=True)
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
        validated = [EquipmentStateRow.model_validate(dict(r)).model_dump(mode="json") for r in rows]
        return json.dumps(validated)
    finally:
        await conn.close()


@mcp.tool()
async def forecast(hours: int = 72) -> str:
    """Get weather forecast summary for the next N hours (default 72).
    Returns hourly temp, RH, VPD, cloud cover, solar radiation."""
    try:
        hours = max(1, min(int(hours), 168))
    except (TypeError, ValueError):
        return json.dumps({"error": "hours must be an integer between 1 and 168"})
    conn = await _db()
    try:
        rows = await conn.fetch(
            """
            SELECT to_char(ts AT TIME ZONE 'America/Denver', 'Dy HH24:MI') as time,
                   round(temp_f::numeric,0) as temp, round(rh_pct::numeric,0) as rh,
                   round(vpd_kpa::numeric,2) as vpd, round(cloud_cover_pct::numeric,0) as cloud,
                   round(GREATEST(COALESCE(direct_radiation_w_m2,0),0)::numeric,0) as solar
            FROM (
                SELECT DISTINCT ON (ts) ts, temp_f, rh_pct, vpd_kpa, cloud_cover_pct,
                       direct_radiation_w_m2
                FROM weather_forecast
                WHERE ts > now() AND ts < now() + ($1::int * interval '1 hour')
                ORDER BY ts, fetched_at DESC
            ) sub
            ORDER BY ts
            LIMIT $1
            """,
            hours,
        )
        validated = [ForecastSummaryRow.model_validate(dict(r)).model_dump(mode="json") for r in rows]
        return json.dumps(validated)
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
        rows = await conn.fetch(
            """
            SELECT parameter, round(value::numeric,3) as value, source,
                   to_char(ts AT TIME ZONE 'America/Denver', 'HH24:MI') as updated
            FROM (SELECT DISTINCT ON (parameter) parameter, value, source, ts
                  FROM setpoint_changes ORDER BY parameter, ts DESC) sub
            WHERE parameter = ANY($1::text[])
            ORDER BY parameter
            """,
            sorted(ALL_TUNABLES),
        )
        validated = [SetpointSummary.model_validate(dict(r)).model_dump(mode="json") for r in rows]
        return json.dumps(validated)
    finally:
        await conn.close()


@mcp.tool()
async def set_tunable(
    parameter: str,
    value: float,
    reason: str = "iris-manual",
    trigger_id: str | None = None,
    planner_instance: str | None = None,
) -> str:
    """Push a single registry-approved tunable to the ESP32 immediately.
    The dispatcher will apply it within 5 minutes.
    Example: set_tunable('fog_escalation_kpa', 0.15, 'fog is 7x more effective than misters')

    trigger_id, planner_instance: optional contract v1.4 audit fields.
    Pass through from the trigger banner shown at the bottom of every
    planning event prompt (`trigger_id=<uuid>`, `planner_instance='opus'|'local'`).
    Stamped onto plan_journal so SLA monitors can correlate by uuid."""
    # Schema-level gate first rejects typos; the registry then blocks
    # operator-only safety rails and readback-only diagnostics.
    if parameter not in ALL_TUNABLES:
        return json.dumps({"error": f"'{parameter}' is not a known tunable — not in verdify_schemas.ALL_TUNABLES"})
    if parameter not in PLANNER_PUSHABLE_REG:
        return json.dumps(
            {
                "error": f"'{parameter}' is not planner-pushable in the tunable registry",
                "allowed": sorted(PLANNER_PUSHABLE_REG),
            }
        )

    # Phase-1b: set_tunable writes to setpoint_plan (one-shot waypoint at
    # ts=now()) so the dispatcher's plan-reading cycle doesn't overwrite
    # the iris push within 5 minutes. Observed live 2026-04-21:
    # min_heat_off_s=180 pushed at 11:36, overwritten to 300 from the
    # prior sunrise plan within 4 minutes. setpoint_plan is the dispatcher's
    # actual source of truth; writing there makes iris pushes durable until
    # the next plan supersedes.
    #
    # plan_id format `iris-oneshot-<YYYYMMDD-HHMM>` lets the next set_plan
    # call (which deactivates older plans) distinguish iris tactical pushes
    # from automatic SUNRISE/SUNSET plans and preserve them across boundaries.
    # Contract v1.4 §2.C — stamp audit metadata into setpoint_plan.reason
    # text so the trigger and instance survive on the row even though
    # setpoint_plan has no dedicated columns yet. Searchable via
    # `WHERE reason LIKE '%trigger=<uuid>%'`.
    audit_suffix_parts = []
    if trigger_id:
        audit_suffix_parts.append(f"trigger={trigger_id}")
    if planner_instance:
        audit_suffix_parts.append(f"instance={planner_instance}")
    if audit_suffix_parts:
        reason_with_audit = f"{reason} [{' '.join(audit_suffix_parts)}]"
    else:
        reason_with_audit = reason

    conn = await _db()
    try:
        now_mdt = datetime.now(ZoneInfo("America/Denver"))
        plan_id = f"iris-oneshot-{now_mdt.strftime('%Y%m%d-%H%M')}"
        await conn.execute(
            """
            INSERT INTO setpoint_plan (ts, parameter, value, plan_id, source, reason)
            VALUES (now(), $1, $2, $3, 'iris', $4)
            ON CONFLICT (ts, parameter, plan_id) DO UPDATE
              SET value = EXCLUDED.value, reason = EXCLUDED.reason
            """,
            parameter,
            value,
            plan_id,
            reason_with_audit,
        )
        return json.dumps(
            {
                "ok": True,
                "parameter": parameter,
                "value": value,
                "reason": reason_with_audit,
                "plan_id": plan_id,
                "trigger_id": trigger_id,
                "planner_instance": planner_instance,
                "note": (
                    "Written to setpoint_plan as a one-shot waypoint at now(). "
                    "Dispatcher pushes to ESP32 within 5 minutes and this value "
                    "persists until the next set_plan or set_tunable supersedes."
                ),
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
        result = send_to_iris("SUNRISE", "Ad-hoc planning cycle (triggered via MCP)", context=context)
        resp = PlanRunResponse(
            ok=bool(result.get("delivered")),
            note="SUNRISE event sent to Iris planner. Check #greenhouse for the brief.",
            error=None if result.get("delivered") else result.get("gateway_body"),
        )
        return resp.model_dump_json(exclude_none=True)
    except Exception as e:
        return PlanRunResponse(ok=False, error=str(e)).model_dump_json(exclude_none=True)


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
        resp = PlanStatusResponse(
            plan=PlanStatusJournal.model_validate(dict(journal)) if journal else None,
            future_waypoints=[PlanStatusWaypoint.model_validate(dict(w)) for w in waypoints],
        )
        return resp.model_dump_json(exclude_none=True)
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
        validated = [LessonSummary.model_validate(dict(r)).model_dump(mode="json") for r in rows]
        return json.dumps(validated)
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════════════════
# DATA QUERY TOOL
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
async def query(sql: str) -> str:
    """Run a read-only SQL query against the Verdify database.
    Returns up to 100 rows as JSON. Only SELECT queries allowed."""
    sql_stripped = sql.strip()
    sql_upper = sql_stripped.upper()
    if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
        return json.dumps({"error": "Only SELECT/WITH queries are allowed"})
    # Keep this as a simple one-statement escape hatch. The DB transaction is
    # read-only below, but rejecting multi-statement text avoids surprising
    # behavior and keeps tool output bounded.
    if ";" in sql_stripped.rstrip(";"):
        return json.dumps({"error": "Only a single read-only statement is allowed"})

    conn = await _db()
    try:
        async with conn.transaction(readonly=True):
            await conn.execute("SET LOCAL statement_timeout = '5s'")
            rows = await conn.fetch(sql_stripped.rstrip(";"))
        return _json([dict(r) for r in rows[:100]])
    except asyncpg.ReadOnlySQLTransactionError:
        return json.dumps({"error": "Query attempted a write and was rejected by the read-only transaction"})
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════════════════
# PLANNING TOOLS
# ═══════════════════════════════════════════════════════════════


@mcp.tool()
async def set_plan(
    plan_id: str,
    hypothesis: str,
    transitions: str,
    experiment: str = "",
    expected_outcome: str = "",
    trigger_id: str | None = None,
    planner_instance: str | None = None,
) -> str:
    """Write a 72-hour setpoint plan with multiple time-based waypoints.
    Deactivates all existing future waypoints, writes new ones, and logs a plan journal entry.
    The dispatcher executes these on schedule — the greenhouse follows the plan even if the planner goes offline.

    plan_id: unique ID like 'iris-YYYYMMDD-HHMM'
    hypothesis: what you expect this plan to achieve — may optionally include a
        fenced ```json block matching PlanHypothesisStructured (conditions +
        stress_windows + rationale). If present, it's validated and stored in
        plan_journal.hypothesis_structured for structured downstream rendering.
    transitions: JSON array of objects: [{"ts": "ISO8601-with-TZ", "params": {"param": value, ...}, "reason": "..."}]
    experiment: optional one-line experiment description
    expected_outcome: optional measurable prediction
    trigger_id, planner_instance: optional contract v1.4 audit fields. Pass
        through from the audit-headers banner shown at the bottom of every
        planning event prompt (`trigger_id=<uuid>`, `planner_instance='opus'|'local'`).
        Stamped onto plan_journal so SLA monitors and audit queries can
        correlate plans to deliveries by uuid (not 2h time-window fallback)."""
    # Sprint 20: validate the whole envelope through Plan schema before any DB writes.
    # This rejects unknown tunables, inverted temp/VPD bands, non-monotonic transitions,
    # bad plan_id format, timezone-naive timestamps, etc. — at the MCP boundary, so
    # partial plans never land in setpoint_plan.
    try:
        waypoints_raw = json.loads(transitions)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON in transitions: {e}"})

    try:
        plan = Plan.model_validate(
            {
                "plan_id": plan_id,
                "hypothesis": hypothesis,
                "experiment": experiment or None,
                "expected_outcome": expected_outcome or None,
                "transitions": waypoints_raw,
            }
        )
    except ValidationError as e:
        return json.dumps({"error": "Plan validation failed", "details": json.loads(e.json())})

    writable_params = [param for wp in plan.transitions for param in wp.params if param not in BAND_OWNED_PARAMS]
    if not writable_params:
        return json.dumps(
            {
                "error": "Plan contains only crop-band params; these are dispatcher-owned read-only context",
                "band_owned_params": sorted(BAND_OWNED_PARAMS),
            }
        )

    # Sprint 20 Phase 5: try to extract a PlanHypothesisStructured JSON block
    # from the hypothesis prose. Fence convention: ```json …``` anywhere in
    # the text. Failure to find or validate is silent — the prose still lands.
    structured_payload: str | None = None
    structured_warning: str | None = None
    import re as _re

    m = _re.search(r"```json\s*(\{.*?\})\s*```", hypothesis, _re.DOTALL)
    if m:
        try:
            structured = PlanHypothesisStructured.model_validate_json(m.group(1))
            structured_payload = structured.model_dump_json()
        except ValidationError as e:
            structured_warning = f"structured hypothesis block present but invalid: {e.errors()[:3]}"

    conn = await _db()
    try:
        async with conn.transaction():
            existing = await conn.fetchval("SELECT 1 FROM plan_journal WHERE plan_id = $1", plan.plan_id)
            if existing:
                return json.dumps({"error": f"plan_id {plan.plan_id!r} already exists; generate a new plan_id"})

            # Deactivate existing future waypoints EXCEPT iris-oneshot tactical pushes.
            # Phase 1b: set_tunable writes to setpoint_plan with plan_id
            # `iris-oneshot-<YYYYMMDD-HHMM>`. Those are live tactical adjustments
            # that should survive across regular sunrise/sunset plans until
            # superseded by a later waypoint. Plan-level supersession is by
            # `created_at DESC` so the newer multi-waypoint plan still wins on
            # any parameter it re-specifies.
            await conn.execute(
                """UPDATE setpoint_plan SET is_active = false
                   WHERE ts > now() AND is_active = true
                     AND plan_id NOT LIKE 'iris-oneshot-%'"""
            )

            # Write new waypoints. Crop-band params are read-only planner
            # context, owned by crop profiles + dispatcher; dropping them
            # here prevents future clamp storms from semantically valid but
            # owner-misaligned plans.
            rows_written = 0
            band_params_dropped = 0
            for wp in plan.transitions:
                for param, value in wp.params.items():
                    if param in BAND_OWNED_PARAMS:
                        band_params_dropped += 1
                        continue
                    await conn.execute(
                        """INSERT INTO setpoint_plan (ts, parameter, value, plan_id, source, reason, created_at, is_active, greenhouse_id)
                           VALUES ($1, $2, $3, $4, 'iris', $5, now(), true, 'vallery')""",
                        wp.ts,
                        param,
                        float(value),
                        plan.plan_id,
                        wp.reason or "",
                    )
                    rows_written += 1

            # Write journal entry — structured JSONB column populated only if
            # the PlanHypothesisStructured block was present AND valid.
            # Contract v1.4 §2.C — stamp planner_instance + trigger_id when the
            # caller passed them through from the prompt's audit-headers banner.
            # Both columns nullable; NULL means "pre-v1.4 path or operator
            # injection that didn't carry headers."
            await conn.execute(
                """INSERT INTO plan_journal
                     (plan_id, created_at, hypothesis, experiment, expected_outcome,
                      hypothesis_structured, greenhouse_id, planner_instance, trigger_id)
                   VALUES ($1, now(), $2, $3, $4, $5::jsonb, 'vallery', $6, $7::uuid)""",
                plan.plan_id,
                plan.hypothesis,
                plan.experiment,
                plan.expected_outcome,
                structured_payload,
                planner_instance,
                trigger_id,
            )

        # Sprint 20 Phase 6: drop a trigger file so verdify-plan-publish.path
        # fires and regenerates the daily plan page. Local-SSD location so
        # inotify actually works (NFS path units don't fire reliably).
        try:
            from datetime import UTC
            from datetime import datetime as _dt

            trigger_path = Path("/var/local/verdify/state/plan-publish-trigger")
            trigger_path.parent.mkdir(parents=True, exist_ok=True)
            trigger_path.write_text(f"{plan.plan_id}\n{_dt.now(UTC).isoformat()}\n")
        except Exception as e:  # never block plan persistence on trigger failures
            log_msg = f"plan-publish trigger write failed (non-fatal): {e}"
            print(log_msg)

        result = {
            "ok": True,
            "plan_id": plan.plan_id,
            "transitions": len(plan.transitions),
            "rows_written": rows_written,
            "band_params_dropped": band_params_dropped,
            "structured_hypothesis": structured_payload is not None,
            "trigger_id": trigger_id,
            "planner_instance": planner_instance,
            "note": "Dispatcher will execute waypoints on schedule. Old future waypoints deactivated.",
        }
        if structured_warning:
            result["structured_warning"] = structured_warning
        return json.dumps(result)
    finally:
        await conn.close()


@mcp.tool()
async def acknowledge_trigger(trigger_id: str, reason: str, planner_instance: str | None = None) -> str:
    """Record that Iris read a planning trigger and intentionally wrote no plan.

    Use this only when a FORECAST/TRANSITION/HEARTBEAT cycle needs no setpoint
    change. It turns the matching plan_delivery_log row from pending -> acked,
    so SLA monitors can distinguish "read/no action" from "silent drop"."""
    try:
        tid = UUID(trigger_id)
    except (TypeError, ValueError):
        return json.dumps({"error": "trigger_id must be a valid UUID"})

    reason = (reason or "").strip()
    if not reason:
        return json.dumps({"error": "reason is required"})
    if len(reason) > 1000:
        return json.dumps({"error": "reason must be <= 1000 characters"})

    conn = await _db()
    try:
        row = await conn.fetchrow(
            """
            UPDATE plan_delivery_log
               SET status = 'acked',
                   acked_at = now(),
                   gateway_body = concat_ws(E'\n', NULLIF(gateway_body, ''), $2::text)
             WHERE trigger_id = $1::uuid
               AND status = 'pending'
             RETURNING id, event_type, instance, delivered_at, status
            """,
            str(tid),
            f"acknowledged by {planner_instance or 'iris'}: {reason}",
        )
        if row is None:
            existing = await conn.fetchrow(
                "SELECT id, event_type, instance, status FROM plan_delivery_log WHERE trigger_id = $1::uuid",
                str(tid),
            )
            if existing is None:
                return json.dumps({"error": f"trigger_id {tid} not found in plan_delivery_log"})
            return _json(
                {
                    "ok": False,
                    "trigger_id": str(tid),
                    "note": "trigger was already resolved",
                    "status": existing["status"],
                    "event_type": existing["event_type"],
                    "instance": existing["instance"],
                }
            )
        return _json(
            {
                "ok": True,
                "trigger_id": str(tid),
                "event_type": row["event_type"],
                "instance": row["instance"],
                "planner_instance": planner_instance,
                "status": row["status"],
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
    try:
        ev = PlanEvaluation.model_validate(
            {
                "plan_id": plan_id,
                "outcome_score": outcome_score,
                "actual_outcome": actual_outcome,
                "lesson_extracted": lesson_extracted or None,
            }
        )
    except ValidationError as e:
        return json.dumps({"error": "PlanEvaluation validation failed", "details": json.loads(e.json())})

    conn = await _db()
    try:
        existing = await conn.fetchrow("SELECT plan_id FROM plan_journal WHERE plan_id = $1", ev.plan_id)
        if not existing:
            return json.dumps({"error": f"Plan '{ev.plan_id}' not found in plan_journal"})

        await conn.execute(
            """UPDATE plan_journal SET
                outcome_score = $2, actual_outcome = $3, lesson_extracted = $4, validated_at = now()
               WHERE plan_id = $1""",
            ev.plan_id,
            ev.outcome_score,
            ev.actual_outcome,
            ev.lesson_extracted,
        )
        return json.dumps({"ok": True, "plan_id": ev.plan_id, "outcome_score": ev.outcome_score})
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
            try:
                payload = CropCreate.model_validate(d)
            except ValidationError as e:
                return json.dumps({"error": "CropCreate validation failed", "details": json.loads(e.json())})
            row = await conn.fetchrow(
                """
                INSERT INTO crops (name, variety, zone, position, planted_date, expected_harvest, stage,
                                   count, notes, seed_lot_id, supplier, base_temp_f,
                                   target_dli, target_vpd_low, target_vpd_high, greenhouse_id)
                VALUES ($1, $2, $3, $4, $5::date, $6::date, $7, $8, $9, $10, $11, $12,
                        $13, $14, $15, 'vallery') RETURNING *""",
                payload.name,
                payload.variety,
                payload.zone,
                payload.position,
                payload.planted_date,
                payload.expected_harvest,
                payload.stage,
                payload.count,
                payload.notes,
                payload.seed_lot_id,
                payload.supplier,
                payload.base_temp_f,
                payload.target_dli,
                payload.target_vpd_low,
                payload.target_vpd_high,
            )
            return _json(dict(row))

        elif action == "update" and crop_id:
            try:
                patch = CropUpdate.model_validate(d)
            except ValidationError as e:
                return json.dumps({"error": "CropUpdate validation failed", "details": json.loads(e.json())})
            set_fields = patch.model_dump(exclude_unset=True)
            if not set_fields:
                return json.dumps({"error": "No fields to update"})
            sets = [f"{k} = ${i}" for i, k in enumerate(set_fields, start=2)]
            sets.append("updated_at = now()")
            vals = [crop_id, *set_fields.values()]
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
    data: JSON with fields appropriate to the action. Envelopes:
      record_observation -> ObservationCreate (obs_type, notes, severity, ...)
      record_event       -> EventCreate (event_type, old_stage, new_stage, ...)
      record_harvest     -> HarvestCreate (weight_kg, unit_count, quality_grade,
                            zone, destination, unit_price, revenue, operator, notes)
      record_treatment   -> TreatmentCreate (product, active_ingredient,
                            concentration, rate, rate_unit, method, zone,
                            target_pest, phi_days, rei_hours, applicator,
                            observation_id, notes)"""
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
            try:
                obs = ObservationCreate.model_validate({**d, "observer": d.get("observer") or "Iris"})
            except ValidationError as e:
                return json.dumps({"error": "ObservationCreate validation failed", "details": json.loads(e.json())})
            row = await conn.fetchrow(
                """
                INSERT INTO observations (crop_id, zone, position, obs_type, notes, severity,
                                          observer, health_score, species, count, affected_pct, photo_path, source)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 'iris') RETURNING *""",
                crop_id,
                obs.zone or crop["zone"],
                obs.position or crop["position"],
                obs.obs_type,
                obs.notes,
                obs.severity,
                obs.observer,
                obs.health_score,
                obs.species,
                obs.count,
                obs.affected_pct,
                obs.photo_path,
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
            try:
                ev = EventCreate.model_validate({**d, "operator": d.get("operator") or "Iris"})
            except ValidationError as e:
                return json.dumps({"error": "EventCreate validation failed", "details": json.loads(e.json())})
            row = await conn.fetchrow(
                """
                INSERT INTO crop_events (crop_id, event_type, old_stage, new_stage, count, operator, source, notes)
                VALUES ($1, $2, $3, $4, $5, $6, 'iris', $7) RETURNING *""",
                crop_id,
                ev.event_type,
                ev.old_stage,
                ev.new_stage,
                ev.count,
                ev.operator,
                ev.notes,
            )
            return _json(dict(row))

        elif action == "record_harvest" and crop_id:
            try:
                hv = HarvestCreate.model_validate({**d, "operator": d.get("operator") or "Iris"})
            except ValidationError as e:
                return json.dumps({"error": "HarvestCreate validation failed", "details": json.loads(e.json())})
            row = await conn.fetchrow(
                """
                INSERT INTO harvests (crop_id, weight_kg, unit_count, quality_grade, zone, destination,
                                      unit_price, revenue, operator, notes)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) RETURNING *""",
                crop_id,
                hv.weight_kg,
                hv.unit_count,
                hv.quality_grade,
                hv.zone,
                hv.destination,
                hv.unit_price,
                hv.revenue,
                hv.operator,
                hv.notes,
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
            try:
                tr = TreatmentCreate.model_validate({**d, "applicator": d.get("applicator") or "Iris"})
            except ValidationError as e:
                return json.dumps({"error": "TreatmentCreate validation failed", "details": json.loads(e.json())})
            row = await conn.fetchrow(
                """
                INSERT INTO treatments (crop_id, product, active_ingredient, concentration, rate, rate_unit,
                                        method, zone, target_pest, phi_days, rei_hours, applicator,
                                        observation_id, notes)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14) RETURNING *""",
                crop_id,
                tr.product,
                tr.active_ingredient,
                tr.concentration,
                tr.rate,
                tr.rate_unit,
                tr.method,
                tr.zone,
                tr.target_pest,
                tr.phi_days,
                tr.rei_hours,
                tr.applicator,
                tr.observation_id,
                tr.notes,
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
            try:
                ack = AlertAckPayload.model_validate({"acknowledged_by": d.get("acknowledged_by") or "iris"})
            except ValidationError as e:
                return json.dumps({"error": "AlertAckPayload validation failed", "details": json.loads(e.json())})
            await conn.execute(
                "UPDATE alert_log SET acknowledged_at = now(), acknowledged_by = $2, "
                "disposition = 'acknowledged' WHERE id = $1",
                alert_id,
                ack.acknowledged_by,
            )
            return json.dumps({"ok": True, "alert_id": alert_id, "action": "acknowledged"})

        elif action == "resolve" and alert_id:
            try:
                res = AlertResolvePayload.model_validate(
                    {
                        "resolved_by": d.get("resolved_by") or "iris",
                        "resolution": d.get("resolution") or "Resolved by Iris",
                    }
                )
            except ValidationError as e:
                return json.dumps({"error": "AlertResolvePayload validation failed", "details": json.loads(e.json())})
            await conn.execute(
                "UPDATE alert_log SET resolved_at = now(), resolved_by = $2, "
                "resolution = $3, disposition = 'resolved' WHERE id = $1",
                alert_id,
                res.resolved_by,
                res.resolution,
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
            try:
                payload = LessonCreate.model_validate(d)
            except ValidationError as e:
                return json.dumps({"error": "LessonCreate validation failed", "details": json.loads(e.json())})
            row = await conn.fetchrow(
                """
                INSERT INTO planner_lessons (category, condition, lesson, confidence, times_validated, is_active, greenhouse_id)
                VALUES ($1, $2, $3, $4, 1, true, 'vallery') RETURNING *""",
                payload.category,
                payload.condition,
                payload.lesson,
                payload.confidence,
            )
            return _json(dict(row))

        elif action == "update" and lesson_id:
            try:
                patch = LessonUpdate.model_validate(d)
            except ValidationError as e:
                return json.dumps({"error": "LessonUpdate validation failed", "details": json.loads(e.json())})
            set_fields = patch.model_dump(exclude_unset=True)
            if not set_fields:
                return json.dumps({"error": "No fields to update"})
            sets = [f"{k} = ${i}" for i, k in enumerate(set_fields, start=2)]
            vals = [lesson_id, *set_fields.values()]
            row = await conn.fetchrow(f"UPDATE planner_lessons SET {', '.join(sets)} WHERE id = $1 RETURNING *", *vals)
            return _json(dict(row)) if row else json.dumps({"error": "Lesson not found"})

        elif action == "deactivate" and lesson_id:
            await conn.execute("UPDATE planner_lessons SET is_active = false WHERE id = $1", lesson_id)
            return json.dumps({"ok": True, "lesson_id": lesson_id, "action": "deactivated"})

        elif action == "validate" and lesson_id:
            try:
                val = LessonValidate.model_validate(d) if d else LessonValidate()
            except ValidationError as e:
                return json.dumps({"error": "LessonValidate validation failed", "details": json.loads(e.json())})
            if val.confidence:
                await conn.execute(
                    "UPDATE planner_lessons SET times_validated = times_validated + 1, "
                    "last_validated = now(), confidence = $2 WHERE id = $1",
                    lesson_id,
                    val.confidence,
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
# Sprint 23 — Topology + crop-history tools for Iris
# ═══════════════════════════════════════════════════════════════
#
# These expose the topology tables (zones/shelves/positions/equipment)
# and the crop-history views to Iris, so planning decisions can reference
# "what is currently at SOUTH-FLOOR-1" instead of opaque zone strings.


@mcp.tool()
async def topology() -> str:
    """Return the full greenhouse → zones → shelves → positions tree.

    Use this when you need to know the physical layout: what zones exist,
    what shelves each zone contains, and what position slots are
    defined. The planner uses this to validate setpoint scope (e.g.,
    per-zone VPD targets) and the website uses it for navigation.
    """
    conn = await _db()
    try:
        row = await conn.fetchrow(
            "SELECT greenhouse_id, greenhouse_name, zones FROM v_topology_tree WHERE greenhouse_id = 'vallery'"
        )
        if row is None:
            return _json({"error": "topology not available"})
        # asyncpg returns JSONB as str unless a codec is registered
        z = row["zones"]
        zones = json.loads(z) if isinstance(z, str) else z
        return _json(
            {
                "greenhouse_id": row["greenhouse_id"],
                "greenhouse_name": row["greenhouse_name"],
                "zones": zones,
            }
        )
    finally:
        await conn.close()


@mcp.tool()
async def position_current(zone_slug: str = "") -> str:
    """Return the current occupancy of every position (and which crop, if any).

    Args:
        zone_slug: optional — narrow to one zone (south, north, east, west, center).

    Each row: position_label, crop_name, crop_stage, crop_days_in_place, is_occupied.
    Use this to see "what is planted where right now."
    """
    conn = await _db()
    try:
        if zone_slug:
            rows = await conn.fetch(
                "SELECT * FROM v_position_current WHERE greenhouse_id = 'vallery' AND zone_slug = $1",
                zone_slug,
            )
        else:
            rows = await conn.fetch("SELECT * FROM v_position_current WHERE greenhouse_id = 'vallery'")
        return _json([dict(r) for r in rows])
    finally:
        await conn.close()


@mcp.tool()
async def crop_history(position_id: int = 0) -> str:
    """Return the chronological crop history at a given position.

    Args:
        position_id: the integer position_id. Use `position_current()` to find it.

    Returns every crop that has ever been at this position, newest first, with
    planted_date, cleared_at, final_stage, days_in_place, observation_count,
    and harvest_count. Includes both active and historical rows.
    """
    conn = await _db()
    try:
        if not position_id:
            return _json({"error": "position_id required"})
        rows = await conn.fetch(
            """
            SELECT * FROM v_crop_history
            WHERE position_id = $1 AND greenhouse_id = 'vallery'
            ORDER BY planted_date DESC
            """,
            position_id,
        )
        return _json([dict(r) for r in rows])
    finally:
        await conn.close()


@mcp.tool()
async def crop_lifecycle(crop_id: int) -> str:
    """Return a single crop's full lifecycle timeline.

    Args:
        crop_id: integer crop id.

    Returns: planted_date, cleared_at, current_stage, days_alive, event timeline
    (planted/stage_change/transplanted/removed/harvested), harvest totals
    (weight_kg, units, revenue), observation count + avg health score.
    The authoritative per-crop summary for planning decisions and
    retrospective evaluation.
    """
    conn = await _db()
    try:
        row = await conn.fetchrow(
            "SELECT * FROM v_crop_lifecycle WHERE crop_id = $1 AND greenhouse_id = 'vallery'",
            crop_id,
        )
        if row is None:
            return _json({"error": f"crop {crop_id} not found"})
        d = dict(row)
        # Unpack the JSONB events array
        ev = d.get("events")
        if isinstance(ev, str):
            d["events"] = json.loads(ev)
        return _json(d)
    finally:
        await conn.close()


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    os.environ.setdefault("MCP_HTTP_HOST", "127.0.0.1")
    os.environ.setdefault("MCP_HTTP_PORT", "8000")
    mcp.run(transport="streamable-http")
