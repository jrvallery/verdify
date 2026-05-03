#!/usr/bin/env python3
"""Generate the public Baseline vs Iris evidence page."""

from __future__ import annotations

import csv
import subprocess
from dataclasses import dataclass
from pathlib import Path

OUT = Path("/mnt/iris/verdify-vault/website/evidence/baseline-vs-iris.md")
DB = ["docker", "exec", "-i", "verdify-timescaledb", "psql", "-U", "verdify", "-d", "verdify"]

PERIOD_SQL = r"""
WITH periods AS (
  SELECT 'Planner offline window'::text AS period, 1 AS sort_order, DATE '2026-04-22' AS start_date, DATE '2026-04-25' AS end_date
  UNION ALL
  SELECT 'Iris online window', 2, DATE '2026-04-26', DATE '2026-05-02'
), day_metrics AS (
  SELECT
    p.period,
    p.sort_order,
    ds.date,
    ds.compliance_pct,
    ds.temp_compliance_pct,
    ds.vpd_compliance_pct,
    COALESCE(ds.stress_hours_heat,0) + COALESCE(ds.stress_hours_cold,0) + COALESCE(ds.stress_hours_vpd_high,0) + COALESCE(ds.stress_hours_vpd_low,0) AS stress_h,
    ds.water_used_gal,
    ds.kwh_total,
    ds.cost_total,
    vp.planner_score,
    (SELECT count(*) FROM plan_journal pj WHERE (pj.created_at AT TIME ZONE 'America/Denver')::date = ds.date) AS plans
  FROM periods p
  JOIN daily_summary ds ON ds.date BETWEEN p.start_date AND p.end_date
  LEFT JOIN v_planner_performance vp ON vp.date = ds.date
)
SELECT
  period,
  min(date) AS start_date,
  max(date) AS end_date,
  count(*) AS days,
  round(avg(plans)::numeric, 1) AS avg_plans_day,
  round(avg(compliance_pct)::numeric, 1) AS both_axis_compliance_pct,
  round(avg(temp_compliance_pct)::numeric, 1) AS temp_compliance_pct,
  round(avg(vpd_compliance_pct)::numeric, 1) AS vpd_compliance_pct,
  round(avg(stress_h)::numeric, 1) AS stress_hours_day,
  round(avg(water_used_gal)::numeric, 1) AS water_gal_day,
  round(avg(kwh_total)::numeric, 1) AS kwh_day,
  round(avg(cost_total)::numeric, 2) AS cost_day_usd,
  round(avg(planner_score)::numeric, 1) AS planner_score
FROM day_metrics
GROUP BY period, sort_order
ORDER BY sort_order;
"""

DAILY_SQL = r"""
SELECT
  ds.date,
  (SELECT count(*) FROM plan_journal pj WHERE (pj.created_at AT TIME ZONE 'America/Denver')::date = ds.date) AS plans,
  round(ds.compliance_pct::numeric,1) AS both_axis,
  round(ds.temp_compliance_pct::numeric,1) AS temp_axis,
  round(ds.vpd_compliance_pct::numeric,1) AS vpd_axis,
  round((COALESCE(ds.stress_hours_heat,0)+COALESCE(ds.stress_hours_cold,0)+COALESCE(ds.stress_hours_vpd_high,0)+COALESCE(ds.stress_hours_vpd_low,0))::numeric,1) AS stress_h,
  round(COALESCE(ds.stress_hours_vpd_high,0)::numeric,1) AS vpd_high_h,
  round(COALESCE(ds.stress_hours_heat,0)::numeric,1) AS heat_h,
  round(ds.cost_total::numeric,2) AS cost_usd,
  round(COALESCE(vp.planner_score,0)::numeric,1) AS planner_score
FROM daily_summary ds
LEFT JOIN v_planner_performance vp ON vp.date = ds.date
WHERE ds.date BETWEEN DATE '2026-04-22' AND DATE '2026-05-02'
ORDER BY ds.date;
"""


