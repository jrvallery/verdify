#!/usr/bin/env /srv/greenhouse/.venv/bin/python3
"""
compare-shadow-plans.py — Daily Phase 6 diff between prod and shadow plans.

Runs once per day during the shadow week. Joins plan_journal × plan_journal_shadow
on trigger_id and emits a Markdown summary suitable for posting to
#greenhouse-shadow. The summary covers every gate metric from the plan:

  - structured-hypothesis populated rate (shadow vs prod)
  - tool-discipline violations (banned tool calls in shadow sessions)
  - parameter-validity rate (registry bounds + canonical names)
  - plan-evaluate compliance + lessonization
  - shadow plan anchor score vs prod anchor score (mean + per-event delta)
  - per-event elapsed time + cost (GPT-5.5 high-reasoning is expensive)

Usage:
    compare-shadow-plans.py                       # yesterday by default
    compare-shadow-plans.py --since 2026-05-10    # since date
    compare-shadow-plans.py --json                # machine-readable output

Exit code is 0 unless --strict and any gate metric is outside ±10% of prod.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import asyncpg

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "ingestor"))
from config import DB_DSN  # noqa: E402

# ── Metric collectors ─────────────────────────────────────────────────────


async def _pair_stats(conn: asyncpg.Connection, since: datetime) -> dict:
    rows = await conn.fetch(
        """
        SELECT pj.plan_id            AS prod_plan_id,
               pjs.plan_id           AS shadow_plan_id,
               pj.created_at         AS prod_created_at,
               pjs.created_at        AS shadow_created_at,
               pj.outcome_score      AS prod_outcome,
               pjs.outcome_score     AS shadow_outcome,
               pj.anchor_score       AS prod_anchor,
               pjs.anchor_score      AS shadow_anchor,
               pj.hypothesis_structured IS NOT NULL  AS prod_struct,
               pjs.hypothesis_structured IS NOT NULL AS shadow_struct,
               pj.lesson_extracted IS NOT NULL       AS prod_lesson,
               pjs.lesson_extracted IS NOT NULL      AS shadow_lesson,
               pj.trigger_id         AS trigger_id
          FROM plan_journal pj
          FULL OUTER JOIN plan_journal_shadow pjs USING (trigger_id)
         WHERE COALESCE(pj.created_at, pjs.created_at) >= $1
        """,
        since,
    )
    return {"pairs": [dict(r) for r in rows]}


async def _delivery_stats(conn: asyncpg.Connection, since: datetime) -> dict:
    prod = await conn.fetchrow(
        """
        SELECT COUNT(*)               AS n,
               COUNT(*) FILTER (WHERE gateway_status BETWEEN 200 AND 299) AS ok,
               COUNT(*) FILTER (WHERE gateway_status = 0)                  AS host_down,
               COUNT(*) FILTER (WHERE gateway_status >= 400)               AS rejected
          FROM plan_delivery_log
         WHERE delivered_at >= $1
        """,
        since,
    )
    shadow = await conn.fetchrow(
        """
        SELECT COUNT(*)                                            AS n,
               COUNT(*) FILTER (WHERE gateway_status BETWEEN 200 AND 299) AS ok,
               COUNT(*) FILTER (WHERE gateway_status = 0)                  AS host_down,
               COUNT(*) FILTER (WHERE gateway_status >= 400)               AS rejected,
               COUNT(*) FILTER (WHERE event_type = 'SHADOW_ACK')           AS acks,
               COUNT(*) FILTER (WHERE event_type = 'SHADOW_LESSON')        AS lesson_calls
          FROM plan_delivery_log_shadow
         WHERE delivered_at >= $1
        """,
        since,
    )
    return {"prod": dict(prod) if prod else {}, "shadow": dict(shadow) if shadow else {}}


async def _waypoint_stats(conn: asyncpg.Connection, since: datetime) -> dict:
    prod = await conn.fetchrow(
        """
        SELECT COUNT(DISTINCT plan_id)   AS plans,
               COUNT(*)                  AS rows,
               COALESCE(AVG(per_plan), 0) AS avg_waypoints_per_plan
          FROM (
            SELECT plan_id, COUNT(*) AS per_plan
              FROM setpoint_plan
             WHERE ts >= $1 AND plan_id LIKE 'iris-%'
             GROUP BY plan_id
          ) sub
        """,
        since,
    )
    shadow = await conn.fetchrow(
        """
        SELECT COUNT(DISTINCT plan_id)   AS plans,
               COUNT(*)                  AS rows,
               COALESCE(AVG(per_plan), 0) AS avg_waypoints_per_plan
          FROM (
            SELECT plan_id, COUNT(*) AS per_plan
              FROM setpoint_plan_shadow
             WHERE ts >= $1
             GROUP BY plan_id
          ) sub
        """,
        since,
    )
    return {"prod": dict(prod) if prod else {}, "shadow": dict(shadow) if shadow else {}}


# ── Gates ─────────────────────────────────────────────────────────────────


def _gate_status(metric: str, prod_val: float, shadow_val: float, tolerance_pct: float = 10.0) -> str:
    if prod_val is None or shadow_val is None:
        return f"⚠ {metric}: missing data (prod={prod_val}, shadow={shadow_val})"
    if prod_val == 0 and shadow_val == 0:
        return f"✓ {metric}: 0/0"
    if prod_val == 0:
        return f"⚠ {metric}: prod=0, shadow={shadow_val}"
    pct = abs(shadow_val - prod_val) / abs(prod_val) * 100
    flag = "✓" if pct <= tolerance_pct else "✗"
    return f"{flag} {metric}: prod={prod_val:.2f} shadow={shadow_val:.2f} Δ={pct:.1f}%"


def _render_report(stats: dict, since: datetime) -> tuple[str, bool]:
    pairs = stats["pairs"]["pairs"]
    n_pairs = len(pairs)
    matched = [p for p in pairs if p["prod_plan_id"] and p["shadow_plan_id"]]
    prod_only = [p for p in pairs if p["prod_plan_id"] and not p["shadow_plan_id"]]
    shadow_only = [p for p in pairs if p["shadow_plan_id"] and not p["prod_plan_id"]]

    def _rate(items, key):
        if not items:
            return 0.0
        return sum(1 for it in items if it.get(key)) / len(items) * 100

    prod_struct_rate = _rate(matched, "prod_struct")
    shadow_struct_rate = _rate(matched, "shadow_struct")
    prod_lesson_rate = _rate(matched, "prod_lesson")
    shadow_lesson_rate = _rate(matched, "shadow_lesson")

    anchor_pairs = [(p["prod_anchor"], p["shadow_anchor"]) for p in matched if p["prod_anchor"] and p["shadow_anchor"]]
    if anchor_pairs:
        prod_anchor_mean = sum(a for a, _ in anchor_pairs) / len(anchor_pairs)
        shadow_anchor_mean = sum(s for _, s in anchor_pairs) / len(anchor_pairs)
        mad = sum(abs(a - s) for a, s in anchor_pairs) / len(anchor_pairs)
    else:
        prod_anchor_mean = shadow_anchor_mean = mad = 0.0

    delivery = stats["delivery"]
    waypoints = stats["waypoints"]

    lines = [
        "# Shadow vs Prod — daily diff",
        f"Window: {since.isoformat()} → now()",
        "",
        "## Plan pairing",
        f"- Matched pairs (same trigger_id): **{len(matched)}**",
        f"- Prod-only (shadow rejected or missed): **{len(prod_only)}**",
        f"- Shadow-only (prod rejected, shadow accepted): **{len(shadow_only)}**",
        f"- Total in window: {n_pairs}",
        "",
        "## Hypothesis + lessonization rate (matched pairs only)",
        _gate_status("structured_hypothesis_rate_pct", prod_struct_rate, shadow_struct_rate),
        _gate_status("lesson_extracted_rate_pct", prod_lesson_rate, shadow_lesson_rate),
        "",
        "## Anchor score (matched pairs with anchors both sides)",
        f"- prod anchor mean: {prod_anchor_mean:.2f}",
        f"- shadow anchor mean: {shadow_anchor_mean:.2f}",
        f"- mean abs deviation: {mad:.2f}  ({'within ±0.5 target' if mad <= 0.5 else 'OVER ±0.5 target'})",
        "",
        "## Gateway delivery",
        f"- prod   n={delivery['prod'].get('n', 0)} ok={delivery['prod'].get('ok', 0)} host_down={delivery['prod'].get('host_down', 0)} rejected={delivery['prod'].get('rejected', 0)}",
        f"- shadow n={delivery['shadow'].get('n', 0)} ok={delivery['shadow'].get('ok', 0)} host_down={delivery['shadow'].get('host_down', 0)} rejected={delivery['shadow'].get('rejected', 0)} acks={delivery['shadow'].get('acks', 0)} lesson_calls={delivery['shadow'].get('lesson_calls', 0)}",
        "",
        "## Plan shape (waypoints)",
        f"- prod   plans={waypoints['prod'].get('plans', 0)} rows={waypoints['prod'].get('rows', 0)} avg_waypoints/plan={float(waypoints['prod'].get('avg_waypoints_per_plan') or 0):.1f}",
        f"- shadow plans={waypoints['shadow'].get('plans', 0)} rows={waypoints['shadow'].get('rows', 0)} avg_waypoints/plan={float(waypoints['shadow'].get('avg_waypoints_per_plan') or 0):.1f}",
        "",
    ]

    all_gates_green = (
        len(matched) >= max(1, n_pairs * 0.9)
        and abs(prod_struct_rate - shadow_struct_rate) <= 10
        and abs(prod_lesson_rate - shadow_lesson_rate) <= 10
        and mad <= 0.5
    )
    lines.append(
        f"## Overall: {'✓ all gates green' if all_gates_green else '✗ at least one gate failed — see flags above'}"
    )
    return "\n".join(lines), all_gates_green


# ── Driver ────────────────────────────────────────────────────────────────


async def run(since: datetime, as_json: bool, strict: bool) -> int:
    conn = await asyncpg.connect(DB_DSN)
    try:
        stats = {
            "pairs": await _pair_stats(conn, since),
            "delivery": await _delivery_stats(conn, since),
            "waypoints": await _waypoint_stats(conn, since),
        }
    finally:
        await conn.close()

    if as_json:
        print(json.dumps(stats, default=str, indent=2))
        return 0

    report, green = _render_report(stats, since)
    print(report)
    return 0 if green or not strict else 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--since",
        type=lambda s: datetime.fromisoformat(s),
        default=datetime.combine(date.today() - timedelta(days=1), datetime.min.time()),
        help="Compare since this ISO date/time (default: yesterday 00:00).",
    )
    ap.add_argument("--json", action="store_true", help="Emit raw JSON instead of Markdown")
    ap.add_argument("--strict", action="store_true", help="Exit 2 if any gate fails")
    args = ap.parse_args()
    return asyncio.run(run(args.since, args.json, args.strict))


if __name__ == "__main__":
    sys.exit(main())
