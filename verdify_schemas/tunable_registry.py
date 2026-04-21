"""Tunable registry — Phase-1 single source of truth for every tunable.

Consolidates what used to live in four separate places that drifted:
- `verdify_schemas.tunables.ALL_TUNABLES` (canonical schema enum)
- `mcp.server.TIER1` (hand-maintained planner allowlist)
- `ingestor.entity_map.SETPOINT_MAP` (dispatcher route)
- `ingestor.entity_map.CFG_READBACK_MAP` (firmware readback)
- `firmware/greenhouse/controls.yaml` clamp pairs

Each new tunable previously required 4 updates kept in sync by hand. Sprint-15
and sprint-15.1 each hit this as the drift cause of planner-rejected pushes
("not a Tier 1 tunable"). This registry is the single definition; TIER1 +
SETPOINT_MAP + CFG_READBACK_MAP become computed views.

Phase 1a (this commit): define the model + populate a representative subset
+ ship the drift-guard test. Phase 1b migrates the remaining tunables and
flips ALL_TUNABLES to derive from here.

See the rewrite plan at
`.claude-agents/iris-dev/plans/yo-iris-dev-you-help-humming-stonebraker.md`
for the full roadmap.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TunableDef(BaseModel):
    """One row in the tunable registry. Each field has exactly one owner.

    Attributes:
        name: canonical name (snake_case). Matches entry_map.SETPOINT_MAP value.
        kind: numeric (float/int) or switch (bool) or enum (int mapped to symbolic).
        min, max: schema-level bounds (advisory for planner UI). None if unbounded.
        default: firmware default from `greenhouse_types.h::default_setpoints()`.
        fw_clamp_lo, fw_clamp_hi: dispatcher + firmware clamp. Must match the
            `cf(val, lo, hi)` / `ci((int)val, lo, hi)` call in controls.yaml
            `/setpoints` handler. Drift guard checks this every CI run.
        esp_object_id: ESPHome entity object_id (slug). Same string as
            SETPOINT_MAP key today; mcp/ingestor will derive from here.
        cfg_readback_object_id: `cfg_*` sensor slug, if firmware publishes one.
            None ⇒ fire-and-forget; must document rationale in `notes`.
        push_owner: who is the source of truth.
        planner_pushable: can Iris push it via `set_tunable`?
        tier: 1 ⇒ appears in `_PLANNER_CORE` prompt; 2 ⇒ escape-hatch only.
        enum_values: for `kind == "enum"`, int value ↔ symbolic name.
        notes: anything human.
    """

    name: str
    kind: Literal["numeric", "switch", "enum"]
    min: float | None = None
    max: float | None = None
    default: float
    fw_clamp_lo: float | None = None
    fw_clamp_hi: float | None = None
    esp_object_id: str
    cfg_readback_object_id: str | None = None
    push_owner: Literal["planner", "band", "safety", "operator", "dispatcher_default", "firmware_internal"]
    planner_pushable: bool = True
    tier: Literal[1, 2] = 1
    enum_values: dict[str, int] | None = None
    notes: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRY — Phase 1a seed. The entries below cover the sprint-15 / sprint-15.1
# tunables (the highest-drift-risk subset) and a few representative Tier 1
# knobs to validate the drift-guard pattern against controls.yaml.
#
# Phase 1b will expand this to all ~49 live tunables (89 current - 14 deletions
# - 7 collapsed into postures = ~68, minus the 19 crop/safety/operator-only
# params we're not pulling into planner surface).
# ─────────────────────────────────────────────────────────────────────────────

REGISTRY: dict[str, TunableDef] = {
    # ── Sprint-15 summer-vent gate (the class of tunable that repeatedly hit
    # the TIER1 drift bug). Definitive source-of-truth for min/max + clamps.
    "sw_summer_vent_enabled": TunableDef(
        name="sw_summer_vent_enabled",
        kind="switch",
        default=1,
        esp_object_id="summer_vent_enabled",
        cfg_readback_object_id="cfg_summer_vent_enabled",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Master switch for the sprint-15 outdoor-cooler-and-drier gate. "
        "Default ON: firmware behavior without it is wrong in summer.",
    ),
    "vent_prefer_temp_delta_f": TunableDef(
        name="vent_prefer_temp_delta_f",
        kind="numeric",
        min=2.0,
        max=15.0,
        default=5.0,
        fw_clamp_lo=2.0,
        fw_clamp_hi=15.0,
        esp_object_id="vent_prefer_temp_delta__f_",
        cfg_readback_object_id="cfg___vent_prefer_temp_delta__f_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Outdoor must be ≥ this many °F cooler than indoor for gate to fire.",
    ),
    "vent_prefer_dp_delta_f": TunableDef(
        name="vent_prefer_dp_delta_f",
        kind="numeric",
        min=2.0,
        max=15.0,
        default=5.0,
        fw_clamp_lo=2.0,
        fw_clamp_hi=15.0,
        esp_object_id="vent_prefer_dp_delta__f_",
        cfg_readback_object_id="cfg___vent_prefer_dp_delta__f_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Outdoor dewpoint must be ≥ this many °F below indoor DP for gate.",
    ),
    "outdoor_staleness_max_s": TunableDef(
        name="outdoor_staleness_max_s",
        kind="numeric",
        min=120,
        max=1800,
        default=600,
        fw_clamp_lo=120,
        fw_clamp_hi=1800,
        esp_object_id="outdoor_staleness_max__s_",
        cfg_readback_object_id="cfg___outdoor_staleness_max__s_",
        push_owner="planner",
        planner_pushable=True,
        tier=2,
        notes="Gate disables when outdoor data older than this. Sprint-15.1 "
        "raised default 300→600 and floor 60→120 so dispatcher cadence "
        "jitter doesn't intermittently disqualify the gate.",
    ),
    "summer_vent_min_runtime_s": TunableDef(
        name="summer_vent_min_runtime_s",
        kind="numeric",
        min=60,
        max=600,
        default=180,
        fw_clamp_lo=60,
        fw_clamp_hi=600,
        esp_object_id="summer_vent_min_runtime__s_",
        cfg_readback_object_id="cfg___summer_vent_min_runtime__s_",
        push_owner="planner",
        planner_pushable=True,
        tier=2,
    ),
    # ── Sprint-15.1 vent-close interlocks (fixes 4/5/7) ──────────────
    "sw_fog_closes_vent": TunableDef(
        name="sw_fog_closes_vent",
        kind="switch",
        default=1,
        esp_object_id="fog_closes_vent",
        cfg_readback_object_id=None,  # switch entity; state tracked in equipment_state not setpoint_snapshot
        push_owner="operator",
        planner_pushable=True,
        tier=2,
        notes="Fog fires only when vent is closed. Default ON; disabling "
        "re-enables FW-9b emergency fog during VENTILATE (tradeoff).",
    ),
    "sw_mister_closes_vent": TunableDef(
        name="sw_mister_closes_vent",
        kind="switch",
        default=1,
        esp_object_id="mister_closes_vent",
        cfg_readback_object_id=None,
        push_owner="operator",
        planner_pushable=True,
        tier=2,
        notes="Mister fires only when vent is closed. Sprint-15.1 fix 5+7.",
    ),
    # ── Representative Tier 1 planner knobs — proof of pattern ─────
    "bias_heat": TunableDef(
        name="bias_heat",
        kind="numeric",
        min=-10.0,
        max=10.0,
        default=3.0,
        fw_clamp_lo=-10.0,
        fw_clamp_hi=10.0,  # controls.yaml clamp
        esp_object_id="bias_heat__f",  # entity_map.SETPOINT_MAP
        cfg_readback_object_id="cfg___bias_heat___f_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Note: validate_setpoints tightens this to [-5, +5] at ingest; "
        "controls.yaml accepts [-10, +10]. Registry uses the wider value.",
    ),
    "bias_cool": TunableDef(
        name="bias_cool",
        kind="numeric",
        min=-10.0,
        max=10.0,
        default=5.0,
        fw_clamp_lo=-10.0,
        fw_clamp_hi=10.0,
        esp_object_id="bias_cool__f",
        cfg_readback_object_id="cfg___bias_cool___f_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
    ),
    "min_heat_off_s": TunableDef(
        name="min_heat_off_s",
        kind="numeric",
        min=60,
        max=600,
        default=180,
        fw_clamp_lo=60,
        fw_clamp_hi=600,
        esp_object_id="min_heat_off__s_",
        cfg_readback_object_id="cfg___min_heat_off__s_",
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Sprint-15.1 fix 6: default 300→180. Clamp ceiling tightened 60→600 so planner can't walk past 10 min.",
    ),
    # ── Phase-2 dwell gate ───────────────────────────────────────────
    "sw_dwell_gate_enabled": TunableDef(
        name="sw_dwell_gate_enabled",
        kind="switch",
        default=0,
        esp_object_id="dwell_gate_enabled",
        cfg_readback_object_id=None,  # switch; state in equipment_state
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="Master switch for Phase-2 mode-dwell gate. Default OFF for "
        "shadow-mode bake. Flip to ON after 14d replay+shadow validation.",
    ),
    "dwell_gate_ms": TunableDef(
        name="dwell_gate_ms",
        kind="numeric",
        min=60000,
        max=1800000,
        default=300000,
        fw_clamp_lo=60000,
        fw_clamp_hi=1800000,
        esp_object_id="dwell_gate_ms",
        cfg_readback_object_id=None,
        push_owner="planner",
        planner_pushable=True,
        tier=2,
        notes="Dwell hold duration. Default 5 min. Safety rails + R2-3 "
        "dry override + vpd_min_safe rescue preempt unconditionally.",
    ),
    "fog_escalation_kpa": TunableDef(
        name="fog_escalation_kpa",
        kind="numeric",
        min=0.1,
        max=1.0,
        default=0.5,
        fw_clamp_lo=0.1,
        fw_clamp_hi=1.0,  # controls.yaml clamp
        esp_object_id="fog_escalation__kpa_",
        cfg_readback_object_id=None,  # Phase 1b adds cfg_* readback
        push_owner="planner",
        planner_pushable=True,
        tier=1,
        notes="PHASE 1B TODO: add cfg_* readback (fire-and-forget today).",
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Derived views — ONE source of truth above, many consumers below.
# ─────────────────────────────────────────────────────────────────────────────


def _all_tunables() -> frozenset[str]:
    return frozenset(REGISTRY)


def _tier1() -> frozenset[str]:
    """Planner-accessible via MCP set_tunable. Replaces mcp/server.py TIER1."""
    return frozenset(n for n, d in REGISTRY.items() if d.planner_pushable and d.tier == 1)


def _planner_pushable() -> frozenset[str]:
    """Broader set: everything the planner CAN push (includes tier-2 escape hatch)."""
    return frozenset(n for n, d in REGISTRY.items() if d.planner_pushable)


def _setpoint_map() -> dict[str, str]:
    """ESPHome object_id → canonical name. Replaces ingestor.entity_map.SETPOINT_MAP."""
    return {d.esp_object_id: n for n, d in REGISTRY.items()}


def _cfg_readback_map() -> dict[str, str]:
    """cfg_* slug → canonical name. Replaces ingestor.entity_map.CFG_READBACK_MAP."""
    return {d.cfg_readback_object_id: n for n, d in REGISTRY.items() if d.cfg_readback_object_id}


# Phase 1a: expose as module attributes for consumers that already import
# computed-view style. `ALL_TUNABLES_REG` etc. coexist with the legacy
# `ALL_TUNABLES` in `tunables.py` during migration; Phase 1b flips the legacy
# module to import from here.
ALL_TUNABLES_REG: frozenset[str] = _all_tunables()
TIER1_REG: frozenset[str] = _tier1()
PLANNER_PUSHABLE_REG: frozenset[str] = _planner_pushable()
SETPOINT_MAP_REG: dict[str, str] = _setpoint_map()
CFG_READBACK_MAP_REG: dict[str, str] = _cfg_readback_map()


def get(name: str) -> TunableDef | None:
    """Lookup a tunable by canonical name. None if not registered."""
    return REGISTRY.get(name)
