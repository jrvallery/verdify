#!/usr/bin/env /srv/greenhouse/.venv/bin/python3
"""Normalize Grafana dashboard JSON units, labels, colors, and known SQL drift."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

DEFAULT_ROOTS = [
    Path("grafana/dashboards"),
    Path("grafana/provisioning/dashboards/json"),
    Path("/mnt/iris/verdify/grafana/dashboards"),
    Path("/mnt/iris/verdify/grafana/provisioning/dashboards/json"),
]

ENTITY_COLORS = {
    "Indoor": "#73BF69",
    "Actual Indoor Temp": "#73BF69",
    "Actual Indoor VPD": "#73BF69",
    "Outdoor": "#8C8C8C",
    "Outdoor Temp": "#8C8C8C",
    "Outdoor RH": "#8C8C8C",
    "Outdoor VPD": "#8C8C8C",
    "Forecast": "#42A5F5",
    "Forecast Temp (°F)": "#42A5F5",
    "Setpoint High": "#EF5350",
    "Setpoint Low": "#42A5F5",
    "Band High": "#EF5350",
    "Band Low": "#42A5F5",
    "VPD High": "#EF5350",
    "VPD Low": "#42A5F5",
    "South": "#EF5350",
    "South VPD": "#EF5350",
    "North": "#42A5F5",
    "North VPD": "#42A5F5",
    "East": "#AB47BC",
    "East VPD": "#AB47BC",
    "West": "#66BB6A",
    "West VPD": "#66BB6A",
    "Center": "#E040FB",
    "Heat 1": "#FF9800",
    "Heat 2": "#F4511E",
    "Fan 1": "#26A69A",
    "Fan 2": "#5C6BC0",
    "Vent": "#FFCA28",
    "Fog": "#00ACC1",
    "Mister South": "#CE93D8",
    "Mister West": "#F48FB1",
    "Mister Center": "#E040FB",
    "Drip Wall": "#4DB6AC",
    "Drip Center": "#4FC3F7",
    "Grow Light": "#9CCC65",
    "Grow Light Main": "#9CCC65",
    "Grow Light Grow": "#C6FF00",
    "Electric": "#FF9800",
    "Gas": "#F44336",
    "Water": "#2196F3",
    "Sensor DLI": "#FFA726",
    "DLI Today": "#FFA726",
    "Estimated Plant DLI": "#73BF69",
    "Reference DLI": "#8C8C8C",
    "Target DLI": "#8C8C8C",
    "Solar (W/m²)": "#FFA726",
    "Solar W/m²": "#FFA726",
    "Outdoor Lux": "#FDD835",
    "Temp Compliance %": "#EF5350",
    "VPD Compliance %": "#42A5F5",
    "Total Compliance %": "#73BF69",
    "Temp Stress Hours": "#EF5350",
    "VPD Stress Hours": "#42A5F5",
    "Total Stress Hours": "#FFB74D",
    "Total Stress-Category Hours": "#FFB74D",
}


def flatten_panels(panels: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for panel in panels or []:
        if panel.get("type") == "row":
            out.extend(flatten_panels(panel.get("panels")))
        elif "id" in panel:
            out.append(panel)
    return out


def text_for_panel(panel: dict[str, Any], extra: str = "") -> str:
    target_text = " ".join(str(t.get("rawSql") or t.get("expr") or "") for t in panel.get("targets") or [])
    return f"{panel.get('title') or ''} {panel.get('description') or ''} {target_text} {extra}".lower()


def set_axis_label(panel: dict[str, Any], label: str) -> None:
    custom = panel.setdefault("fieldConfig", {}).setdefault("defaults", {}).setdefault("custom", {})
    if isinstance(custom, dict):
        custom["axisLabel"] = label


def normalize_unit(unit: Any, panel: dict[str, Any], field_name: str = "") -> Any:
    if not isinstance(unit, str):
        return unit
    text = text_for_panel(panel, field_name)
    title = str(panel.get("title") or "").lower()
    if unit in {"°F", "degF"}:
        return "fahrenheit"
    if unit == "%":
        return "percent"
    if unit in {"kPa", "pressurekPa", "pressurePascal"} and "vpd" in text:
        return "pressurekpa"
    if unit == "kPa":
        return "pressurekpa"
    if unit == "gpm":
        return "gal/min"
    if unit == "gallons":
        return "gal"
    if unit == "kWh":
        return "kwatth"
    if unit == "deckbytes":
        return "kbytes"
    if unit == "watt" and any(word in text for word in ("irradiance", "solar_w_m2", "solar_irradiance_w_m2", "w/m")):
        return "watt/m²"
    if unit in {"none", "short"} and "dli" in text:
        return "mol/m²/d"
    if unit == "h":
        if "solar noon altitude" in title:
            return "degree"
        if any(word in text for word in ("hour", "hrs", "runtime", "stress", "plan age", "uptime", "gl hours")):
            set_axis_label(panel, "Hours")
            return "short"
        if any(word in text for word in ("transition", "writes", "oscillation", "cycles", "unique states")):
            return "short"
    return unit


def color_property(value: str) -> dict[str, str]:
    return {"fixedColor": value, "mode": "fixed"}


def normalize_overrides(panel: dict[str, Any]) -> bool:
    changed = False
    overrides = panel.setdefault("fieldConfig", {}).setdefault("overrides", [])
    if not isinstance(overrides, list):
        return False
    for override in overrides:
        matcher = override.get("matcher") or {}
        name = str(matcher.get("options") or "")
        props = override.setdefault("properties", [])
        if not isinstance(props, list):
            continue
        for prop in props:
            if prop.get("id") == "unit":
                new_unit = normalize_unit(prop.get("value"), panel, name)
                if new_unit != prop.get("value"):
                    prop["value"] = new_unit
                    changed = True
            if prop.get("id") == "color" and name in ENTITY_COLORS:
                new_color = color_property(ENTITY_COLORS[name])
                if prop.get("value") != new_color:
                    prop["value"] = new_color
                    changed = True
    existing_color_matchers = {
        str((override.get("matcher") or {}).get("options") or "")
        for override in overrides
        if (override.get("matcher") or {}).get("id") == "byName"
    }
    target_names = set()
    for target in panel.get("targets") or []:
        raw = str(target.get("rawSql") or "")
        target_names.update(re.findall(r'AS\s+"([^"]+)"', raw, flags=re.IGNORECASE))
    for name in sorted(target_names & set(ENTITY_COLORS) - existing_color_matchers):
        overrides.append(
            {
                "matcher": {"id": "byName", "options": name},
                "properties": [{"id": "color", "value": color_property(ENTITY_COLORS[name])}],
            }
        )
        changed = True
    return changed


def normalize_defaults(panel: dict[str, Any]) -> bool:
    defaults = panel.setdefault("fieldConfig", {}).setdefault("defaults", {})
    if not isinstance(defaults, dict):
        return False
    old_unit = defaults.get("unit")
    new_unit = normalize_unit(old_unit, panel)
    changed = new_unit != old_unit
    if changed:
        defaults["unit"] = new_unit
    if panel.get("type") == "timeseries":
        custom = defaults.setdefault("custom", {})
        if isinstance(custom, dict):
            if "lineWidth" not in custom:
                custom["lineWidth"] = 2
                changed = True
            if "spanNulls" not in custom:
                custom["spanNulls"] = True
                changed = True
            if defaults.get("unit") == "pressurekpa" and not custom.get("axisLabel"):
                custom["axisLabel"] = "kPa"
                changed = True
            if defaults.get("unit") == "fahrenheit" and not custom.get("axisLabel"):
                custom["axisLabel"] = "°F"
                changed = True
    return changed


def stress_sql(title: str, parameter: str) -> str | None:
    if parameter == "vpd_high":
        label = "VPD Stress Hours"
        expr = "COALESCE(stress_hours_vpd_high,0) + COALESCE(stress_hours_vpd_low,0)"
    elif parameter == "temp_high":
        label = "Heat Stress Hours"
        expr = "COALESCE(stress_hours_heat,0)"
    elif parameter == "temp_low":
        label = "Cold Stress Hours"
        expr = "COALESCE(stress_hours_cold,0)"
    else:
        return None
    if "stress" not in title.lower():
        return None
    return (
        "SELECT (date + time '12:00')::timestamptz AS time, "
        f'ROUND(({expr})::numeric, 2) AS "{label}" '
        "FROM daily_summary "
        "WHERE $__timeFilter((date + time '12:00')::timestamptz) "
        "ORDER BY date"
    )


def normalize_sql(sql: str, panel: dict[str, Any]) -> str:
    original = sql
    sql = sql.replace("avg(score::numeric)", "avg(outcome_score::numeric)")
    sql = sql.replace("c.avg(temp_avg) OVER (ORDER BY ts", "avg(c.temp_avg) OVER (ORDER BY c.ts")
    sql = sql.replace("c.avg(vpd_avg) OVER (ORDER BY ts", "avg(c.vpd_avg) OVER (ORDER BY c.ts")
    sql = sql.replace("c.avg(temp_avg) OVER (ORDER BY c.ts", "avg(c.temp_avg) OVER (ORDER BY c.ts")
    sql = sql.replace("c.avg(vpd_avg) OVER (ORDER BY c.ts", "avg(c.vpd_avg) OVER (ORDER BY c.ts")
    sql = sql.replace(
        "SELECT date_trunc('month', ts) AS time, sum(cost_total_usd) AS \"Monthly Cost\" "
        "FROM daily_summary WHERE ts > now() - interval '365 days' GROUP BY 1 ORDER BY 1",
        "SELECT date_trunc('month', date)::timestamptz AS time, "
        'sum(cost_total) AS "Monthly Cost" '
        "FROM daily_summary WHERE date >= CURRENT_DATE - 365 GROUP BY 1 ORDER BY 1",
    )
    sql = sql.replace(
        'SELECT ts AS time, cumulative_gallons_today AS "Water Today" '
        "FROM diagnostics WHERE ts > now() - interval '14 days' ORDER BY 1",
        'SELECT ts AS time, mister_water_today AS "Mister Water Today" '
        "FROM climate WHERE ts > now() - interval '14 days' "
        "AND mister_water_today IS NOT NULL ORDER BY 1",
    )
    sql = sql.replace(
        "v_mister_effectiveness WHERE zone='south'", "v_mister_effectiveness WHERE equipment='mister_south'"
    )
    sql = sql.replace(
        "v_mister_effectiveness WHERE zone='west'", "v_mister_effectiveness WHERE equipment='mister_west'"
    )
    sql = sql.replace(
        "v_mister_effectiveness WHERE zone='center'", "v_mister_effectiveness WHERE equipment='mister_center'"
    )
    sql = re.sub(r"AND cost_total > 0\\b", "AND cost_total IS NOT NULL", sql)
    sql = re.sub(r"WHERE cost_total > 0\\b", "WHERE cost_total IS NOT NULL", sql)
    if "FROM setpoint_changes" in original and "Stress" in str(panel.get("title") or ""):
        match = re.search(r"parameter\s*=\s*'([^']+)'", original)
        if match:
            replacement = stress_sql(str(panel.get("title") or ""), match.group(1))
            if replacement:
                sql = replacement
    return sql


def normalize_panel(panel: dict[str, Any]) -> bool:
    changed = False
    title = str(panel.get("title") or "")
    if title.startswith("REVIEW — "):
        panel["title"] = title.removeprefix("REVIEW — ")
        changed = True
    if title == "Planner Stress Hours — Temp, VPD, Total":
        panel["title"] = "Planner Stress-Category Hours — Temp, VPD, Total"
        for target in panel.get("targets") or []:
            raw = target.get("rawSql")
            if isinstance(raw, str):
                target["rawSql"] = raw.replace('"Total Stress Hours"', '"Total Stress-Category Hours"')
                changed = True
    changed = normalize_defaults(panel) or changed
    changed = normalize_overrides(panel) or changed
    for target in panel.get("targets") or []:
        raw = target.get("rawSql")
        if isinstance(raw, str):
            new_raw = normalize_sql(raw, panel)
            if new_raw != raw:
                target["rawSql"] = new_raw
                changed = True
    return changed


def normalize_dashboard(path: Path) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    dashboard = data.get("dashboard") if isinstance(data.get("dashboard"), dict) else data
    changed = False
    for panel in flatten_panels(dashboard.get("panels")):
        changed = normalize_panel(panel) or changed
    if changed:
        path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return changed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", type=Path, default=DEFAULT_ROOTS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    changed: list[Path] = []
    for root in args.roots:
        if root.is_file() and root.suffix == ".json":
            if normalize_dashboard(root):
                changed.append(root)
            continue
        if not root.exists():
            continue
        for path in sorted(root.glob("*.json")):
            if normalize_dashboard(path):
                changed.append(path)
    for path in changed:
        print(path)
    print(f"changed: {len(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
