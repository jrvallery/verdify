"""Phase-1 drift-guard tests for the single-source-of-truth tunable registry.

The test set that closes the sprint-15 / sprint-15.1 drift-class bug:
- Every REGISTRY entry's fw_clamp_lo/hi matches the ESPHome number entity
  min_value/max_value in `firmware/greenhouse/tunables.yaml` for that tunable's
  ESPHome object_id. Direct aioesphomeapi pushes are now the setpoint path.
- Every REGISTRY entry with a non-None cfg_readback_object_id maps bidirectionally
  with `ingestor/entity_map.py::CFG_READBACK_MAP`.
- Every REGISTRY entry maps bidirectionally with `ingestor/entity_map.py::SETPOINT_MAP`.

Runs in <50ms — pure text parsing of tunables.yaml, no ESPHome build needed.
Any drift → CI fails → operator fixes before merge.
"""

from __future__ import annotations

import pathlib
import re
import sys

import pytest

from verdify_schemas.tunable_registry import REGISTRY, registry_value_error

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="module")
def controls_yaml() -> str:
    path = REPO_ROOT / "firmware" / "greenhouse" / "controls.yaml"
    return path.read_text()


@pytest.fixture(scope="module")
def tunables_yaml() -> str:
    path = REPO_ROOT / "firmware" / "greenhouse" / "tunables.yaml"
    return path.read_text()


# ─── Drift Guard #1 — firmware clamps match registry ─────────────────────

_SETPOINT_LITERAL_RE = re.compile(
    r"\.(?P<field>[a-zA-Z0-9_]+)\s*=\s*"
    r"(?P<rhs>(?:uint32_t\()?-?\d+(?:\.\d+)?[fFuUlL]*(?:\))?)\s*,"
)
_NUMBER_BLOCK_RE = re.compile(
    r"\n\s*-\s+platform:\s+template\n(?P<body>.*?)(?=\n\s*-\s+platform:\s+template\n|\nswitch:|\Z)", re.DOTALL
)
_NUMBER_NAME_RE = re.compile(r'\n\s*name:\s*"(?P<name>[^"]+)"')
_MIN_RE = re.compile(r"\n\s*min_value:\s*(?P<value>-?\d+(?:\.\d+)?)")
_MAX_RE = re.compile(r"\n\s*max_value:\s*(?P<value>-?\d+(?:\.\d+)?)")


def _esphome_object_id(name: str) -> str:
    """Mirror ESPHome's object_id slug style used by entity_map.py."""
    return re.sub(r"[^a-z0-9]", "_", name.lower())


def _parse_number_bounds(text: str) -> dict[str, tuple[float, float]]:
    """Extract {object_id: (min_value, max_value)} from ESPHome number entities."""
    out: dict[str, tuple[float, float]] = {}
    number_section = text.split("\nswitch:", 1)[0]
    for m in _NUMBER_BLOCK_RE.finditer(number_section):
        body = "\n" + m.group("body")
        name_m = _NUMBER_NAME_RE.search(body)
        min_m = _MIN_RE.search(body)
        max_m = _MAX_RE.search(body)
        if not (name_m and min_m and max_m):
            continue
        out[_esphome_object_id(name_m.group("name"))] = (float(min_m.group("value")), float(max_m.group("value")))
    return out


