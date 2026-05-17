"""Static Grafana contract tests for band-to-firmware traceability."""

import json
from collections import Counter
from pathlib import Path

DASHBOARD_ROOTS = (
    Path("grafana/dashboards"),
    Path("grafana/provisioning/dashboards/json"),
)

LEGACY_BAND_LABELS = (
    "Firmware Actual/Forecast",
    "Band High (Actual/Forecast)",
    "Band Low (Actual/Forecast)",
    "Planned temp_low",
    "Planned temp_high",
    "Planned vpd_low",
    "Planned vpd_high",
)

TEMP_FIELDS = (
    'firmware_temp_low::float AS "Compliant Low"',
    'firmware_temp_high::float AS "Compliant High"',
)

VPD_FIELDS = (
    'firmware_vpd_low::float AS "Compliant Low"',
    'firmware_vpd_high::float AS "Compliant High"',
)

FORBIDDEN_OPERATOR_FIELDS = (
    "Planner Event",
    "Band/API Update",
    "Firmware Mode Change",
    "Now Divider",
    "Heat Relay",
    "Fan/Vent Relay",
    "Fog Relay",
    "Temp Out of Band",
    "Mist/Fog Relay",
    "VPD Out of Band",
    "Crop Target Low",
    "Crop Target High",
    "Heat Target",
    "Heat On Below",
    "Heat 2 On Below",
    "Heat 2 Clears Above",
    "Cool Hold Until",
    "Cool On Above",
    "Fan On Above",
    "Cool Stage 2 Above",
    "Dehum/Fan Below",
    "Dehum On Below",
    "Dehum Clears Above",
    "Humidify Clears Below",
    "Humidify On Above",
    "Fog On Above",
    "Vent Fog Above",
    "Sealed Fog Above",
)


def _dashboard_paths() -> list[Path]:
    return [path for root in DASHBOARD_ROOTS for path in sorted(root.glob("*.json"))]


def _iter_panels(node: object):
    if not isinstance(node, dict):
        return
    if "targets" in node:
        yield node
    for child in node.get("panels") or ():
        yield from _iter_panels(child)
    for child in node.get("rows") or ():
        yield from _iter_panels(child)


def _panel_sql(panel: dict) -> str:
    return "\n".join(target.get("rawSql", "") for target in panel.get("targets") or ())


def _by_name_override(panel: dict, field_name: str) -> dict | None:
    for override in panel.get("fieldConfig", {}).get("overrides") or ():
        matcher = override.get("matcher", {})
        if matcher.get("id") == "byName" and matcher.get("options") == field_name:
            return override
    return None


def _override_property(override: dict | None, property_id: str):
    if override is None:
        return None
    for prop in override.get("properties") or ():
        if prop.get("id") == property_id:
            return prop.get("value")
    return None


def test_grafana_dashboards_do_not_use_legacy_band_labels():
    dashboards = "\n".join(path.read_text() for path in _dashboard_paths())
    missing = [label for label in LEGACY_BAND_LABELS if label in dashboards]

    assert not missing, f"legacy min/max-only band labels still present: {missing}"


def test_grafana_panels_have_unique_target_ref_ids():
    failures: list[str] = []

    for path in _dashboard_paths():
        data = json.loads(path.read_text())
        for panel in _iter_panels(data):
            refs = [target.get("refId") for target in panel.get("targets") or () if target.get("refId")]
            duplicates = sorted(ref for ref, count in Counter(refs).items() if count > 1)
            if duplicates:
                failures.append(f"{path}:{panel.get('title', '<untitled>')}: duplicate refIds {duplicates}")

    assert not failures, "\n".join(failures)


def test_fn_band_timeline_panels_show_only_compliance_fill():
    failures: list[str] = []

    for path in _dashboard_paths():
        data = json.loads(path.read_text())
        for panel in _iter_panels(data):
            sql = _panel_sql(panel)
            if "fn_band_timeline" not in sql:
                continue

            title = panel.get("title", "<untitled>")
            compliant_high = _by_name_override(panel, "Compliant High")
            if _override_property(compliant_high, "custom.fillBelowTo") != "Compliant Low":
                failures.append(f"{path}:{title}: Compliant High does not fill to Compliant Low")
            if _by_name_override(panel, "Compliant Low") is None:
                failures.append(f"{path}:{title}: missing Compliant Low override")
            for name in ("Compliant Low", "Compliant High"):
                hide_from = _override_property(_by_name_override(panel, name), "custom.hideFrom")
                if hide_from != {"legend": True, "tooltip": True, "viz": False}:
                    failures.append(f"{path}:{title}: {name} should render as fill without legend/tooltip label")

            if "firmware_temp_low" in sql:
                missing = [field for field in TEMP_FIELDS if field not in sql]
                if missing:
                    failures.append(f"{path}:{title}: missing rendered temp fields {missing}")

            if "firmware_vpd_low" in sql:
                missing = [field for field in VPD_FIELDS if field not in sql]
                if missing:
                    failures.append(f"{path}:{title}: missing rendered VPD fields {missing}")

            for hidden in FORBIDDEN_OPERATOR_FIELDS:
                if f'AS "{hidden}"' in sql:
                    failures.append(f"{path}:{title}: {hidden} should not be rendered on operator graph")
                if _by_name_override(panel, hidden) is not None:
                    failures.append(f"{path}:{title}: stale override for hidden field {hidden}")

    assert not failures, "\n".join(failures)
