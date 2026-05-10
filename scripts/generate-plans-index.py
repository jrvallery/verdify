#!/usr/bin/env /srv/greenhouse/.venv/bin/python3
"""Regenerate plans/index.md and data/plans/index.md from DB summaries."""

from __future__ import annotations

import re
import subprocess
from datetime import date
from pathlib import Path

CONTENT_ROOT = Path("/srv/verdify/verdify-site/content")
INDEX = CONTENT_ROOT / "plans" / "index.md"
DATA_INDEX = CONTENT_ROOT / "data" / "plans" / "index.md"
DB_CMD = ["docker", "exec", "verdify-timescaledb", "psql", "-U", "verdify", "-d", "verdify", "-t", "-A", "-F", "|"]


def db_rows(sql: str) -> list[list[str]]:
    result = subprocess.run([*DB_CMD, "-c", sql], capture_output=True, text=True, timeout=15, check=True)
    return [row.split("|") for row in result.stdout.strip().splitlines() if row.strip()]


def default_header(today: date) -> str:
    return f"""---
title: AI Greenhouse Planning Archive
description: "Daily archive and monthly summary of Iris, Verdify's AI greenhouse planner: experiments, scorecards, climate stress, costs, and lessons from each planning cycle."
tags: [plans, greenhouse, ai]
date: {today}
cssclasses:
  - hide-folder-listing
---

# AI Greenhouse Planning Archive

Iris normally runs up to three planning cycles per day. Missed cycles are intentionally visible in this archive, because planner availability is part of the system being audited.

The individual daily pages are generated records, not polished articles. The important story is what the AI planned, what the greenhouse actually experienced, how much stress remained, and what the next plan learned.

To understand the exact parameters behind the plan rows, see [AI-Writable Tunables](/reference/planning-loop/#ai-writable-tunables).

*Generated planning archive: daily pages are lab notebook records. Pending rows and missed cycles stay visible because planner availability is part of the evidence.*

## What the Archive Shows

<div class="metric-grid">
  <div class="metric-card"><strong>Plan frequency</strong><span>Up to 3 cycles/day</span><p>Morning, midday, and evening plans adjust temperature, VPD, misting, fog, ventilation, heat, and lighting tactics.</p></div>
  <div class="metric-card"><strong>Scorecard feedback</strong><span>Outcome-driven</span><p>Daily summaries compare stress hours, compliance, resource use, and experimental outcomes.</p></div>
  <div class="metric-card"><strong>Learning loop</strong><span>Validated lessons</span><p>Useful findings graduate into generated lessons that the planner reads before future cycles.</p></div>
</div>

---"""


def existing_header(today: date) -> str:
    if not INDEX.exists():
        return default_header(today)
    text = INDEX.read_text(encoding="utf-8")
    header = re.split(r"^## (?:Recent Plans|All Plans)$", text, maxsplit=1, flags=re.MULTILINE)[0].strip()
    if not header:
        return default_header(today)
    header = re.sub(r"^date: .*$", f"date: {today}", header, flags=re.MULTILINE)
    header = header.replace(
        "/intelligence/planning/#ai-writable-tunables", "/reference/planning-loop/#ai-writable-tunables"
    )
    if "Generated planning archive" not in header:
        header = header.replace(
            "## What the Archive Shows",
            "*Generated planning archive: daily pages are lab notebook records. Pending rows and missed cycles stay visible because planner availability is part of the evidence.*\n\n## What the Archive Shows",
        )
    return header.rstrip()


def render(rows: list[list[str]], today: date) -> str:
    lines = [
        existing_header(today),
        "",
        "## All Plans",
        "",
        "| Date | Plans | Temp Range | VPD Stress | Cost | Experiment | Score |",
        "|------|-------|------------|------------|------|------------|-------|",
    ]
    for row in rows:
        if len(row) < 7:
            continue
        d, plans, temp_range, vpd, cost, experiment, score = [item.strip() for item in row[:7]]
        lines.append(
            f"| [{d}](/plans/{d}) | {plans} | {temp_range}°F | {vpd}h | ${cost} | {experiment[:40]} | {score} |"
        )
    lines.extend(
        [
            "",
            "---",
            "",
            "*Auto-generated from daily_summary + plan_journal data. Archive rows are generated lab notebook entries; null or pending fields mean the day is still in progress or the source row was not recorded.*",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    rows = db_rows(
        """
        SELECT ds.date,
          (SELECT COUNT(*) FROM plan_journal pj
           WHERE pj.plan_id LIKE 'iris-' || to_char(ds.date, 'YYYYMMDD') || '%') AS plans,
          ROUND(COALESCE(ds.temp_min,0)::numeric,0) || '-' || ROUND(COALESCE(ds.temp_max,0)::numeric,0) AS temp_range,
          ROUND(COALESCE(ds.stress_hours_vpd_high,0)::numeric,1) AS vpd_stress,
          ROUND(COALESCE(ds.cost_total,0)::numeric,2) AS cost,
          COALESCE((SELECT LEFT(pj.experiment, 50) FROM plan_journal pj
            WHERE pj.plan_id LIKE 'iris-' || to_char(ds.date, 'YYYYMMDD') || '%'
            ORDER BY pj.created_at DESC LIMIT 1), '-') AS experiment,
          COALESCE((SELECT pj.outcome_score::text FROM plan_journal pj
            WHERE pj.plan_id LIKE 'iris-' || to_char(ds.date, 'YYYYMMDD') || '%'
            AND pj.outcome_score IS NOT NULL
            ORDER BY pj.created_at DESC LIMIT 1), '-') AS score
        FROM daily_summary ds
        WHERE ds.date >= '2026-03-24'
        ORDER BY ds.date DESC
        """
    )
    output = render(rows, date.today())
    for path in (INDEX, DATA_INDEX):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output, encoding="utf-8")
    print(f"Plans index: {len(rows)} days -> plans/index.md and data/plans/index.md")


if __name__ == "__main__":
    main()
