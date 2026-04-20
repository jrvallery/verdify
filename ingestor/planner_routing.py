"""planner_routing.py — Sprint 25 dual-Iris routing policy.

Pure routing logic for the dual-Iris rollout (contract v1.4 §2.G).
Responsibilities:
  - Load routing thresholds + SLA timeouts from config/ai.yaml.
  - Classify a trigger's severity from live context (forecast delta, deviation
    magnitude, plan age).
  - Pick the right Iris instance (opus vs local) given trigger type + severity.
  - Report the SLA timeout for a (trigger_type, instance) pair so alert_monitor
    can detect stalled triggers.

No side effects, no DB, no HTTP. Consumed by `tasks.py::planning_heartbeat`
and `tasks.py::alert_monitor`. Tested in isolation via a parametrized matrix.

Config fallbacks: if ai.yaml sections are missing, module defaults match the
contract literal values. Production MUST have the sections populated before
the Sprint 25 tactical_heartbeat task ships — missing config silently falls
back to defaults which is correct for opus-only operation but lets the local
SLA table be wrong if the default ever drifts from the contract.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml

log = logging.getLogger("planner_routing")

Instance = Literal["opus", "local"]
Severity = Literal["minor", "major"]
TriggerType = Literal[
    "SUNRISE",
    "SUNSET",
    "MIDNIGHT",
    "TRANSITION",
    "FORECAST",
    "DEVIATION",
    "HEARTBEAT",
    "MANUAL",
]


# ── Defaults (contract v1.4 §2.G) — used when ai.yaml sections are missing ──

_DEFAULT_ROUTING = {
    "forecast_major_delta_vpd_kPa": 0.5,
    "forecast_major_delta_temp_F": 10.0,
    "deviation_major_threshold": 0.15,
    "deviation_prolonged_cycles": 3,
}

# Minutes per (instance, trigger_type). n/a combos not in the mapping.
_DEFAULT_SLA_MIN = {
    ("opus", "SUNRISE"): 15,
    ("opus", "SUNSET"): 15,
    ("opus", "MIDNIGHT"): 15,
    ("opus", "FORECAST"): 30,
    ("opus", "DEVIATION"): 10,
    ("local", "TRANSITION"): 30,
    ("local", "FORECAST"): 60,
    ("local", "DEVIATION"): 20,
    ("local", "HEARTBEAT"): 15,
}

# (trigger_type, severity) → default instance. Caller may override.
_ROUTING_TABLE: dict[tuple[TriggerType, Severity], Instance] = {
    ("HEARTBEAT", "minor"): "local",
    ("HEARTBEAT", "major"): "local",
    ("TRANSITION", "minor"): "local",
    ("TRANSITION", "major"): "local",
    ("FORECAST", "minor"): "local",
    ("FORECAST", "major"): "opus",
    ("DEVIATION", "minor"): "local",
    ("DEVIATION", "major"): "opus",
    ("SUNRISE", "minor"): "opus",
    ("SUNRISE", "major"): "opus",
    ("SUNSET", "minor"): "opus",
    ("SUNSET", "major"): "opus",
    ("MIDNIGHT", "minor"): "opus",
    ("MIDNIGHT", "major"): "opus",
}

# Default config path. Override for tests via load_routing_config(path=...).
_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "ai.yaml"


@dataclass(frozen=True)
class RoutingConfig:
    """Thresholds + SLA timeouts loaded from ai.yaml (or defaults)."""

    forecast_major_delta_vpd_kpa: float
    forecast_major_delta_temp_f: float
    deviation_major_threshold: float
    deviation_prolonged_cycles: int
    sla_min_by_pair: dict[tuple[Instance, TriggerType], int]


@dataclass(frozen=True)
class SeverityContext:
    """Inputs to classify_severity(). Populated by the caller (planning_heartbeat)
    from live DB / forecast state. Any field may be None when unknown — the
    classifier treats None as 'not major on this axis'."""

    forecast_delta_vpd: float | None = None
    forecast_delta_temp_f: float | None = None
    max_abs_deviation: float | None = None
    plan_age_hours: float | None = None
    consecutive_deviation_cycles: int | None = None


@lru_cache(maxsize=1)
def load_routing_config(path: str | None = None) -> RoutingConfig:
    """Load routing thresholds + SLA table from ai.yaml. Cached per path.

    Missing sections → module defaults (contract literals). Missing file →
    defaults + WARNING log. Never raises; planner_routing must always return
    a usable config so the ingestor never deadlocks on config load.
    """
    p = Path(path) if path else _DEFAULT_CONFIG_PATH
    raw: dict = {}
    if p.exists():
        try:
            raw = yaml.safe_load(p.read_text()) or {}
        except Exception as e:
            log.warning("planner_routing: failed to parse %s: %s (using defaults)", p, e)
            raw = {}
    else:
        log.warning("planner_routing: %s not found, using contract defaults", p)

    routing = {**_DEFAULT_ROUTING, **(raw.get("planner_routing") or {})}

    # sla_min_by_pair: contract YAML shape is {opus: {TYPE: min}, local: {TYPE: min}}
    sla_yaml = raw.get("planner_sla") or {}
    sla_min = dict(_DEFAULT_SLA_MIN)
    for instance_key in ("opus", "local"):
        for trigger_type, minutes in (sla_yaml.get(instance_key) or {}).items():
            sla_min[(instance_key, trigger_type)] = int(minutes)

    return RoutingConfig(
        forecast_major_delta_vpd_kpa=float(routing["forecast_major_delta_vpd_kPa"]),
        forecast_major_delta_temp_f=float(routing["forecast_major_delta_temp_F"]),
        deviation_major_threshold=float(routing["deviation_major_threshold"]),
        deviation_prolonged_cycles=int(routing["deviation_prolonged_cycles"]),
        sla_min_by_pair=sla_min,
    )


def classify_severity(
    trigger_type: TriggerType,
    context: SeverityContext,
    *,
    config: RoutingConfig | None = None,
) -> Severity:
    """Decide 'minor' vs 'major' for the given trigger + live context.

    Rules per contract v1.4 §2.G:
      FORECAST: major if |Δvpd_outdoor| > 0.5 kPa OR |Δtemp_F| > 10°F
      DEVIATION: major if max_abs_deviation > 0.15 OR prolonged >3 cycles
      Otherwise trigger-specific defaults route both severities the same
        (SUNRISE/SUNSET/MIDNIGHT always opus; TRANSITION/HEARTBEAT always
        local), so severity classification is a no-op for those types.

    Unknown trigger types default to 'minor' — conservative.
    """
    cfg = config or load_routing_config()

    if trigger_type == "FORECAST":
        if (
            context.forecast_delta_vpd is not None
            and abs(context.forecast_delta_vpd) > cfg.forecast_major_delta_vpd_kpa
        ):
            return "major"
        if (
            context.forecast_delta_temp_f is not None
            and abs(context.forecast_delta_temp_f) > cfg.forecast_major_delta_temp_f
        ):
            return "major"
        return "minor"

    if trigger_type == "DEVIATION":
        if context.max_abs_deviation is not None and context.max_abs_deviation > cfg.deviation_major_threshold:
            return "major"
        if (
            context.consecutive_deviation_cycles is not None
            and context.consecutive_deviation_cycles > cfg.deviation_prolonged_cycles
        ):
            return "major"
        return "minor"

    return "minor"


def pick_instance(
    trigger_type: TriggerType,
    severity: Severity = "minor",
    *,
    override: Instance | None = None,
) -> Instance:
    """Select opus vs local per policy. Override wins unconditionally.

    MANUAL: always follows override; if caller provides no override, defaults
    to 'opus' (safer; paid peer is the more capable one for ad-hoc operator
    debug).
    """
    if override is not None:
        return override
    if trigger_type == "MANUAL":
        return "opus"
    return _ROUTING_TABLE.get((trigger_type, severity), "local")


def sla_for(
    trigger_type: TriggerType,
    instance: Instance,
    *,
    config: RoutingConfig | None = None,
) -> timedelta | None:
    """Look up the SLA timeout for a (trigger, instance) pair.

    Returns None when the combination has no SLA defined (e.g. opus +
    HEARTBEAT doesn't exist in the policy). alert_monitor should skip rows
    with None SLA rather than alert immediately.
    """
    cfg = config or load_routing_config()
    minutes = cfg.sla_min_by_pair.get((instance, trigger_type))
    if minutes is None:
        return None
    return timedelta(minutes=minutes)
