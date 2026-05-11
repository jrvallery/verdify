"""
mcp/server_shadow.py — Shadow MCP server for the Phase 6 Hermes shadow week.

This is a thin wrapper around the production MCP server (`mcp/server.py`)
that re-points the WRITE tools at the *_shadow tables created by migration
115. READ tools are unchanged — they hit the production DB read-only.

Architectural shape: the production MCP server is imported as a module so
its read tools (climate, scorecard, history, etc.) are reused verbatim.
Only `set_plan`, `set_tunable`, `acknowledge_trigger`, `plan_evaluate`, and
`lessons_manage` are reimplemented here to redirect writes to the shadow
side-channel tables. `lessons_search` and `knowledge_search` use the
production embeddings table read-only.

Runtime contract: this server binds to a different port (default 8001) so
it can run alongside the production MCP. The shadow Hermes container
(`hermes-iris-shadow` on :8643) points its MCP config at this URL.

Usage:
    MCP_HTTP_HOST=127.0.0.1 MCP_HTTP_PORT=8001 \\
    python3 -m mcp.server_shadow
"""

from __future__ import annotations

import json
import os
import sys
from uuid import UUID

import asyncpg
from mcp.server.fastmcp import FastMCP

# Import the production server module to reuse the read tools + DB helpers.
sys.path.insert(0, os.path.dirname(__file__))

mcp_shadow = FastMCP("verdify-shadow")


# ── DB helper (mirrors production _db) ─────────────────────────────────────


async def _db() -> asyncpg.Connection:
    """Return an asyncpg connection. Mirrors mcp/server.py:_db so the shadow
    server can run standalone without importing the production module's
    module-level singletons."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ingestor"))
    from config import DB_DSN  # noqa: E402

    return await asyncpg.connect(DB_DSN)


def _json(payload) -> str:
    return json.dumps(payload, default=str, indent=2)


# ── Shadow write tools — same signatures as production, different storage ─


@mcp_shadow.tool()
async def set_plan(
    plan_id: str = "",
    hypothesis: str = "",
    transitions: str = "",
    experiment: str = "",
    expected_outcome: str = "",
    trigger_id: str | None = None,
    planner_instance: str | None = None,
) -> str:
    """Shadow set_plan: validates the envelope like production but writes to
    plan_journal_shadow + setpoint_plan_shadow. Returns success to the agent
    so the cycle proceeds as if a real plan landed.

    Shadow validation is intentionally permissive: we do NOT enforce the
    SUNRISE/SUNSET structured-hypothesis check, because the shadow week's
    job is to surface what the alternate gateway would naturally produce.
    Diff against the production row reveals enforcement deltas.
    """
    if not plan_id:
        return json.dumps({"error": "plan_id is required"})
    if not transitions:
        return json.dumps({"error": "transitions is required"})

    normalized_trigger = None
    if trigger_id:
        try:
            normalized_trigger = str(UUID(trigger_id))
        except (TypeError, ValueError):
            return json.dumps({"error": "trigger_id must be a valid UUID"})

    try:
        waypoints = json.loads(transitions)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON in transitions: {e}"})
    if not isinstance(waypoints, list):
        return json.dumps({"error": "transitions must be a JSON array"})

    # Extract optional structured hypothesis without enforcing it.
    structured_payload: str | None = None
    import re as _re

    m = _re.search(r"```json\s*(\{.*?\})\s*```", hypothesis, _re.DOTALL)
    if m:
        try:
            structured_payload = json.dumps(json.loads(m.group(1)))
        except Exception:
            pass
    if structured_payload is None:
        stripped = (hypothesis or "").strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                structured_payload = json.dumps(json.loads(stripped))
            except Exception:
                pass

    # Resolve which prod plan this shadow row pairs against — same
    # trigger_id should already exist in plan_journal if prod ran first.
    conn = await _db()
    try:
        matched_prod = None
        if normalized_trigger:
            matched_prod = await conn.fetchval(
                "SELECT plan_id FROM plan_journal WHERE trigger_id = $1::uuid",
                normalized_trigger,
            )

        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO plan_journal_shadow
                  (plan_id, hypothesis, experiment, expected_outcome,
                   hypothesis_structured, planner_instance, trigger_id,
                   matched_prod_plan_id, greenhouse_id)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7::uuid, $8, 'vallery')
                ON CONFLICT (plan_id) DO UPDATE SET
                   hypothesis            = EXCLUDED.hypothesis,
                   experiment            = EXCLUDED.experiment,
                   expected_outcome      = EXCLUDED.expected_outcome,
                   hypothesis_structured = EXCLUDED.hypothesis_structured,
                   matched_prod_plan_id  = EXCLUDED.matched_prod_plan_id
                """,
                plan_id,
                hypothesis,
                experiment or None,
                expected_outcome or None,
                structured_payload,
                planner_instance,
                normalized_trigger,
                matched_prod,
            )

            params_seen = set()
            for _idx, wp in enumerate(waypoints):
                if not isinstance(wp, dict):
                    continue
                ts = wp.get("ts")
                params = wp.get("params", {})
                reason = wp.get("reason")
                if not ts or not isinstance(params, dict):
                    continue
                for parameter, value in params.items():
                    params_seen.add(parameter)
                    try:
                        await conn.execute(
                            """
                            INSERT INTO setpoint_plan_shadow
                              (ts, parameter, value, plan_id, reason)
                            VALUES ($1::timestamptz, $2, $3, $4, $5)
                            ON CONFLICT (ts, parameter, plan_id) DO UPDATE
                              SET value = EXCLUDED.value, reason = EXCLUDED.reason
                            """,
                            ts,
                            parameter,
                            float(value) if isinstance(value, (int, float)) else None,
                            plan_id,
                            reason,
                        )
                    except Exception as exc:  # pragma: no cover — surface failure
                        print(f"[shadow set_plan] waypoint write failed: {exc}", file=sys.stderr)

            await conn.execute(
                "UPDATE plan_journal_shadow SET params_changed = $2::text[] WHERE plan_id = $1",
                plan_id,
                sorted(params_seen),
            )

        return _json(
            {
                "ok": True,
                "shadow": True,
                "plan_id": plan_id,
                "params_changed": sorted(params_seen),
                "matched_prod_plan_id": matched_prod,
                "structured_hypothesis_captured": structured_payload is not None,
            }
        )
    finally:
        await conn.close()


