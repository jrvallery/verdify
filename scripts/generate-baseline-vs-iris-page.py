#!/usr/bin/env python3
"""Generate the public Baseline vs Iris evidence pages."""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

OUT_PATHS = (
    Path("/mnt/iris/verdify-vault/website/evidence/baseline-vs-iris.md"),
    Path("/mnt/iris/verdify-vault/website/data/baseline-vs-iris.md"),
)
DB = ["docker", "exec", "verdify-timescaledb", "psql", "-U", "verdify", "-d", "verdify"]

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
    COALESCE(ds.stress_hours_heat, 0) + COALESCE(ds.stress_hours_cold, 0)
      + COALESCE(ds.stress_hours_vpd_high, 0) + COALESCE(ds.stress_hours_vpd_low, 0) AS stress_h,
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

CONFOUNDER_SQL = r"""
WITH periods AS (
  SELECT
    'Planner offline window'::text AS period,
    1 AS sort_order,
    TIMESTAMPTZ '2026-04-22 00:00 America/Denver' AS start_ts,
    TIMESTAMPTZ '2026-04-26 00:00 America/Denver' AS end_ts
  UNION ALL
  SELECT
    'Iris online window',
    2,
    TIMESTAMPTZ '2026-04-26 00:00 America/Denver',
    TIMESTAMPTZ '2026-05-03 00:00 America/Denver'
), climate_calc AS (
  SELECT
    p.period,
    p.sort_order,
    c.outdoor_temp_f,
    c.solar_irradiance_w_m2,
    0.6108 * exp(
      (17.27 * ((c.outdoor_temp_f - 32) * 5 / 9))
      / (((c.outdoor_temp_f - 32) * 5 / 9) + 237.3)
    ) * (1 - c.outdoor_rh_pct / 100.0) AS outdoor_vpd
  FROM periods p
  JOIN climate c ON c.ts >= p.start_ts
    AND c.ts < p.end_ts
  WHERE c.outdoor_temp_f IS NOT NULL
    AND c.outdoor_rh_pct IS NOT NULL
), manual_counts AS (
  SELECT
    p.period,
    p.sort_order,
    (SELECT count(*) FROM crop_events ce WHERE ce.ts >= p.start_ts AND ce.ts < p.end_ts) AS crop_events
  FROM periods p
)
SELECT
  cc.period,
  round(avg(cc.outdoor_temp_f)::numeric, 1) AS outdoor_temp_avg_f,
  round(max(cc.outdoor_temp_f)::numeric, 1) AS outdoor_temp_max_f,
  round(avg(cc.outdoor_vpd)::numeric, 2) AS outdoor_vpd_avg_kpa,
  round(avg(cc.solar_irradiance_w_m2)::numeric, 0) AS solar_avg_w_m2,
  max(mc.crop_events) AS crop_events
FROM climate_calc cc
JOIN manual_counts mc USING (period, sort_order)
GROUP BY cc.period, cc.sort_order
ORDER BY cc.sort_order;
"""