@dataclass(frozen=True)
class Period:
    label: str
    start: str
    end: str
    days: str
    avg_plans: str
    both_axis: str
    temp_axis: str
    vpd_axis: str
    stress_h: str
    water_gal: str
    kwh: str
    cost_usd: str
    score: str


@dataclass(frozen=True)
class Daily:
    date: str
    plans: str
    both_axis: str
    temp_axis: str
    vpd_axis: str
    stress_h: str
    vpd_high_h: str
    heat_h: str
    cost_usd: str
    score: str


def psql(sql: str) -> list[list[str]]:
    proc = subprocess.run(
        [*DB, "-t", "-A", "-F", "\t"],
        input=sql,
        text=True,
        check=True,
        capture_output=True,
    )
    return [row for row in csv.reader(proc.stdout.splitlines(), delimiter="\t") if row]


def as_periods() -> list[Period]:
    return [Period(*row) for row in psql(PERIOD_SQL)]


def as_daily() -> list[Daily]:
    return [Daily(*row) for row in psql(DAILY_SQL)]


def fmt_delta(current: str, baseline: str, suffix: str = "") -> str:
    cur = float(current)
    base = float(baseline)
    delta = cur - base
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.1f}{suffix}"


def fmt_reduction(current: str, baseline: str, suffix: str = "") -> str:
    cur = float(current)
    base = float(baseline)
    delta = base - cur
    if delta >= 0:
        return f"{delta:.1f}{suffix} lower"
    return f"{abs(delta):.1f}{suffix} higher"


def fmt_reduction_usd(current: str, baseline: str) -> str:
    cur = float(current)
    base = float(baseline)
    delta = base - cur
    if delta >= 0:
        return f"USD {delta:.2f} lower"
    return f"USD {abs(delta):.2f} higher"


