#!/usr/bin/env /srv/greenhouse/.venv/bin/python3
"""Audit planner tunable traceability across schema, MCP, dispatcher, and firmware.

This is intentionally static. It catches the drift class where Hermes can plan
or push a tunable that is not part of the executable planner-policy contract,
lacks a readback, or is known to be a reserved/no-op firmware global.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "ingestor"))

from entity_map import CFG_READBACK_MAP, SETPOINT_MAP  # noqa: E402

from verdify_schemas.tunable_registry import PLANNER_PUSHABLE_REG, REGISTRY, TIER1_REG  # noqa: E402
from verdify_schemas.tunables import ALL_TUNABLES  # noqa: E402

RESERVED_NO_EFFECT = {
    "fan_burst_min",
    "fog_burst_min",
    "mist_vent_close_lead_s",
    "mist_vent_reopen_delay_s",
    "mister_all_off_s",
    "mister_all_on_s",
    "mister_max_runtime_min",
    "mister_off_s",
    "mister_on_s",
    "summer_vent_min_runtime_s",
    "vent_bypass_min",
}


def _assigned_set(path: Path, name: str) -> set[str]:
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        value = node.value
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "frozenset":
            value = value.args[0]
        return set(ast.literal_eval(value))
    raise RuntimeError(f"{name} assignment not found in {path}")


def main() -> int:
    mcp_path = REPO_ROOT / "mcp" / "server.py"
    plan_required = _assigned_set(mcp_path, "PLAN_REQUIRED_PARAMS")
    mcp_tier1 = _assigned_set(mcp_path, "TIER1_TUNABLES")
    registry_tier1 = set(TIER1_REG)
    planner_policy = set(PLANNER_PUSHABLE_REG)
    registry_planner_policy = {name for name, spec in REGISTRY.items() if spec.control_class == "planner_policy"}
    setpoint_params = set(SETPOINT_MAP.values())
    readback_params = set(CFG_READBACK_MAP.values())

    failures: list[str] = []
    if plan_required != registry_tier1:
        failures.append(
            "PLAN_REQUIRED_PARAMS differs from registry Tier 1: "
            f"missing={sorted(registry_tier1 - plan_required)} extra={sorted(plan_required - registry_tier1)}"
        )
    if mcp_tier1 != registry_tier1:
        failures.append(
            "TIER1_TUNABLES differs from registry Tier 1: "
            f"missing={sorted(registry_tier1 - mcp_tier1)} extra={sorted(mcp_tier1 - registry_tier1)}"
        )
    if planner_policy != registry_planner_policy:
        failures.append(
            "PLANNER_PUSHABLE_REG must equal canonical planner-policy rows: "
            f"missing={sorted(registry_planner_policy - planner_policy)} extra={sorted(planner_policy - registry_planner_policy)}"
        )

    registry_missing = sorted(set(ALL_TUNABLES) - set(REGISTRY))
    if registry_missing:
        failures.append(f"ALL_TUNABLES missing from tunable_registry: {registry_missing}")

    for param in sorted(plan_required):
        spec = REGISTRY[param]
        if param not in setpoint_params:
            failures.append(f"{param}: missing SETPOINT_MAP route")
        if param not in readback_params:
            failures.append(f"{param}: missing CFG_READBACK_MAP route")
        if not spec.cfg_readback_object_id:
            failures.append(f"{param}: registry cfg_readback_object_id is empty")
        if param in RESERVED_NO_EFFECT:
            failures.append(f"{param}: reserved/no-effect param is in Tier 1")

    for param in sorted(planner_policy):
        spec = REGISTRY[param]
        if param not in setpoint_params:
            failures.append(f"{param}: planner-policy param missing SETPOINT_MAP route")
        if param not in readback_params:
            failures.append(f"{param}: planner-policy param missing CFG_READBACK_MAP route")
        if not spec.cfg_readback_object_id:
            failures.append(f"{param}: planner-policy registry cfg_readback_object_id is empty")

    pushable_reserved = sorted(p for p in RESERVED_NO_EFFECT if REGISTRY[p].planner_pushable)
    if pushable_reserved:
        failures.append(f"reserved/no-effect params are planner-pushable: {pushable_reserved}")

    print(f"registry_total={len(REGISTRY)}")
    print(f"schema_tunables={len(ALL_TUNABLES)}")
    print(f"registry_tier1={len(registry_tier1)}")
    print(f"plan_required={len(plan_required)}")
    print(f"mcp_tier1={len(mcp_tier1)}")
    print(f"planner_policy={len(planner_policy)}")
    print(f"planner_policy_optional={len(planner_policy - registry_tier1)}")
    print(f"tier1_with_readback={len(plan_required & readback_params)}")
    print(f"reserved_no_effect={len(RESERVED_NO_EFFECT)}")

    if failures:
        print("FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