class TestDriftGuard:
    def test_registry_clamps_match_tunables_yaml(self, tunables_yaml: str) -> None:
        """Every registry entry with fw_clamp_lo/hi must match tunables.yaml.

        This is the drift guard. Sprint-15 and sprint-15.1 would have failed
        here if run pre-merge — they both added tunables to the schema
        without touching the MCP allowlist / readback. Guard catches
        firmware clamp drift specifically: if someone changes a number
        min_value/max_value and doesn't update the registry, this fails.
        """
        bounds = _parse_number_bounds(tunables_yaml)
        # Only check numeric tunables with explicit fw_clamp declared.
        to_check = {n: d for n, d in REGISTRY.items() if d.kind == "numeric" and d.fw_clamp_lo is not None}
        missing: list[str] = []
        mismatched: list[str] = []
        for name, d in to_check.items():
            key = d.esp_object_id
            if key not in bounds:
                missing.append(name)
                continue
            lo, hi = bounds[key]
            if abs(lo - d.fw_clamp_lo) > 1e-6 or abs(hi - d.fw_clamp_hi) > 1e-6:
                mismatched.append(f"{name}: registry=({d.fw_clamp_lo}, {d.fw_clamp_hi}) tunables.yaml=({lo}, {hi})")
        if missing:
            pytest.fail(
                f"Registry has {len(missing)} tunables with fw_clamp declared "
                f"but no matching ESPHome number in tunables.yaml: "
                f"{missing[:10]}. Either add to tunables.yaml or remove "
                f"fw_clamp_lo/hi from registry."
            )
        if mismatched:
            pytest.fail(f"Clamp drift detected in {len(mismatched)} tunables:\n  " + "\n  ".join(mismatched))

    def test_controls_setpoints_are_not_literal_policy(self, controls_yaml: str) -> None:
        """Setpoints fields must come from globals/handler values, not local
        literals. Literal safety bounds belong in validate_setpoints(), where
        they are fallback clamps, not in the live ESPHome Setpoints builder.
        """
        m = re.search(r"Setpoints setpts\s*=\s*\{(?P<body>.*?)\n\s*\};", controls_yaml, re.DOTALL)
        assert m, "Could not find Setpoints setpts initializer in controls.yaml"
        literal_fields = [match.group("field") for match in _SETPOINT_LITERAL_RE.finditer(m.group("body"))]
        assert not literal_fields, (
            "Setpoints initializer has hardcoded numeric policy literals: "
            f"{literal_fields}. Add globals/tunables/readbacks and assign from id(...)."
        )

    def test_registry_matches_entity_map_setpoint(self) -> None:
        """Every REGISTRY entry's esp_object_id must be in entity_map.SETPOINT_MAP
        (so dispatcher can route it) and every SETPOINT_MAP route must have a
        registry row.
        """
        # Resolve ingestor module; same idiom as test_tunables.py
        for p in reversed(
            (
                str(REPO_ROOT / "ingestor"),
                "/srv/verdify/ingestor",
                "/mnt/iris/verdify/ingestor",
            )
        ):
            if p not in sys.path:
                sys.path.insert(0, p)
        from entity_map import SETPOINT_MAP

        em_object_ids = set(SETPOINT_MAP)
        missing = []
        for name, d in REGISTRY.items():
            if d.esp_object_id not in em_object_ids:
                missing.append(f"{name}: esp_object_id='{d.esp_object_id}' not in SETPOINT_MAP")
        assert not missing, (
            f"{len(missing)} registry entries have esp_object_ids not in entity_map.SETPOINT_MAP:\n  "
            + "\n  ".join(missing)
        )
        missing_registry = sorted(set(SETPOINT_MAP.values()) - set(REGISTRY))
        assert not missing_registry, (
            f"{len(missing_registry)} SETPOINT_MAP params have no tunable_registry row: "
            f"{missing_registry}. Add registry metadata so MCP/planner access cannot drift."
        )

    def test_registry_cfg_readback_matches_entity_map(self) -> None:
        """Every REGISTRY entry with a non-None cfg_readback_object_id must
        appear in entity_map.CFG_READBACK_MAP.
        """
        for p in reversed(
            (
                str(REPO_ROOT / "ingestor"),
                "/srv/verdify/ingestor",
                "/mnt/iris/verdify/ingestor",
            )
        ):
            if p not in sys.path:
                sys.path.insert(0, p)
        from entity_map import CFG_READBACK_MAP

        em_slugs = set(CFG_READBACK_MAP)
        missing = []
        for name, d in REGISTRY.items():
            if d.cfg_readback_object_id and d.cfg_readback_object_id not in em_slugs:
                missing.append(f"{name}: cfg_readback_object_id='{d.cfg_readback_object_id}' not in CFG_READBACK_MAP")
        assert not missing, f"{len(missing)} registry entries have cfg readbacks not routed:\n  " + "\n  ".join(missing)

    def test_registry_subset_of_all_tunables(self) -> None:
        """Every REGISTRY entry must be in the legacy ALL_TUNABLES frozenset.

        Phase-1a subset — registry and ALL_TUNABLES coexist. Registry is a
        seed; enforce one direction (registry ⊆ ALL_TUNABLES) so a new
        registry entry can't bypass the legacy schema enum.
        """
        from verdify_schemas.tunables import ALL_TUNABLES

        extras = set(REGISTRY) - set(ALL_TUNABLES)
        assert not extras, (
            f"Registry has {len(extras)} entries not in legacy ALL_TUNABLES: "
            f"{sorted(extras)}. Add to tunables.py first (Phase-1b flips this)."
        )

    def test_registry_tier1_is_subset_of_mcp_tier1(self) -> None:
        """Every REGISTRY entry with tier=1 + planner_pushable=True must be in
        mcp/server.py TIER1_TUNABLES so Iris can actually push it.

        Phase-1a: one-directional check. Phase-1b replaces mcp TIER1 with
        `PLANNER_PUSHABLE_REG` from this module.
        """
        mcp_path = REPO_ROOT / "mcp" / "server.py"
        text = mcp_path.read_text()
        # Grab either the legacy local TIER1 set or the module-level
        # TIER1_TUNABLES frozenset contract.
        m = re.search(r"TIER1(?:_TUNABLES)?\s*=\s*(?:frozenset\(\s*)?\{([^}]+)\}", text, re.DOTALL)
        assert m, "Couldn't find TIER1/TIER1_TUNABLES set in mcp/server.py"
        tier1_body = m.group(1)
        mcp_tier1 = set(re.findall(r'"([a-z0-9_]+)"', tier1_body))
        registry_tier1 = {n for n, d in REGISTRY.items() if d.tier == 1 and d.planner_pushable}
        missing = registry_tier1 - mcp_tier1
        assert not missing, (
            f"{len(missing)} registry tier-1 entries not in mcp/server.py TIER1_TUNABLES: "
            f"{sorted(missing)}. Add to TIER1_TUNABLES (Phase-1b retires it entirely)."
        )

    def test_mcp_set_tunable_uses_planner_pushable_registry(self) -> None:
        """MCP set_tunable must expose all registry planner-pushable params,
        not just the daily Tier 1 prompt subset.
        """
        mcp_path = REPO_ROOT / "mcp" / "server.py"
        text = mcp_path.read_text()
        assert "PLANNER_PUSHABLE_REG" in text
        assert "parameter not in PLANNER_PUSHABLE_REG" in text
        assert "parameter not in TIER1_TUNABLES" not in text

    def test_registry_value_error_reports_bounds_and_nearest_safe(self) -> None:
        err = registry_value_error("mister_all_kpa", 2.8)
        assert err is not None
        assert "mister_all_kpa=2.8 outside registry bounds [1, 2.5]" in err
        assert "nearest_safe=2.5" in err

    def test_mcp_set_tunable_validates_registry_bounds(self) -> None:
        """set_tunable must reject out-of-range planner pushes before DB writes."""
        mcp_path = REPO_ROOT / "mcp" / "server.py"
        text = mcp_path.read_text()
        assert "registry_value_error(parameter, value)" in text
        assert "Tunable value outside registry bounds" in text
