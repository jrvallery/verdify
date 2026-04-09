#!/usr/bin/env python3
"""
Grafana Dashboard Style Standardizer

Applies the homepage (site-home.json) visual style to all site-* dashboards:
- Rolling averages (15-row temp, 30-row VPD)
- Crop band fills (fn_band_setpoints)
- Equipment cascade dots at fixed Y positions
- Solar irradiance golden gradient background
- Consistent colors, tooltip, legend settings

Usage:
    python3 standardize-dashboards.py [--dry-run] [--phase N]
"""

import json
import copy
import sys
import os
from pathlib import Path

DASHBOARD_DIR = Path("/srv/verdify/provisioning/dashboards/json")

# ─── Canonical datasource ────────────────────────────────────────────
DS = {"type": "grafana-postgresql-datasource", "uid": "verdify-tsdb"}

# ─── Canonical SQL templates ─────────────────────────────────────────

SQL_ROLLING_TEMP = """SELECT ts AS time,
    avg(temp_avg) OVER (ORDER BY ts ROWS BETWEEN 14 PRECEDING AND CURRENT ROW) AS "Indoor"
FROM climate
WHERE $__timeFilter(ts) AND ts <= now() AND temp_avg IS NOT NULL
ORDER BY ts"""

SQL_ROLLING_VPD = """SELECT ts AS time,
    avg(vpd_avg) OVER (ORDER BY ts ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS "Indoor VPD"
FROM climate
WHERE $__timeFilter(ts) AND ts <= now() AND vpd_avg IS NOT NULL
ORDER BY ts"""

SQL_OUTDOOR_TEMP_FORECAST = """(SELECT ts AS time, outdoor_temp_f AS "Outdoor Forecast"
 FROM climate WHERE outdoor_temp_f IS NOT NULL ORDER BY ts DESC LIMIT 1)
UNION ALL
(SELECT DISTINCT ON (date_trunc('hour', ts))
     date_trunc('hour', ts) AS time,
     temp_f::float AS "Outdoor Forecast"
 FROM weather_forecast
 WHERE ts > now() AND ts < now() + interval '72 hours'
 ORDER BY date_trunc('hour', ts), fetched_at DESC)
ORDER BY time"""

SQL_OUTDOOR_TEMP = """SELECT ts AS time, outdoor_temp_f AS "Outdoor"
FROM climate
WHERE $__timeFilter(ts) AND ts <= now() AND outdoor_temp_f IS NOT NULL
ORDER BY ts"""

SQL_OUTDOOR_VPD_FORECAST = """(SELECT ts AS time,
     (0.6108 * EXP(17.27 * ((outdoor_temp_f-32)/1.8) / (((outdoor_temp_f-32)/1.8)+237.3)) * (1.0 - outdoor_rh_pct/100.0))::float AS "Outdoor VPD Forecast"
 FROM climate WHERE outdoor_temp_f IS NOT NULL AND outdoor_rh_pct IS NOT NULL ORDER BY ts DESC LIMIT 1)
UNION ALL
(SELECT DISTINCT ON (date_trunc('hour', ts))
     date_trunc('hour', ts) AS time,
     vpd_kpa::float AS "Outdoor VPD Forecast"
 FROM weather_forecast
 WHERE ts > now() AND ts < now() + interval '72 hours'
 ORDER BY date_trunc('hour', ts), fetched_at DESC)
ORDER BY time"""

SQL_OUTDOOR_VPD = """SELECT ts AS time,
    (0.6108 * EXP(17.27 * ((outdoor_temp_f-32)/1.8) / (((outdoor_temp_f-32)/1.8)+237.3)) * (1.0 - outdoor_rh_pct/100.0))::float AS "Outdoor VPD"
FROM climate
WHERE $__timeFilter(ts) AND ts <= now() AND outdoor_temp_f IS NOT NULL AND outdoor_rh_pct IS NOT NULL
ORDER BY ts"""

SQL_TEMP_BAND = """WITH timeline AS (
    SELECT generate_series($__timeFrom(), $__timeTo(), interval '30 minutes') AS ts
)
SELECT t.ts AS time,
    (fn_band_setpoints(t.ts)).temp_low::float AS "Band Low",
    (fn_band_setpoints(t.ts)).temp_high::float AS "Band High"
FROM timeline t ORDER BY t.ts"""