@mcp_shadow.tool()
async def set_tunable(
    parameter: str,
    value: float,
    reason: str = "",
    trigger_id: str | None = None,
    planner_instance: str | None = None,
) -> str:
    """Shadow set_tunable: records the proposed write but does NOT push to
    the dispatcher. Stored as a single-waypoint row in setpoint_plan_shadow
    keyed by a synthetic plan_id so the diff job can attribute the change
    to the originating trigger."""
    if not trigger_id:
        return json.dumps({"error": "trigger_id is required"})
    try:
        normalized_trigger = str(UUID(trigger_id))
    except (TypeError, ValueError):
        return json.dumps({"error": "trigger_id must be a valid UUID"})

    synthetic_plan_id = f"shadow-tunable-{normalized_trigger}-{parameter}"
    conn = await _db()
    try:
        await conn.execute(
            """
            INSERT INTO setpoint_plan_shadow (ts, parameter, value, plan_id, reason)
            VALUES (now(), $1, $2, $3, $4)
            ON CONFLICT (ts, parameter, plan_id) DO UPDATE
              SET value = EXCLUDED.value, reason = EXCLUDED.reason
            """,
            parameter,
            float(value),
            synthetic_plan_id,
            reason or f"shadow set_tunable {parameter}={value}",
        )
        return _json(
            {
                "ok": True,
                "shadow": True,
                "parameter": parameter,
                "value": value,
                "synthetic_plan_id": synthetic_plan_id,
            }
        )
    finally:
        await conn.close()


@mcp_shadow.tool()
async def acknowledge_trigger(trigger_id: str, reason: str, planner_instance: str | None = None) -> str:
    """Shadow acknowledge — recorded in plan_delivery_log_shadow only.
    Production plan_delivery_log is untouched."""
    if not trigger_id:
        return json.dumps({"error": "trigger_id is required"})
    try:
        normalized_trigger = str(UUID(trigger_id))
    except (TypeError, ValueError):
        return json.dumps({"error": "trigger_id must be a valid UUID"})

    conn = await _db()
    try:
        await conn.execute(
            """
            INSERT INTO plan_delivery_log_shadow
              (event_type, event_label, trigger_id, instance, gateway_body)
            VALUES ('SHADOW_ACK', $1, $2::uuid, $3, $4)
            """,
            reason[:200],
            normalized_trigger,
            planner_instance,
            f"shadow acknowledge: {reason[:1500]}",
        )
        return _json({"ok": True, "shadow": True, "acknowledged": True})
    finally:
        await conn.close()


