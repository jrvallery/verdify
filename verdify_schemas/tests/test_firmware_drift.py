"""Firmware ↔ entity_map drift guard.

Parses every ESPHome YAML in /srv/verdify/firmware/greenhouse/ to extract
the universe of declared entity `id:` values, then asserts every key in
the ingestor's entity_map dicts (CLIMATE_MAP, SETPOINT_MAP, DIAGNOSTIC_MAP,
EQUIPMENT_*, STATE_MAP, CFG_READBACK_MAP, DAILY_ACCUM_MAP) corresponds to
a real entity the firmware emits.

Forward direction only: ingestor expectations → firmware reality.

Why not reverse (firmware → ingestor)? Many firmware entities are
intentionally unmapped — local-only timers, intermediate computations,
template helpers that drive other entities. A reverse guard would need
a whitelist of "expected-untracked" ids; high noise, low signal.

Pairs with the existing test_drift_guards.py (DB ↔ schema) and
test_tunables.py (entity_map ↔ schema): three drift-guards now triangulate
firmware ↔ ingestor ↔ schema ↔ DB.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

YAML_DIR = Path("/srv/verdify/firmware/greenhouse")
PLATFORMS = ("sensor", "binary_sensor", "switch", "number", "text_sensor", "select", "button")

# ESPHome YAML uses !secret etc. — register no-op constructors so safe_load works.
for tag in ("!secret", "!lambda", "!include"):
    yaml.SafeLoader.add_constructor(tag, lambda loader, node: None)


def _slugify(name: str) -> tuple[str, ...]:
    """Approximate ESPHome's name-to-object_id slugification.

    ESPHome's actual algorithm: lowercase, then replace each char that
    isn't [a-z0-9] with `_` individually (no collapsing). Trailing
    underscores are PRESERVED (e.g. "Vent Latch Timer (s)" →
    `vent_latch_timer__s_`).

    We emit several variants to match across edge cases:
      - tight: collapse runs, strip ends — matches simple names
      - loose: per-char replace, preserve all underscores — matches names
        with bullets, parens, units in ()
      - loose_stripped: per-char replace, strip ends — older entity_map
        keys sometimes used this style
    """
    s = name.lower()
    tight = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    per_char = re.sub(r"[^a-z0-9]", "_", s)
    loose = per_char  # preserve all underscores including trailing
    loose_stripped = per_char.strip("_")
    return (tight, loose, loose_stripped)


def _firmware_entity_ids() -> set[str]:
    """Return the set of object_ids the firmware emits over aioesphomeapi.

    For each entity, we collect:
      - the explicit `object_id:` (highest precedence)
      - otherwise both slugifications of `name:` (tight + loose, since
        ESPHome's exact algorithm depends on platform & character class)
      - the C++ `id:` (last-resort match for entities used internally)
    """
    if not YAML_DIR.exists():
        return set()
    ids: set[str] = set()
    for yf in sorted(YAML_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(yf.read_text())
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict):
            continue
        for plat, items in data.items():
            if plat not in PLATFORMS or not isinstance(items, list):
                continue
            for entry in items:
                if not isinstance(entry, dict):
                    continue
                if "object_id" in entry:
                    ids.add(str(entry["object_id"]))
                if "id" in entry:
                    ids.add(str(entry["id"]))
                if "name" in entry and isinstance(entry["name"], str):
                    for candidate in _slugify(entry["name"]):
                        ids.add(candidate)
    return ids


pytestmark = pytest.mark.skipif(not YAML_DIR.exists(), reason="firmware YAML directory not available")


@pytest.fixture(scope="module")
def fw_ids() -> set[str]:
    ids = _firmware_entity_ids()
    if not ids:
        pytest.skip("no firmware entity ids parsed (yaml read failed?)")
    return ids


@pytest.fixture(scope="module")
def entity_map():
    """Resolve entity_map from VM compat path or repo-relative."""
    here = Path(__file__).resolve()
    repo_root = here.parent.parent.parent
    for p in ("/srv/verdify/ingestor", str(repo_root / "ingestor"), "/mnt/iris/verdify/ingestor"):
        if p not in sys.path:
            sys.path.insert(0, p)
    try:
        import entity_map as em
    except ImportError as e:
        pytest.skip(f"entity_map not importable: {e}")
    return em


# Maps in ingestor/entity_map.py whose KEYS are firmware entity object_ids /
# ESPHome `id:` values. Each key here must correspond to a real `id:` in
# firmware/greenhouse/*.yaml — otherwise the ingestor expects telemetry that
# the firmware never emits.
MAP_NAMES = [
    "CLIMATE_MAP",
    "EQUIPMENT_BINARY_MAP",
    "EQUIPMENT_SWITCH_MAP",
    "STATE_MAP",
    "SETPOINT_MAP",
    "DIAGNOSTIC_MAP",
    "DAILY_ACCUM_MAP",
    "CFG_READBACK_MAP",
]


# Known-pre-existing drift — entity_map keys whose firmware-side entities
# either:
#  (a) were renamed in firmware without updating entity_map (real bug — fix),
#  (b) are tracked through a different path than `id:` / `name:` slugify
#      (slugify edge case our heuristic doesn't cover — accept), or
#  (c) refer to entities that no longer exist in firmware at all (dead route).
#
# Each entry below should ideally migrate to a fix or removal in a
# follow-up sprint. New drift NOT in this list will fail CI loud — that's
# the point of the guard.
KNOWN_PRE_EXISTING_DRIFT: dict[str, set[str]] = {
    "CLIMATE_MAP": {
        # `water_used__gal_`: firmware tracks via flow_total internally; ingestor
        # currently maps the published name but firmware emits under a different
        # path. Sprint 24+ cleanup.
        "water_used__gal_",
    },
    "EQUIPMENT_BINARY_MAP": {
        # The *_running / *_active / *_blocked / *_open entries here predate
        # the equipment_state event-stream pattern; they map to internal
        # logic signals, not published binary_sensors. To remove: audit
        # each, drop those the dispatcher no longer writes.
        "economiser_blocked",
        "fan_1_running",
        "fan_2_running",
        "fan_burst_active",
        "fog_burst_active",
        "fog_running",
        "heat_1_running",
        "heat_2_running",
        "leak_detected",
        "mister_budget_exceeded",
        "mister_running",
        "occupancy_active",
        "sntp_status",
        "vent_bypass_active",
        "vent_open",
        "vent_running",
        "vpd_emergency",
        "water_flowing",
    },
    "DAILY_ACCUM_MAP": {
        # Drip runtime sensors removed from firmware in Sprint 18 redesign;
        # ingestor map still references the old names. Cleanup pending.
        "center_drips_runtime__today_",
        "wall_drips_runtime__today_",
    },
}


@pytest.mark.parametrize("map_name", MAP_NAMES)
def test_entity_map_keys_exist_in_firmware(map_name, fw_ids, entity_map):
    """Every key in <map_name> must be a real firmware entity id, except
    the documented KNOWN_PRE_EXISTING_DRIFT allowlist."""
    em_map = getattr(entity_map, map_name, None)
    if em_map is None:
        pytest.skip(f"{map_name} not present in entity_map")
    expected = set(em_map.keys())
    allowed_drift = KNOWN_PRE_EXISTING_DRIFT.get(map_name, set())
    new_missing = sorted((expected - fw_ids) - allowed_drift)
    assert not new_missing, (
        f"{map_name} has {len(new_missing)} NEW entity id(s) the firmware doesn't emit: "
        f"{new_missing[:10]}"
        + ("..." if len(new_missing) > 10 else "")
        + ". Either the firmware was changed (entity renamed/dropped) or the ingestor "
        "map references a typo. If this is intentional pre-existing drift, add it to "
        "KNOWN_PRE_EXISTING_DRIFT[<map_name>] in test_firmware_drift.py."
    )


def test_known_drift_is_still_drifting(fw_ids, entity_map):
    """Inverse guard — if firmware ADDED back an entity that's in the
    pre-existing-drift list, remove it from the allowlist. Keeps the
    allowlist from rotting into a permanent ignore."""
    no_longer_drifting: dict[str, list[str]] = {}
    for map_name, drift_keys in KNOWN_PRE_EXISTING_DRIFT.items():
        em_map = getattr(entity_map, map_name, {})
        em_keys = set(em_map.keys())
        # An entry is "no longer drifting" if it now exists in fw_ids
        # AND is still in the entity_map (so the route is actually used)
        resolved = sorted({k for k in drift_keys if k in fw_ids and k in em_keys})
        if resolved:
            no_longer_drifting[map_name] = resolved
    assert not no_longer_drifting, (
        f"These entries are in KNOWN_PRE_EXISTING_DRIFT but the firmware now emits them — "
        f"remove from the allowlist: {no_longer_drifting}"
    )


def test_firmware_emits_a_reasonable_number_of_entities(fw_ids):
    """Sanity check — if the YAML parser silently lost everything we want to know."""
    assert len(fw_ids) >= 50, f"only {len(fw_ids)} firmware entity ids parsed; expected >=50"