SQL_VPD_BAND = """WITH timeline AS (
    SELECT generate_series($__timeFrom(), $__timeTo(), interval '30 minutes') AS ts
)
SELECT t.ts AS time,
    (fn_band_setpoints(t.ts)).vpd_low::float AS "Band Low",
    (fn_band_setpoints(t.ts)).vpd_high::float AS "Band High"
FROM timeline t ORDER BY t.ts"""

SQL_SOLAR_OBSERVED = 'SELECT ts AS time, solar_irradiance_w_m2 AS "Solar W/m\u00b2" FROM climate WHERE $__timeFilter(ts) AND solar_irradiance_w_m2 IS NOT NULL ORDER BY ts'

SQL_SOLAR_FORECAST = """(SELECT ts AS time, solar_irradiance_w_m2 AS "Solar Forecast"
FROM climate WHERE solar_irradiance_w_m2 IS NOT NULL ORDER BY ts DESC LIMIT 1)
UNION ALL
(SELECT DISTINCT ON (date_trunc('hour', ts))
    date_trunc('hour', ts) AS time, solar_w_m2 AS "Solar Forecast"
FROM weather_forecast WHERE ts > now() AND ts < now() + interval '72 hours'
ORDER BY date_trunc('hour', ts), fetched_at DESC)
ORDER BY time"""

def sql_equipment_dot(equipment, y_val, alias):
    return f'SELECT $__time(ts), CASE WHEN state THEN {y_val} ELSE NULL END AS "{alias}" FROM equipment_state WHERE equipment=\'{equipment}\' AND $__timeFilter(ts) ORDER BY ts'


# ─── Canonical targets ───────────────────────────────────────────────

def make_target(sql, ref_id, fmt="table"):
    return {"datasource": DS, "editorMode": "code", "format": fmt, "rawQuery": True, "rawSql": sql, "refId": ref_id}


# ─── Canonical overrides ─────────────────────────────────────────────

def override_fixed_color(name, color, extra_props=None):
    props = [{"id": "color", "value": {"fixedColor": color, "mode": "fixed"}}]
    if extra_props:
        props.extend(extra_props)
    return {"matcher": {"id": "byName", "options": name}, "properties": props}

def override_indoor_temp():
    return override_fixed_color("Indoor", "#73BF69", [{"id": "custom.lineWidth", "value": 2}])

def override_indoor_vpd():
    return override_fixed_color("Indoor VPD", "#73BF69", [{"id": "custom.lineWidth", "value": 2}])