DAILY_SQL = r"""
SELECT
  ds.date,
  (SELECT count(*) FROM plan_journal pj WHERE (pj.created_at AT TIME ZONE 'America/Denver')::date = ds.date) AS plans,
  round(ds.compliance_pct::numeric, 1) AS both_axis,
  round(ds.temp_compliance_pct::numeric, 1) AS temp_axis,
  round(ds.vpd_compliance_pct::numeric, 1) AS vpd_axis,
  round((COALESCE(ds.stress_hours_heat, 0) + COALESCE(ds.stress_hours_cold, 0)
    + COALESCE(ds.stress_hours_vpd_high, 0) + COALESCE(ds.stress_hours_vpd_low, 0))::numeric, 1) AS stress_h,
  round(COALESCE(ds.stress_hours_vpd_high, 0)::numeric, 1) AS vpd_high_h,
  round(COALESCE(ds.stress_hours_heat, 0)::numeric, 1) AS heat_h,
  round(ds.cost_total::numeric, 2) AS cost_usd,
  round(COALESCE(vp.planner_score, 0)::numeric, 1) AS planner_score
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
class Confounders:
    label: str
    outdoor_temp_avg_f: str
    outdoor_temp_max_f: str
    outdoor_vpd_avg_kpa: str
    solar_avg_w_m2: str
    crop_events: str


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
        [*DB, "-X", "-v", "ON_ERROR_STOP=1", "-t", "-A", "-F", "\t", "-c", sql],
        text=True,
        check=True,
        capture_output=True,
    )
    return [row for row in csv.reader(proc.stdout.splitlines(), delimiter="\t") if row]


def as_periods() -> list[Period]:
    rows = psql(PERIOD_SQL)
    if len(rows) != 2:
        raise RuntimeError(f"Expected 2 period rows, got {len(rows)}")
    return [Period(*row) for row in rows]


def as_confounders() -> list[Confounders]:
    rows = psql(CONFOUNDER_SQL)
    if len(rows) != 2:
        raise RuntimeError(f"Expected 2 confounder rows, got {len(rows)}")
    return [Confounders(*row) for row in rows]


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


def render(periods: list[Period], confounders: list[Confounders], daily: list[Daily]) -> str:
    baseline, current = periods
    base_conf, current_conf = confounders
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
title: "AI Greenhouse Baseline vs Iris"
description: "A launch-safe operational comparison between the April 22-25 planner-offline window and the following Iris-online window."
tags: [evidence, planning, scorecard, baseline]
date: 2026-05-03
type: evidence
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

# Baseline vs Iris

This is an operational comparison, not a controlled A/B test, and it does not isolate Iris as the only variable. The baseline window is the April 22-25, 2026 planner-offline run already documented in the public outage story. The comparison window is April 26-May 2, 2026, when normal Iris planning resumed.

The comparison is still useful because it answers the launch question a skeptical reader will ask first: when the planning loop is online, do the public scorecards look different from the period where the ESP32 had to keep running without normal AI plans?

For the exact parameters Iris can change when it is online, see [AI-Writable Tunables](/reference/planning-loop/#ai-writable-tunables).

For the broader caveat language, see the [Launch FAQ](/reference/faq/#does-verdify-claim-better-yield-or-profit). For the live receipts behind this page, use [Planning Quality](/data/planning-quality/), [Operations](/data/operations/), and the [planning archive](/data/plans/).

## Periods Compared

<div class="metric-grid">
  <div class="metric-card"><strong>{baseline.start} to {baseline.end}</strong><p>{baseline.label}: {baseline.days} days, {baseline.avg_plans} Iris plans/day.</p></div>
  <div class="metric-card"><strong>{current.start} to {current.end}</strong><p>{current.label}: {current.days} days, {current.avg_plans} Iris plans/day.</p></div>
</div>

## Summary Table

<div class="data-table">
{metric_rows}
</div>

## Confounders To Keep In View

This comparison is useful, but it is not weather-normalized proof that Iris caused every improvement. The Iris-online window was cooler, more humid, and lower-solar on average, which likely made VPD and heat stress easier. The table below makes those confounders explicit instead of burying them in caveats.

<div class="data-table">
  <div class="data-row"><strong>Outdoor temperature</strong><span>{base_conf.outdoor_temp_avg_f}°F avg / {base_conf.outdoor_temp_max_f}°F max -> {current_conf.outdoor_temp_avg_f}°F avg / {current_conf.outdoor_temp_max_f}°F max</span><p>The Iris-online window was cooler, reducing heat-load pressure.</p></div>
  <div class="data-row"><strong>Outdoor VPD / humidity</strong><span>{base_conf.outdoor_vpd_avg_kpa} kPa avg -> {current_conf.outdoor_vpd_avg_kpa} kPa avg</span><p>The Iris-online window had less dry-air pressure, so VPD compliance was easier to recover.</p></div>
  <div class="data-row"><strong>Solar irradiance</strong><span>{base_conf.solar_avg_w_m2} W/m² avg -> {current_conf.solar_avg_w_m2} W/m² avg</span><p>Lower solar load reduces overheating and evaporative demand.</p></div>
  <div class="data-row"><strong>Manual interventions</strong><span>{base_conf.crop_events} logged crop events -> {current_conf.crop_events} logged crop events</span><p>Logged event counts are shown explicitly, but operator activity is not controlled like a lab experiment.</p></div>
  <div class="data-row"><strong>Hardware changes</strong><span>No major hardware change is asserted here</span><p>The comparison uses the same greenhouse and controller boundary, but it is not a locked hardware trial.</p></div>
  <div class="data-row"><strong>Crop mix / active bands</strong><span>Same public crop-control model, plants still aging</span><p>Crop targets are comparable enough for an operational receipt, not for yield attribution or agronomic proof.</p></div>
</div>

## Visual Evidence

The two graphs below use the exact comparison span, April 22 through May 2, 2026. They are the clearest visual read on the claim: during the planner-offline days, compliance was lower and stress-category hours were higher; after Iris resumed, the scorecard generally moved in the right direction. The charts still do not prove causality because weather and operator activity were not held constant.

<div class="pg s2">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-planning-quality/?orgId=1&panelId=10&theme=dark&from=1776837600000&to=1777788000000" width="100%" height="320" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-planning-quality/?orgId=1&panelId=20&theme=dark&from=1776837600000&to=1777788000000" width="100%" height="320" frameborder="0"></iframe>

</div>

## Resource Tradeoffs

The comparison is more useful when stress is shown beside what the greenhouse spent trying to reduce it. These existing planning-quality panels use the public 30-day scorecard context, which includes both the April 22-25 outage window and the April 26-May 2 Iris-online window.

<div class="pg s2">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-planning-quality/?orgId=1&panelId=15&theme=dark&from=now-30d&to=now" width="100%" height="320" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-planning-quality/?orgId=1&panelId=16&theme=dark&from=now-30d&to=now" width="100%" height="320" frameborder="0"></iframe>

</div>

Cost, water, and misting are not success metrics by themselves. They matter because an AI planner can improve the headline score only if it reduces plant stress without hiding the resource bill.

## Daily Rows

<div class="data-table">
{daily_rows}
</div>

## Definitions

<div class="data-table">
  <div class="data-row"><strong>Both-axis compliance</strong><span><code>daily_summary.compliance_pct</code></span><p>Percent of samples where temperature and VPD were both inside the active crop band.</p></div>
  <div class="data-row"><strong>Cumulative stress-axis hours/day</strong><span>Heat + cold + VPD-high + VPD-low</span><p>Summed daily stress duration from corrected daily summary fields. This is not capped at one stress type; a hot-dry hour can count on more than one axis.</p></div>
  <div class="data-row"><strong>Planner score</strong><span><code>v_planner_performance.planner_score</code></span><p>Composite score: 80% compliance and 20% cost efficiency. It is useful as an operational KPI, not as a yield claim.</p></div>
  <div class="data-row"><strong>Metered electric energy/day</strong><span><code>daily_summary.kwh_total</code></span><p>Electric energy from the greenhouse power meter where available, with runtime estimates kept as a separate diagnostic.</p></div>
  <div class="data-row"><strong>Cost/day</strong><span>Electric + gas + water</span><p>Resource spend comes from estimated daily summary fields unless marked measured. The greenhouse is solar-aligned but still uses grid electricity and gas heat.</p></div>
</div>

## Caveats

- Weather, crop load, hardware state, and operator activity were not identical across the two windows.
- The baseline is a real outage window, not a hand-picked fixed-rule controller experiment.
- The strongest claim is not that Iris guarantees better outcomes every day. The useful claim is that the system makes planner availability, physical stress, cost, and score visible enough to audit.
- This is not a yield, profit, or controlled-trial claim. It is a launch-safe operational receipt; see the [FAQ](/reference/faq/#does-verdify-claim-better-yield-or-profit) for the claim boundary.
- Known physical and instrumentation limits still apply, including weather, sensor coverage, water attribution, and firmware-change risk. See [Known Limits](/reference/known-limits/) and [Firmware Change Protocol](/reference/firmware-change-protocol/).

## Reproducibility

This page is generated by `scripts/generate-baseline-vs-iris-page.py` from `daily_summary`, `plan_journal`, `v_planner_performance`, `climate`, and `crop_events`.

For raw launch-safe data, use the [7-day climate CSV](/static/data/verdify-sample-7d-climate.csv), [30-day plan outcomes CSV](/static/data/verdify-sample-30d-plan-outcomes.csv), and [dataset notes](/static/data/verdify-sample-readme.txt). The current public snapshot is available from the [evidence snapshot API](https://api.verdify.ai/api/v1/public/evidence-snapshot).

## Where To Go Next

- [Why the AI Does Not Control Relays](/reference/safety/) explains the safety split behind the outage window.
- [Planning Loop](/reference/planning-loop/) shows how Iris writes hypotheses and waypoints.
- [AI-Writable Tunables](/reference/planning-loop/#ai-writable-tunables) lists the bounded control surface behind those waypoints.
- [Planning Quality](/data/planning-quality/) shows the live scorecard and forecast-plan-outcome panels.
- [Generated Lessons](/reference/lessons/) shows what the planner reads before future plans.
- [Data Model](/reference/data-model/) explains the tables, views, and sample exports behind this comparison.
"""


def write_outputs(markdown: str) -> None:
    for path in OUT_PATHS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
        print(f"Wrote {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="fail if generated pages differ from the checked-in vault output"
    )
    parser.add_argument("--stdout", action="store_true", help="print generated Markdown instead of writing files")
    args = parser.parse_args()

    markdown = render(as_periods(), as_confounders(), as_daily())
    if args.stdout:
        print(markdown)
        return 0

    if args.check:
        stale = [path for path in OUT_PATHS if path.read_text(encoding="utf-8") != markdown]
        if stale:
            print("Baseline vs Iris page is stale:", ", ".join(str(path) for path in stale), file=sys.stderr)
            return 1
        return 0

    write_outputs(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
