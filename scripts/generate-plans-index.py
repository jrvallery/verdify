#!/usr/bin/env /srv/greenhouse/.venv/bin/python3
"""generate-plans-index.py — Regenerate plans/index.md with summary stats table."""

import subprocess
from datetime import date
from html import escape
from pathlib import Path

CONTENT_DIR = Path("/srv/verdify/verdify-site/content/plans")
DB_CMD = "docker exec verdify-timescaledb psql -U verdify -d verdify -t -A"


def db_rows(sql):
    r = subprocess.run(f'{DB_CMD} -c "{sql}"', shell=True, capture_output=True, text=True, timeout=15)
    return [row.split("|") for row in r.stdout.strip().split("\n") if row.strip()]


def main():
    rows = db_rows("""
        SELECT ds.date,
            (SELECT COUNT(*) FROM plan_journal pj WHERE pj.plan_id LIKE 'iris-' || to_char(ds.date, 'YYYYMMDD') || '%') AS cycles,
            ROUND(COALESCE(ds.stress_hours_vpd_high,0)::numeric,1) AS vpd_stress,
            ROUND(COALESCE(ds.stress_hours_heat,0)::numeric,1) AS heat_stress,
            ROUND(COALESCE(ds.cost_total,0)::numeric,2) AS cost,
            ROUND(COALESCE(ds.temp_max,0)::numeric,0) AS temp_max,
            COALESCE((SELECT LEFT(pj.experiment, 50) FROM plan_journal pj WHERE pj.plan_id LIKE 'iris-' || to_char(ds.date, 'YYYYMMDD') || '%' ORDER BY pj.created_at DESC LIMIT 1), '-') AS experiment,
            COALESCE((SELECT pj.outcome_score::text FROM plan_journal pj WHERE pj.plan_id LIKE 'iris-' || to_char(ds.date, 'YYYYMMDD') || '%' AND pj.outcome_score IS NOT NULL ORDER BY pj.created_at DESC LIMIT 1), '-') AS score
        FROM daily_summary ds
        WHERE ds.date >= '2026-03-24'
        ORDER BY ds.date DESC
    """)

    lines = [
        "---",
        "title: Daily Plans",
        "tags: [plans, greenhouse, ai]",
        f"date: {date.today()}",
        "---",
        "",
        "# Daily Plans",
        "",
        "Every day, Iris runs 3 planning cycles (6 AM, 12 PM, 6 PM MDT) to manage greenhouse setpoints.",
        "",
        "---",
        "",
        "## Recent Plans",
        "",
        '<div class="data-table">',
    ]

    for row in rows:
        if len(row) >= 8:
            d = row[0].strip()
            link = f'<a href="/plans/{d}/">{escape(d)}</a>'
            experiment = row[6].strip()[:80]
            lines.append(
                f'  <div class="data-row"><strong>{link}</strong>'
                f"<span>{escape(row[1].strip())} cycles; score {escape(row[7].strip())}; cost ${escape(row[4].strip())}</span>"
                f"<p>VPD stress {escape(row[2].strip())}h; heat stress {escape(row[3].strip())}h; "
                f"peak {escape(row[5].strip())}°F. Experiment: {escape(experiment)}.</p></div>"
            )

    lines.extend(
        [
            "</div>",
            "",
            "---",
            "",
            "*Auto-generated from daily_summary + plan_journal data.*",
        ]
    )

    (CONTENT_DIR / "index.md").write_text("\n".join(lines))
    print(f"Plans index: {len(rows)} days")


if __name__ == "__main__":
    main()