def override_outdoor_forecast():
    return override_fixed_color("Outdoor Forecast", "#8C8C8C", [
        {"id": "custom.lineWidth", "value": 1},
        {"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [10, 5]}}
    ])

def override_outdoor_vpd_forecast():
    return override_fixed_color("Outdoor VPD Forecast", "#8C8C8C", [
        {"id": "custom.lineWidth", "value": 1},
        {"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [10, 5]}}
    ])

def override_outdoor():
    return override_fixed_color("Outdoor", "#8C8C8C", [{"id": "custom.lineWidth", "value": 1}])

def override_outdoor_vpd():
    return override_fixed_color("Outdoor VPD", "#8C8C8C", [{"id": "custom.lineWidth", "value": 1}])

def override_band_high():
    return override_fixed_color("Band High", "#56A64B", [
        {"id": "custom.lineWidth", "value": 1},
        {"id": "custom.fillBelowTo", "value": "Band Low"},
        {"id": "custom.fillOpacity", "value": 10},
        {"id": "custom.hideFrom", "value": {"legend": True, "tooltip": False, "viz": False}}
    ])

def override_band_low():
    return override_fixed_color("Band Low", "#56A64B", [
        {"id": "custom.lineWidth", "value": 1},
        {"id": "custom.hideFrom", "value": {"legend": True, "tooltip": False, "viz": False}}
    ])

def override_solar_observed():
    return override_fixed_color("Solar W/m\u00b2", "#FFA726", [
        {"id": "custom.lineWidth", "value": 0},
        {"id": "custom.fillOpacity", "value": 35},
        {"id": "custom.gradientMode", "value": "opacity"},
        {"id": "custom.axisPlacement", "value": "right"},
        {"id": "unit", "value": "watt"},
        {"id": "min", "value": 0},
        {"id": "max", "value": 1200}
    ])

def override_solar_forecast():
    return override_fixed_color("Solar Forecast", "#FFD740", [
        {"id": "custom.lineWidth", "value": 0},
        {"id": "custom.fillOpacity", "value": 18},
        {"id": "custom.gradientMode", "value": "opacity"},
        {"id": "custom.axisPlacement", "value": "right"},
        {"id": "unit", "value": "watt"},
        {"id": "min", "value": 0},
        {"id": "max", "value": 1200},
        {"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [10, 5]}}
    ])

def override_equip_dot(name, color):
    return override_fixed_color(name, color, [
        {"id": "custom.drawStyle", "value": "points"},
        {"id": "custom.pointSize", "value": 3}
    ])

# Equipment dot overrides
TEMP_EQUIP_OVERRIDES = [
    override_equip_dot("Fan 1", "rgba(50,150,255,0.7)"),
    override_equip_dot("Fan 2", "rgba(80,180,255,0.7)"),
    override_equip_dot("Fog", "rgba(200,100,255,0.7)"),
    override_equip_dot("Heat 1", "rgba(255,80,50,0.7)"),
    override_equip_dot("Heat 2 (gas)", "rgba(255,140,50,0.7)"),
]

VPD_EQUIP_OVERRIDES = [
    override_equip_dot("Mister South", "rgba(239,83,80,0.7)"),
    override_equip_dot("Mister West", "rgba(255,167,38,0.7)"),
    override_equip_dot("Mister Center", "rgba(171,71,188,0.7)"),
    override_equip_dot("Fog", "rgba(126,87,194,0.7)"),
]

# Equipment dot targets
TEMP_EQUIP_TARGETS = [
    make_target(sql_equipment_dot("fan1", 82, "Fan 1"), "E"),
    make_target(sql_equipment_dot("fan2", 84, "Fan 2"), "F"),
    make_target(sql_equipment_dot("fog", 86, "Fog"), "H"),
    make_target(sql_equipment_dot("heat1", 58, "Heat 1"), "G"),
    make_target(sql_equipment_dot("heat2", 56, "Heat 2 (gas)"), "I"),
]

VPD_EQUIP_TARGETS = [
    make_target(sql_equipment_dot("mister_south", 1.8, "Mister South"), "E"),
    make_target(sql_equipment_dot("mister_west", 1.9, "Mister West"), "F"),
    make_target(sql_equipment_dot("mister_center", 2.0, "Mister Center"), "G"),
    make_target(sql_equipment_dot("fog", 2.1, "Fog"), "H"),
]


# ─── Canonical defaults ──────────────────────────────────────────────

CANONICAL_CUSTOM_DEFAULTS = {
    "axisBorderShow": False,
    "axisCenteredZero": False,
    "axisColorMode": "text",
    "axisLabel": "",
    "axisPlacement": "auto",
    "drawStyle": "line",
    "fillOpacity": 0,
    "gradientMode": "none",
    "hideFrom": {"legend": False, "tooltip": False, "viz": False},
    "lineInterpolation": "smooth",
    "lineWidth": 1,
    "pointSize": 5,
    "showPoints": "never",
    "spanNulls": True,
    "stacking": {"group": "A", "mode": "none"},
    "thresholdsStyle": {"mode": "off"}
}

CANONICAL_TOOLTIP = {"mode": "multi", "sort": "desc"}
CANONICAL_LEGEND = {"displayMode": "list", "placement": "bottom", "showLegend": True}


# ─── Transform functions ─────────────────────────────────────────────

def apply_defaults(panel):
    """Apply canonical defaults to a timeseries panel."""
    if panel.get("type") != "timeseries":
        return
    fc = panel.setdefault("fieldConfig", {})
    defaults = fc.setdefault("defaults", {})
    custom = defaults.setdefault("custom", {})
    for k, v in CANONICAL_CUSTOM_DEFAULTS.items():
        custom[k] = v
    opts = panel.setdefault("options", {})
    opts["tooltip"] = copy.deepcopy(CANONICAL_TOOLTIP)
    opts["legend"] = copy.deepcopy(CANONICAL_LEGEND)


def build_full_temp_panel(panel):
    """Transform a temperature panel to full homepage style."""
    apply_defaults(panel)
    panel["fieldConfig"]["defaults"]["unit"] = "fahrenheit"
    panel["fieldConfig"]["defaults"]["decimals"] = 1

    panel["targets"] = [
        make_target(SQL_ROLLING_TEMP, "A"),
        make_target(SQL_OUTDOOR_TEMP_FORECAST, "B"),
        make_target(SQL_TEMP_BAND, "C"),
        make_target(SQL_OUTDOOR_TEMP, "D"),
        make_target(SQL_SOLAR_OBSERVED, "J"),
        make_target(SQL_SOLAR_FORECAST, "K"),
    ] + [copy.deepcopy(t) for t in TEMP_EQUIP_TARGETS]

    panel["fieldConfig"]["overrides"] = [
        override_indoor_temp(),
        override_outdoor_forecast(),
        override_band_high(),
        override_band_low(),
        override_outdoor(),
        override_solar_observed(),
        override_solar_forecast(),
    ] + [copy.deepcopy(o) for o in TEMP_EQUIP_OVERRIDES]


def build_full_vpd_panel(panel):
    """Transform a VPD panel to full homepage style."""
    apply_defaults(panel)
    panel["fieldConfig"]["defaults"]["unit"] = "pressurePascal"
    panel["fieldConfig"]["defaults"]["decimals"] = 2

    panel["targets"] = [
        make_target(SQL_ROLLING_VPD, "A"),
        make_target(SQL_OUTDOOR_VPD_FORECAST, "B"),
        make_target(SQL_VPD_BAND, "C"),
        make_target(SQL_OUTDOOR_VPD, "D"),
    ] + [copy.deepcopy(t) for t in VPD_EQUIP_TARGETS]

    panel["fieldConfig"]["overrides"] = [
        override_indoor_vpd(),
        override_outdoor_vpd_forecast(),
        override_band_high(),
        override_band_low(),
        override_outdoor_vpd(),
    ] + [copy.deepcopy(o) for o in VPD_EQUIP_OVERRIDES]


def add_band_overlay_temp(panel):
    """Add crop band + solar bg to a zone temp comparison panel (keep existing targets)."""
    apply_defaults(panel)
    # Remove any existing fillOpacity from defaults
    panel["fieldConfig"]["defaults"]["custom"]["fillOpacity"] = 0

    # Add band + solar targets
    existing_refs = {t.get("refId") for t in panel.get("targets", [])}
    new_ref = chr(ord("A") + len(panel["targets"]))
    panel["targets"].append(make_target(SQL_TEMP_BAND, new_ref))
    panel["targets"].append(make_target(SQL_SOLAR_OBSERVED, chr(ord(new_ref) + 1)))
    panel["targets"].append(make_target(SQL_SOLAR_FORECAST, chr(ord(new_ref) + 2)))

    # Add band + solar overrides (keep existing zone color overrides)
    panel["fieldConfig"]["overrides"].extend([
        override_band_high(),
        override_band_low(),
        override_solar_observed(),
        override_solar_forecast(),
    ])


def add_band_overlay_vpd(panel):
    """Add crop VPD band to a zone VPD comparison panel (keep existing targets)."""
    apply_defaults(panel)
    panel["fieldConfig"]["defaults"]["custom"]["fillOpacity"] = 0

    new_ref = chr(ord("A") + len(panel["targets"]))
    panel["targets"].append(make_target(SQL_VPD_BAND, new_ref))

    panel["fieldConfig"]["overrides"].extend([
        override_band_high(),
        override_band_low(),
    ])


def upgrade_solar_gradient(panel):
    """Upgrade a solar radiation panel to golden gradient style."""
    for override in panel.get("fieldConfig", {}).get("overrides", []):
        name = override.get("matcher", {}).get("options", "")
        if "Actual" in name or "Observed" in name:
            override["properties"] = [
                {"id": "color", "value": {"fixedColor": "#FFA726", "mode": "fixed"}},
                {"id": "custom.lineWidth", "value": 0},
                {"id": "custom.fillOpacity", "value": 35},
                {"id": "custom.gradientMode", "value": "opacity"},
            ]
        elif "Forecast" in name:
            override["properties"] = [
                {"id": "color", "value": {"fixedColor": "#FFD740", "mode": "fixed"}},
                {"id": "custom.lineWidth", "value": 0},
                {"id": "custom.fillOpacity", "value": 18},
                {"id": "custom.gradientMode", "value": "opacity"},
                {"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [10, 5]}},
            ]
    apply_defaults(panel)


def add_rolling_avg_to_actual(panel, metric="temp"):
    """Replace raw actual series with rolling avg, apply homepage colors."""
    for target in panel.get("targets", []):
        sql = target.get("rawSql", "")
        # Find the "Actual" series and wrap with rolling avg
        if "Actual" in sql and "Indoor" in sql:
            if metric == "temp":
                target["rawSql"] = sql.replace(
                    "temp_avg AS",
                    'avg(temp_avg) OVER (ORDER BY ts ROWS BETWEEN 14 PRECEDING AND CURRENT ROW) AS'
                )
            elif metric == "vpd":
                target["rawSql"] = sql.replace(
                    "vpd_avg AS",
                    'avg(vpd_avg) OVER (ORDER BY ts ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS'
                )
    # Fix colors
    for override in panel.get("fieldConfig", {}).get("overrides", []):
        name = override.get("matcher", {}).get("options", "")
        if "Actual" in name and ("Temp" in name or "Indoor" in name):
            for prop in override.get("properties", []):
                if prop["id"] == "color":
                    prop["value"] = {"fixedColor": "#73BF69", "mode": "fixed"}
    apply_defaults(panel)


def tooltip_legend_sweep(panel):
    """Just ensure tooltip/legend consistency on timeseries panels."""
    if panel.get("type") != "timeseries":
        return
    opts = panel.setdefault("options", {})
    opts["tooltip"] = copy.deepcopy(CANONICAL_TOOLTIP)
    opts["legend"] = copy.deepcopy(CANONICAL_LEGEND)
    # Also set smooth interpolation
    custom = panel.setdefault("fieldConfig", {}).setdefault("defaults", {}).setdefault("custom", {})
    custom["lineInterpolation"] = "smooth"
    custom["showPoints"] = "never"
    custom["spanNulls"] = True


# ─── Dashboard-specific transforms ───────────────────────────────────

def transform_climate_cooling(dash):
    for panel in dash["panels"]:
        pid = panel.get("id")
        title = panel.get("title", "")
        if pid == 937 or "Cooling Cascade" in title:
            build_full_temp_panel(panel)
            panel["title"] = "Temperature vs Target Band"
        elif pid == 211 or "Zone Temperature" in title:
            add_band_overlay_temp(panel)
        elif pid == 109 or "Indoor vs Outdoor Temp" in title:
            apply_defaults(panel)
        elif pid == 111 or "Forecast vs Actual Solar" in title:
            upgrade_solar_gradient(panel)


def transform_climate_heating(dash):
    for panel in dash["panels"]:
        pid = panel.get("id")
        title = panel.get("title", "")
        if pid == 920 or "Heating Cascade" in title:
            build_full_temp_panel(panel)
            panel["title"] = "Temperature vs Target Band"
        elif pid == 109 or "Indoor vs Outdoor Temp" in title:
            apply_defaults(panel)


def transform_climate_humidity(dash):
    for panel in dash["panels"]:
        pid = panel.get("id")
        title = panel.get("title", "")
        if pid == 15 or (title == "VPD vs Setpoints"):
            build_full_vpd_panel(panel)
            panel["title"] = "VPD vs Target Band"
        elif pid == 12 or "Zone VPD" in title:
            add_band_overlay_vpd(panel)


def transform_climate_controller(dash):
    for panel in dash["panels"]:
        pid = panel.get("id")
        title = panel.get("title", "")
        if pid == 114 or title == "Temperature vs Setpoints":
            build_full_temp_panel(panel)
            panel["title"] = "Temperature vs Target Band"
        elif pid == 115 or title == "VPD vs Setpoints":
            build_full_vpd_panel(panel)
            panel["title"] = "VPD vs Target Band"
        elif panel.get("type") == "timeseries":
            tooltip_legend_sweep(panel)


def transform_greenhouse_zones(dash):
    for panel in dash["panels"]:
        title = panel.get("title", "")
        if "Zone Temperature" in title:
            add_band_overlay_temp(panel)
        elif "Zone VPD" in title:
            add_band_overlay_vpd(panel)


def transform_greenhouse_crops(dash):
    for panel in dash["panels"]:
        title = panel.get("title", "")
        if "Zone VPD" in title:
            add_band_overlay_vpd(panel)
        elif panel.get("type") == "timeseries":
            tooltip_legend_sweep(panel)


def transform_climate_lighting(dash):
    for panel in dash["panels"]:
        title = panel.get("title", "")
        if "Forecast vs Actual Solar" in title:
            upgrade_solar_gradient(panel)
        elif panel.get("type") == "timeseries":
            tooltip_legend_sweep(panel)


def transform_climate_water(dash):
    for panel in dash["panels"]:
        pid = panel.get("id")
        title = panel.get("title", "")
        if pid == 108 or "Water as Climate Control" in title:
            # Replace raw VPD with rolling avg, add mister dots
            build_full_vpd_panel(panel)
            panel["title"] = "VPD & Mister Activity"
        elif panel.get("type") == "timeseries":
            tooltip_legend_sweep(panel)


def transform_evidence_dashboards(dash):
    for panel in dash["panels"]:
        pid = panel.get("id")
        title = panel.get("title", "")
        if pid == 50 or title == "Temperature vs Setpoints":
            build_full_temp_panel(panel)
            panel["title"] = "Temperature vs Target Band"
        elif pid == 51 or title == "VPD vs Setpoints":
            build_full_vpd_panel(panel)
            panel["title"] = "VPD vs Target Band"
        elif "Zone Temperature" in title:
            add_band_overlay_temp(panel)
        elif "Zone VPD" in title:
            add_band_overlay_vpd(panel)
        elif "Forecast vs Planned vs Actual" in title and "Temp" in title:
            add_rolling_avg_to_actual(panel, "temp")
        elif panel.get("type") == "timeseries":
            tooltip_legend_sweep(panel)


def transform_intelligence_planning(dash):
    for panel in dash["panels"]:
        title = panel.get("title", "")
        if "Forecast vs Planned vs Actual" in title and "Temp" in title:
            add_rolling_avg_to_actual(panel, "temp")
        elif "Forecast vs Planned vs Actual" in title and "VPD" in title:
            add_rolling_avg_to_actual(panel, "vpd")
        elif panel.get("type") == "timeseries":
            tooltip_legend_sweep(panel)


def transform_tooltip_legend_only(dash):
    for panel in dash["panels"]:
        if panel.get("type") == "timeseries":
            tooltip_legend_sweep(panel)


# ─── Main ────────────────────────────────────────────────────────────

PHASE_1 = {
    "site-climate-cooling.json": transform_climate_cooling,
    "site-climate-heating.json": transform_climate_heating,
    "site-climate-humidity.json": transform_climate_humidity,
    "site-climate-controller.json": transform_climate_controller,
}

PHASE_2 = {
    "site-greenhouse-zones.json": transform_greenhouse_zones,
    "site-greenhouse-crops.json": transform_greenhouse_crops,
    "site-climate-lighting.json": transform_climate_lighting,
    "site-climate-water.json": transform_climate_water,
    "site-evidence-dashboards.json": transform_evidence_dashboards,
}

PHASE_3 = {
    "site-intelligence-planning.json": transform_intelligence_planning,
    "site-evidence-economics.json": transform_tooltip_legend_only,
    "site-evidence-operations.json": transform_tooltip_legend_only,
    "site-intelligence-data.json": transform_tooltip_legend_only,
}

ALL_PHASES = {1: PHASE_1, 2: PHASE_2, 3: PHASE_3}


def main():
    dry_run = "--dry-run" in sys.argv
    phase_filter = None
    for arg in sys.argv[1:]:
        if arg.startswith("--phase"):
            phase_filter = int(sys.argv[sys.argv.index(arg) + 1])

    phases = {phase_filter: ALL_PHASES[phase_filter]} if phase_filter else ALL_PHASES

    for phase_num, phase_files in sorted(phases.items()):
        print(f"\n{'='*60}")
        print(f"Phase {phase_num}: {len(phase_files)} dashboards")
        print(f"{'='*60}")

        for filename, transform_fn in phase_files.items():
            filepath = DASHBOARD_DIR / filename
            if not filepath.exists():
                print(f"  SKIP {filename} (not found)")
                continue

            with open(filepath) as f:
                dash = json.load(f)

            # Count panels before
            ts_panels = sum(1 for p in dash["panels"] if p.get("type") == "timeseries")

            transform_fn(dash)

            if dry_run:
                print(f"  DRY-RUN {filename} ({ts_panels} timeseries panels)")
            else:
                with open(filepath, "w") as f:
                    json.dump(dash, f, indent=2)
                    f.write("\n")
                print(f"  WROTE {filename} ({ts_panels} timeseries panels)")

    if dry_run:
        print("\nDry run complete. No files were modified.")
    else:
        print(f"\nDone. Reload Grafana dashboards to see changes.")


if __name__ == "__main__":
    main()
