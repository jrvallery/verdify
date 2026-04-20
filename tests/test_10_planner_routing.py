"""Sprint 25 — planner_routing unit tests.

Pure matrix tests over classify_severity + pick_instance + sla_for. No DB,
no HTTP, no ai.yaml dependency — uses module defaults + in-test config
overrides. Run independent of the live stack.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pytest

_INGESTOR_PATH = str(Path(__file__).resolve().parent.parent / "ingestor")
if _INGESTOR_PATH not in sys.path:
    sys.path.insert(0, _INGESTOR_PATH)

from planner_routing import (  # noqa: E402
    _DEFAULT_SLA_MIN,
    RoutingConfig,
    SeverityContext,
    classify_severity,
    load_routing_config,
    pick_instance,
    sla_for,
)

# ── pick_instance ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "trigger_type,severity,expected",
    [
        # Scheduled Opus — always opus regardless of severity
        ("SUNRISE", "minor", "opus"),
        ("SUNRISE", "major", "opus"),
        ("SUNSET", "minor", "opus"),
        ("SUNSET", "major", "opus"),
        ("MIDNIGHT", "minor", "opus"),
        ("MIDNIGHT", "major", "opus"),
        # HEARTBEAT + TRANSITION always local
        ("HEARTBEAT", "minor", "local"),
        ("HEARTBEAT", "major", "local"),
        ("TRANSITION", "minor", "local"),
        ("TRANSITION", "major", "local"),
        # FORECAST + DEVIATION escalate on major
        ("FORECAST", "minor", "local"),
        ("FORECAST", "major", "opus"),
        ("DEVIATION", "minor", "local"),
        ("DEVIATION", "major", "opus"),
    ],
)
def test_pick_instance_matrix(trigger_type, severity, expected):
    assert pick_instance(trigger_type, severity) == expected


def test_pick_instance_manual_defaults_to_opus():
    assert pick_instance("MANUAL") == "opus"


def test_pick_instance_override_always_wins():
    # Override wins even when the policy would pick the other instance
    assert pick_instance("SUNRISE", "major", override="local") == "local"
    assert pick_instance("HEARTBEAT", "minor", override="opus") == "opus"


# ── classify_severity ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "delta_vpd,delta_temp,expected",
    [
        (None, None, "minor"),
        (0.3, 5, "minor"),  # both below thresholds
        (0.6, 5, "major"),  # vpd above 0.5 kPa
        (0.3, 12, "major"),  # temp above 10°F
        (-0.6, -12, "major"),  # negatives count via abs
        (0.5, 10, "minor"),  # at thresholds → not major (strictly greater)
    ],
)
def test_classify_severity_forecast(delta_vpd, delta_temp, expected):
    ctx = SeverityContext(forecast_delta_vpd=delta_vpd, forecast_delta_temp_f=delta_temp)
    assert classify_severity("FORECAST", ctx) == expected


@pytest.mark.parametrize(
    "max_abs_dev,consecutive,expected",
    [
        (None, None, "minor"),
        (0.10, 1, "minor"),  # both below thresholds
        (0.20, 1, "major"),  # magnitude above 0.15
        (0.10, 4, "major"),  # prolonged above 3 cycles
        (0.15, 3, "minor"),  # at thresholds → not major (strictly greater)
    ],
)
def test_classify_severity_deviation(max_abs_dev, consecutive, expected):
    ctx = SeverityContext(max_abs_deviation=max_abs_dev, consecutive_deviation_cycles=consecutive)
    assert classify_severity("DEVIATION", ctx) == expected


def test_classify_severity_non_forecast_non_deviation_is_minor():
    # SUNRISE/SUNSET/MIDNIGHT/TRANSITION/HEARTBEAT all route on type alone;
    # severity is always 'minor' (their policy doesn't branch).
    for t in ("SUNRISE", "SUNSET", "MIDNIGHT", "TRANSITION", "HEARTBEAT"):
        assert classify_severity(t, SeverityContext()) == "minor"


# ── sla_for ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "trigger_type,instance,expected_min",
    [
        # opus scheduled
        ("SUNRISE", "opus", 15),
        ("SUNSET", "opus", 15),
        ("MIDNIGHT", "opus", 15),
        ("FORECAST", "opus", 30),
        ("DEVIATION", "opus", 10),
        # local
        ("TRANSITION", "local", 30),
        ("FORECAST", "local", 60),
        ("DEVIATION", "local", 20),
        ("HEARTBEAT", "local", 15),
    ],
)
def test_sla_for_defined_pairs(trigger_type, instance, expected_min):
    result = sla_for(trigger_type, instance)
    assert result == timedelta(minutes=expected_min)


@pytest.mark.parametrize(
    "trigger_type,instance",
    [
        ("HEARTBEAT", "opus"),  # opus doesn't do heartbeats
        ("TRANSITION", "opus"),  # opus doesn't do transitions (MIDNIGHT split out)
        ("MANUAL", "opus"),  # manual: no SLA
        ("MANUAL", "local"),
    ],
)
def test_sla_for_undefined_pairs_returns_none(trigger_type, instance):
    assert sla_for(trigger_type, instance) is None


# ── load_routing_config ────────────────────────────────────────────


def test_load_routing_config_falls_back_to_defaults(tmp_path, monkeypatch):
    # Clear the lru_cache so a new path is honored
    load_routing_config.cache_clear()
    fake_path = tmp_path / "does-not-exist.yaml"
    cfg = load_routing_config(str(fake_path))
    # Defaults from contract
    assert cfg.forecast_major_delta_vpd_kpa == 0.5
    assert cfg.forecast_major_delta_temp_f == 10.0
    assert cfg.deviation_major_threshold == 0.15
    assert cfg.deviation_prolonged_cycles == 3
    # SLA table matches defaults
    assert cfg.sla_min_by_pair[("opus", "SUNRISE")] == 15
    assert cfg.sla_min_by_pair[("local", "HEARTBEAT")] == 15


def test_load_routing_config_applies_yaml_overrides(tmp_path):
    load_routing_config.cache_clear()
    p = tmp_path / "ai.yaml"
    p.write_text(
        """