@mcp_shadow.tool()
async def plan_evaluate(plan_id: str, outcome_score: int, actual_outcome: str, lesson_extracted: str = "") -> str:
    """Shadow plan_evaluate: writes to plan_journal_shadow + computes the
    deterministic anchor_score against the SHADOW plan's governed window.
    Lessonization is recorded in lesson_extracted but does NOT insert into
    production planner_lessons — the shadow week's lesson_extracted is
    diffed against the prod row instead."""
    conn = await _db()
    try:
        existing = await conn.fetchval("SELECT plan_id FROM plan_journal_shadow WHERE plan_id = $1", plan_id)
        if not existing:
            return json.dumps({"error": f"shadow plan '{plan_id}' not found"})

        anchor_score = None
        try:
            anchor_score = await conn.fetchval(
                # Use the production scorecard function on the shadow plan's
                # interval window. If the shadow plan doesn't match a real
                # interval (no successor), this returns NULL.
                "SELECT fn_plan_anchor_score($1)",
                plan_id,
            )
        except Exception:
            pass

        await conn.execute(
            """
            UPDATE plan_journal_shadow SET
              outcome_score = $2, actual_outcome = $3, lesson_extracted = $4,
              anchor_score  = $5, validated_at = now()
             WHERE plan_id = $1
            """,
            plan_id,
            int(outcome_score),
            actual_outcome,
            lesson_extracted or None,
            anchor_score,
        )

        return _json(
            {
                "ok": True,
                "shadow": True,
                "plan_id": plan_id,
                "outcome_score": int(outcome_score),
                "anchor_score": anchor_score,
            }
        )
    finally:
        await conn.close()


@mcp_shadow.tool()
async def lessons_manage(action: str, lesson_id: int = 0, data: str = "") -> str:
    """Shadow lessons_manage — recorded in plan_delivery_log_shadow.gateway_body
    as JSON breadcrumbs. We do not mutate production planner_lessons during
    the shadow week; any lessons the shadow gateway would have created get
    counted in the diff report instead."""
    payload = {"action": action, "lesson_id": lesson_id, "data": data}
    conn = await _db()
    try:
        await conn.execute(
            """
            INSERT INTO plan_delivery_log_shadow
              (event_type, event_label, gateway_body)
            VALUES ('SHADOW_LESSON', $1, $2)
            """,
            f"lessons_manage:{action}",
            json.dumps(payload)[:2000],
        )
        return _json({"ok": True, "shadow": True, "recorded": payload})
    finally:
        await conn.close()


# ── Read tools: re-export from the production server unchanged ──────────


def _wire_read_tools_from_production() -> None:
    """Import the production MCP server's read tool functions and re-register
    them on `mcp_shadow`. We don't touch the write tools — those are
    explicitly reimplemented above to redirect to shadow tables."""
    from mcp import server as prod_server  # type: ignore

    # FastMCP doesn't expose a public re-register hook, so we lean on the
    # decorator path: each production read tool is already decorated with
    # @mcp.tool() against its FastMCP instance. The shadow server registers
    # its own decorated functions referencing the production logic.
    read_tool_names = (
        "climate",
        "scorecard",
        "equipment_state",
        "forecast",
        "get_setpoints",
        "plan_status",
        "lessons",
        "lessons_search",
        "knowledge_search",
        "history",
        "alerts",
        "crops",
        "observations",
        "topology",
        "position_current",
        "crop_history",
        "crop_lifecycle",
    )
    for name in read_tool_names:
        fn = getattr(prod_server, name, None)
        if fn is None:
            print(f"[shadow] read tool {name!r} not found in production server, skipping", file=sys.stderr)
            continue
        # Strip prod's @mcp.tool() registration metadata and re-decorate against shadow.
        # FastMCP tool functions are async; wrap them transparently.
        wrapper = _make_passthrough(fn)
        wrapper.__name__ = name
        wrapper.__doc__ = fn.__doc__
        mcp_shadow.tool()(wrapper)


def _make_passthrough(fn):
    async def _inner(*args, **kwargs):
        return await fn(*args, **kwargs)

    return _inner


# Wire on import so the shadow server is fully registered before mcp.run().
_wire_read_tools_from_production()


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    os.environ.setdefault("MCP_HTTP_HOST", "127.0.0.1")
    os.environ.setdefault("MCP_HTTP_PORT", "8001")
    mcp_shadow.run(transport="streamable-http")
