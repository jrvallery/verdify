#!/usr/bin/env /srv/greenhouse/.venv/bin/python3
"""Sprint 20 Phase 7: generate /website/forecast/index.md from
weather_forecast + fn_forecast_correction + forecast_deviation_log.

Validated through verdify_schemas.ForecastHour so malformed DB rows are
caught at the boundary. Invoked by:
  - systemd timer verdify-forecast-page.timer (every 30 min)
  - manual `python3 scripts/generate-forecast-page.py`

Output: /mnt/iris/verdify-vault/website/forecast/index.md
        (picked up by the Quartz poll-timer within 10 s)
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from html import escape
from pathlib import Path

sys.path.insert(0, "/mnt/iris/verdify")
import yaml  # noqa: E402

from verdify_schemas import ForecastHour, ForecastVaultFrontmatter  # noqa: E402

OUT_PATH = Path("/mnt/iris/verdify-vault/website/forecast/index.md")


def _data_table(rows: list[tuple[str, str, str]]) -> str:
    if not rows:
        return '<div class="metric-grid">\n  <div class="metric-card"><strong>No data</strong><p>No rows available.</p></div>\n</div>'
    lines = ['<div class="data-table">']
    for title, meta, body in rows:
        lines.append(
            f'  <div class="data-row"><strong>{escape(str(title))}</strong>'
            f"<span>{escape(str(meta))}</span><p>{escape(str(body))}</p></div>"
        )
    lines.append("</div>")
    return "\n".join(lines)


def psql(sql: str, timeout: int = 45) -> list[list[str]]:
    result = subprocess.run(
        [
            "docker",
            "exec",
            "verdify-timescaledb",
            "psql",
            "-U",
            "verdify",
            "-d",
            "verdify",
            "-t",
            "-A",
            "-F",
            "|",
            "-c",
            sql,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )
    rows = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        rows.append(line.split("|"))
    return rows


def _hourly_72h() -> list[ForecastHour]:
    """Latest-fetched hourly rows from now through +72 h."""
    sql = """
        SELECT DISTINCT ON (ts) ts, fetched_at, temp_f, rh_pct, vpd_kpa,
               solar_w_m2, cloud_cover_pct, wind_speed_mph, precip_prob_pct,
               weather_code
          FROM weather_forecast
         WHERE fetched_at = (SELECT max(fetched_at) FROM weather_forecast)
           AND ts > now()
           AND ts < now() + interval '72 hours'
         ORDER BY ts, fetched_at DESC
    """
    rows = psql(sql)
    hours: list[ForecastHour] = []
    for r in rows:
        if len(r) < 10:
            continue
        try:
            # psql emits '2026-04-19 01:00:00+00' — normalize to ISO for fromisoformat.
            ts = datetime.fromisoformat(r[0].replace(" ", "T"))
            fetched = datetime.fromisoformat(r[1].replace(" ", "T"))
            hours.append(
                ForecastHour.model_validate(
                    {
                        "ts": ts,
                        "fetched_at": fetched,
                        "temp_f": float(r[2]) if r[2] else None,
                        "rh_pct": float(r[3]) if r[3] else None,
                        "vpd_kpa": float(r[4]) if r[4] else None,
                        "solar_w_m2": float(r[5]) if r[5] else None,
                        "cloud_cover_pct": float(r[6]) if r[6] else None,
                        "wind_speed_mph": float(r[7]) if r[7] else None,
                        "precip_prob_pct": float(r[8]) if r[8] else None,
                        "weather_code": int(r[9]) if r[9] else None,
                    },
                ),
            )
        except Exception as exc:  # noqa: S112 — best-effort forecast parse; log and move on
            print(f"skipping forecast row (ts={r[0]!r}): {exc}", file=sys.stderr)
            continue
    return hours


def _daily_4to7() -> list[dict]:
    """Daily rollup for days 4–7 out: low, high, min RH, max precip, avg VPD."""
    sql = """
        SELECT (ts AT TIME ZONE 'America/Denver')::date AS day,
               round(min(temp_f)::numeric, 1) AS low,
               round(max(temp_f)::numeric, 1) AS high,
               round(min(rh_pct)::numeric, 0) AS rh_min,
               round(max(precip_prob_pct)::numeric, 0) AS precip_max,
               round(avg(vpd_kpa)::numeric, 2) AS vpd_avg,
               round(avg(cloud_cover_pct)::numeric, 0) AS cloud_avg
          FROM weather_forecast
         WHERE fetched_at = (SELECT max(fetched_at) FROM weather_forecast)
           AND ts >= now() + interval '72 hours'
           AND ts < now() + interval '7 days'
         GROUP BY 1 ORDER BY 1
    """
    rows = psql(sql)
    return [
        {"day": r[0], "low": r[1], "high": r[2], "rh_min": r[3], "precip_max": r[4], "vpd_avg": r[5], "cloud_avg": r[6]}
        for r in rows
        if len(r) >= 7
    ]


def _bias_correction() -> dict[str, tuple[str, str]]:
    """7-day rolling bias correction per forecast parameter."""
    out = {}
    for p in ("temp_f", "rh_pct", "solar_w_m2"):
        rows = psql(f"SELECT avg_error, samples FROM fn_forecast_correction('{p}', 24)")
        if rows and rows[0][0]:
            out[p] = (rows[0][0], rows[0][1])
    return out


def _recent_deviations() -> list[list[str]]:
    """Last 10 triggered deviation events."""
    sql = """
        SELECT to_char(ts AT TIME ZONE 'America/Denver', 'MM-DD HH24:MI') AS t,
               parameter,
               round(observed::numeric, 1) AS observed,
               round(forecasted::numeric, 1) AS forecast,
               round(delta::numeric, 1) AS delta
          FROM forecast_deviation_log
         WHERE triggered = true
         ORDER BY ts DESC
         LIMIT 10
    """
    return psql(sql)


def _render(hours: list[ForecastHour], daily: list[dict], bias: dict, deviations: list) -> str:
    denver_now = datetime.now(UTC).astimezone()
    # Sprint 22: frontmatter validated through ForecastVaultFrontmatter.
    fm = ForecastVaultFrontmatter(
        date=denver_now.date(),
        tags=["forecast", "auto-generated"],
        last_updated=denver_now.isoformat(timespec="seconds"),
    )
    yaml_block = yaml.safe_dump(
        fm.model_dump(mode="json", exclude_none=True),
        sort_keys=False,
        default_flow_style=None,
    )
    lines = [
        "---",
        yaml_block.rstrip(),
        "---",
        "",
        "# Forecast",
        "",
        "*This page regenerates every 30 minutes from the latest Open-Meteo sync. "
        "Open-Meteo's biases are tracked and reported below; apply them to the raw "
        "numbers for a more accurate expectation.*",
        "",
        "## Bias correction (7-day rolling)",
        "",
    ]
    if bias:
        interp = {
            "temp_f": "Open-Meteo under/over-predicts temp",
            "rh_pct": "Open-Meteo under/over-predicts RH",
            "solar_w_m2": "Open-Meteo under/over-predicts solar radiation",
        }
        rows = []
        for p, (err, n) in bias.items():
            rows.append((p, f"avg error {err}; {n} samples", interp.get(p, "")))
        lines.append(_data_table(rows))
    else:
        lines.append("*No bias correction available — not enough observation/forecast overlap yet.*")

    lines.extend(
        [
            "",
            "## Hourly — next 72 h",
            "",
        ]
    )
    hourly_rows = []
    for h in hours:
        ts_local = h.ts.astimezone().strftime("%m-%d %H:%M")
        hourly_rows.append(
            (
                ts_local,
                f"{h.temp_f or '—'}°F; RH {h.rh_pct or '—'}%; VPD {h.vpd_kpa or '—'} kPa",
                f"Solar {h.solar_w_m2 or '—'} W/m²; cloud {h.cloud_cover_pct or '—'}%; wind {h.wind_speed_mph or '—'} mph; precip {h.precip_prob_pct or '—'}%.",
            )
        )
    lines.append(_data_table(hourly_rows))

    lines.extend(
        [
            "",
            "## Days 4–7 outlook",
            "",
        ]
    )
    daily_rows = []
    for d in daily:
        daily_rows.append(
            (
                d["day"],
                f"{d['low']}–{d['high']}°F; RH min {d['rh_min']}%",
                f"Precip max {d['precip_max']}%; VPD avg {d['vpd_avg']} kPa; cloud avg {d['cloud_avg']}%.",
            )
        )
    lines.append(_data_table(daily_rows))

    lines.extend(
        [
            "",
            "## Recent forecast misses",
            "",
            "Last 10 deviations where observed outdoor conditions diverged far enough from the "
            "latest forecast to trigger a replan.",
            "",
        ]
    )
    if deviations:
        rows = []
        for d in deviations:
            rows.append((d[0], d[1], f"Observed {d[2]}; forecast {d[3]}; delta {d[4]}."))
        lines.append(_data_table(rows))
    else:
        lines.append(
            '<div class="metric-grid">\n  <div class="metric-card"><strong>No recent deviations</strong><p>No triggered deviations in the recent log.</p></div>\n</div>'
        )

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    rows = psql("SELECT count(*) FROM weather_forecast")
    if not rows or int(rows[0][0]) == 0:
        print("No weather_forecast rows available — skipping.")
        return
    hours = _hourly_72h()
    daily = _daily_4to7()
    bias = _bias_correction()
    deviations = _recent_deviations()
    body = _render(hours, daily, bias, deviations)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Only rewrite if content changed — saves unnecessary site rebuilds.
    old = OUT_PATH.read_text() if OUT_PATH.exists() else ""
    if old != body:
        OUT_PATH.write_text(body)
        print(f"Wrote {OUT_PATH} ({len(body)} chars; {len(hours)} hourly rows, {len(daily)} daily rows)")
    else:
        print(f"No change; {OUT_PATH} unchanged ({len(hours)} hourly rows)")


if __name__ == "__main__":
    main()