def render(periods: list[Period], daily: list[Daily]) -> str:
    baseline, current = periods
    rows = [
        (
            "Average Iris plans/day",
            baseline.avg_plans,
            current.avg_plans,
            fmt_delta(current.avg_plans, baseline.avg_plans),
        ),
        (
            "Both-axis compliance",
            f"{baseline.both_axis}%",
            f"{current.both_axis}%",
            fmt_delta(current.both_axis, baseline.both_axis, " pts"),
        ),
        (
            "Temperature compliance",
            f"{baseline.temp_axis}%",
            f"{current.temp_axis}%",
            fmt_delta(current.temp_axis, baseline.temp_axis, " pts"),
        ),
        (
            "VPD compliance",
            f"{baseline.vpd_axis}%",
            f"{current.vpd_axis}%",
            fmt_delta(current.vpd_axis, baseline.vpd_axis, " pts"),
        ),
        (
            "Cumulative stress-axis hours/day",
            f"{baseline.stress_h}h",
            f"{current.stress_h}h",
            fmt_reduction(current.stress_h, baseline.stress_h, "h"),
        ),
        (
            "Water/day",
            f"{baseline.water_gal} gal",
            f"{current.water_gal} gal",
            fmt_reduction(current.water_gal, baseline.water_gal, " gal"),
        ),
        (
            "Estimated electric energy/day",
            f"{baseline.kwh} kWh",
            f"{current.kwh} kWh",
            fmt_reduction(current.kwh, baseline.kwh, " kWh"),
        ),
        (
            "Cost/day",
            f"USD {baseline.cost_usd}",
            f"USD {current.cost_usd}",
            fmt_reduction_usd(current.cost_usd, baseline.cost_usd),
        ),
        ("Planner score", baseline.score, current.score, fmt_delta(current.score, baseline.score)),
    ]
    metric_rows = "\n".join(
        f'  <div class="data-row"><strong>{metric}</strong><span>{base} -> {cur}</span><p>{delta}</p></div>'
        for metric, base, cur, delta in rows
    )
    daily_rows = "\n".join(
        f'  <div class="data-row"><strong>{d.date}</strong><span>{d.plans} plans - {d.both_axis}% both-axis - {d.score} score</span><p>{d.stress_h}h stress, {d.vpd_high_h}h VPD-high, {d.heat_h}h heat, USD {d.cost_usd}</p></div>'
        for d in daily
    )
    return f"""---
title: \"AI Greenhouse Baseline vs Iris\"
description: \"A launch-safe operational comparison between the April 22-25 planner-offline window and the following Iris-online window.\"
tags: [evidence, planning, scorecard, baseline]
date: 2026-05-03
type: evidence
---

# Baseline vs Iris

This is an operational comparison, not a controlled A/B test, and it does not isolate Iris as the only variable. The baseline window is the April 22-25, 2026 planner-offline run already documented in the public outage story. The comparison window is April 26-May 2, 2026, when normal Iris planning resumed.

The comparison is still useful because it answers the launch question a skeptical reader will ask first: when the planning loop is online, do the public scorecards look different from the period where the ESP32 had to keep running without normal AI plans?

## Periods Compared

<div class=\"metric-grid\">
  <div class=\"metric-card\"><strong>{baseline.start} to {baseline.end}</strong><p>{baseline.label}: {baseline.days} days, {baseline.avg_plans} Iris plans/day.</p></div>
  <div class=\"metric-card\"><strong>{current.start} to {current.end}</strong><p>{current.label}: {current.days} days, {current.avg_plans} Iris plans/day.</p></div>
</div>

## Summary Table

<div class=\"data-table\">
{metric_rows}
</div>

## Daily Rows

<div class=\"data-table\">
{daily_rows}
</div>

## Definitions

<div class=\"data-table\">
  <div class=\"data-row\"><strong>Both-axis compliance</strong><span><code>daily_summary.compliance_pct</code></span><p>Percent of samples where temperature and VPD were both inside the active crop band.</p></div>
  <div class=\"data-row\"><strong>Cumulative stress-axis hours/day</strong><span>Heat + cold + VPD-high + VPD-low</span><p>Summed daily stress duration from corrected daily summary fields. This is not capped at one stress type; a hot-dry hour can count on more than one axis.</p></div>
  <div class=\"data-row\"><strong>Planner score</strong><span><code>v_planner_performance.planner_score</code></span><p>Composite score: 80% compliance and 20% cost efficiency. It is useful as an operational KPI, not as a yield claim.</p></div>
  <div class=\"data-row\"><strong>Estimated electric energy/day</strong><span><code>daily_summary.kwh_total</code></span><p>Electric energy from the daily summary estimate. Treat it as an operational KPI, not a utility-grade billing statement.</p></div>
  <div class=\"data-row\"><strong>Cost/day</strong><span>Electric + gas + water</span><p>Resource spend comes from estimated daily summary fields unless marked measured. The greenhouse is solar-aligned but still uses grid electricity and gas heat.</p></div>
</div>

## Caveats

- Weather, crop load, hardware state, and operator activity were not identical across the two windows.
- The baseline is a real outage window, not a hand-picked fixed-rule controller experiment.
- The strongest claim is not that Iris guarantees better outcomes every day. The useful claim is that the system makes planner availability, physical stress, cost, and score visible enough to audit.

## Reproducibility

This page is generated by `scripts/generate-baseline-vs-iris-page.py` from `daily_summary`, `plan_journal`, and `v_planner_performance`.

For raw launch-safe data, use the [7-day climate CSV](/static/data/verdify-sample-7d-climate.csv), [30-day plan outcomes CSV](/static/data/verdify-sample-30d-plan-outcomes.csv), and [dataset notes](/static/data/verdify-sample-readme.txt).

## Where To Go Next

- [Why the AI Does Not Control Relays](/intelligence/safety-architecture/) explains the safety split behind the outage window.
- [Planning Loop](/intelligence/planning/) shows how Iris writes hypotheses and waypoints.
- [Planning Quality](/evidence/planning-quality/) shows the live scorecard and forecast-plan-outcome panels.
- [Generated Lessons](/greenhouse/lessons/) shows what the planner reads before future plans.
- [Data Model](/intelligence/data/) explains the tables, views, and sample exports behind this comparison.
"""


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(as_periods(), as_daily()), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