planner_routing:
  forecast_major_delta_vpd_kPa: 0.8
  deviation_prolonged_cycles: 5
planner_sla:
  opus:
    SUNRISE: 20
  local:
    HEARTBEAT: 25
"""
    )
    cfg = load_routing_config(str(p))
    # Overridden
    assert cfg.forecast_major_delta_vpd_kpa == 0.8
    assert cfg.deviation_prolonged_cycles == 5
    assert cfg.sla_min_by_pair[("opus", "SUNRISE")] == 20
    assert cfg.sla_min_by_pair[("local", "HEARTBEAT")] == 25
    # Unchanged where YAML didn't specify
    assert cfg.forecast_major_delta_temp_f == 10.0
    assert cfg.deviation_major_threshold == 0.15
    assert cfg.sla_min_by_pair[("opus", "SUNSET")] == 15


def test_defaults_match_contract_literals():
    # Sanity check the module defaults match the published §2.F table.
    # If this drifts, either the contract changed or the module did —
    # investigate before updating this test.
    expected_pairs = {
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
    assert _DEFAULT_SLA_MIN == expected_pairs


# ── RoutingConfig equality / caching ───────────────────────────────


def test_routing_config_is_frozen():
    cfg = RoutingConfig(
        forecast_major_delta_vpd_kpa=0.5,
        forecast_major_delta_temp_f=10.0,
        deviation_major_threshold=0.15,
        deviation_prolonged_cycles=3,
        sla_min_by_pair={},
    )
    with pytest.raises((AttributeError, Exception)):  # dataclass frozen raises FrozenInstanceError
        cfg.forecast_major_delta_vpd_kpa = 0.8  # type: ignore[misc]
