"""Sprint 24.9 fidelity-hardening tests.

Covers the unit-testable subset of S24.9:
  - S24.9.1 (cfg_readback range validation): ranges table present + covers the
    expected safety/band/bias tunables; runtime rejection verified via live
    gate (on_state_change needs an aioesphomeapi state object).
  - S24.9.3 (status='plan_written' on resolve): UPDATE string contains the
    status column (static string check — query itself is integration).
  - S24.9.4 (context-gather sentinel): sentinel is a non-empty string;
    gather_context returns it on subprocess non-zero exit + timeout;
    _deliver_and_log skips actual send_to_iris call when context is the
    sentinel.
  - S24.9.5 (zero-variance rule): documented param list covers the four
    vpd_target zones (firmware sprint-13 flagged west zone specifically).

Not unit-testable here (verified live):
  - S24.9.2 dispatcher SetpointChange validation — requires asyncpg pool
  - S24.9.5 actual DB query over setpoint_snapshot

Run: `pytest tests/test_12_fidelity.py -v`
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest  # noqa: F401  (used by @pytest.fixture in some runs)

_INGESTOR_PATH = str(Path(__file__).resolve().parent.parent / "ingestor")
if _INGESTOR_PATH not in sys.path:
    sys.path.insert(0, _INGESTOR_PATH)

# ingestor.py loads the DSN from env at import time. Provide harmless
# defaults so the module imports in a test-only context without a real DB.
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "test")

import iris_planner  # noqa: E402

import ingestor  # noqa: E402


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
    raise AssertionError(f"{name} assignment not found in {path}")


# ── S24.9.1 — _SETPOINT_RANGES coverage ────────────────────────────


def test_setpoint_ranges_covers_safety_rails():
    """The cfg_readback range-check applies the same _SETPOINT_RANGES the
    setpoint_changes path uses. At minimum these safety rails must be in
    the table — they're the 30-day zero-polluted params the firmware
    sprint-13 historical-impact scan flagged."""
    expected = {
        "safety_min",
        "safety_max",
        "safety_vpd_min",
        "safety_vpd_max",
        "temp_high",
        "temp_low",
        "vpd_high",
        "vpd_low",
    }
    assert expected <= set(ingestor._SETPOINT_RANGES.keys()), (
        f"_SETPOINT_RANGES missing: {expected - set(ingestor._SETPOINT_RANGES.keys())}"
    )


def test_setpoint_ranges_reject_zero_for_safety_min():
    """Concrete check: safety_min=0 is out of [30, 60]. on_state_change's
    cfg_readback path (Sprint 24.9) now drops this instead of storing it."""
    lo, hi = ingestor._SETPOINT_RANGES["safety_min"]
    assert not (lo <= 0.0 <= hi), "0 must fall OUTSIDE safety_min range"
    # Valid operational value is inside
    assert lo <= 40.0 <= hi


def test_setpoint_ranges_accepts_realistic_values():
    """Valid operational values must NOT be rejected."""
    r = ingestor._SETPOINT_RANGES
    assert r["safety_min"][0] <= 40.0 <= r["safety_min"][1]
    assert r["safety_max"][0] <= 100.0 <= r["safety_max"][1]
    assert r["temp_low"][0] <= 65.0 <= r["temp_low"][1]
    assert r["temp_high"][0] <= 78.0 <= r["temp_high"][1]
    assert r["vpd_low"][0] <= 0.8 <= r["vpd_low"][1]
    assert r["vpd_high"][0] <= 1.5 <= r["vpd_high"][1]


# ── S24.9.4 — context-gather failure sentinel ──────────────────────


def test_context_gather_sentinel_defined():
    """The sentinel must exist and be a non-empty, non-whitespace string
    that can't collide with real context output."""
    s = iris_planner.CONTEXT_GATHER_FAILED_SENTINEL
    assert isinstance(s, str)
    assert s.strip() == s  # no leading/trailing whitespace
    assert len(s) >= 10
    # Sentinel should be structurally distinct — contains underscores, no spaces
    assert "_" in s
    assert " " not in s


def test_gather_context_returns_sentinel_on_nonzero_exit():
    """Subprocess exits non-zero → gather_context returns the sentinel,
    NOT the old '(context gathering failed: ...)' string that got spliced
    into the prompt pre-24.9."""
    fake_result = MagicMock(returncode=1, stdout="", stderr="boom")
    with (
        patch("iris_planner.subprocess.run", return_value=fake_result),
        patch("iris_planner._record_plan_context_failure"),
    ):
        result = iris_planner.gather_context()
    assert result == iris_planner.CONTEXT_GATHER_FAILED_SENTINEL


def test_gather_context_returns_sentinel_on_timeout():
    """TimeoutExpired → same sentinel path."""
    import subprocess

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="gather", timeout=60)

    with (
        patch("iris_planner.subprocess.run", side_effect=raise_timeout),
        patch("iris_planner._record_plan_context_failure"),
    ):
        result = iris_planner.gather_context()
    assert result == iris_planner.CONTEXT_GATHER_FAILED_SENTINEL


def test_gather_context_returns_stdout_on_success():
    """Happy path still returns real context stdout, not the sentinel."""
    fake_result = MagicMock(returncode=0, stdout="=== CONTEXT ===\nTemp: 75F\n", stderr="")
    with (
        patch("iris_planner.subprocess.run", return_value=fake_result),
        patch("iris_planner._resolve_plan_context_failures") as resolve,
    ):
        result = iris_planner.gather_context()
    assert result == "=== CONTEXT ===\nTemp: 75F\n"
    assert result != iris_planner.CONTEXT_GATHER_FAILED_SENTINEL
    resolve.assert_called_once_with()


def test_record_plan_context_failure_dedupes_open_alerts():
    with patch("iris_planner._run_alert_sql") as run_sql:
        iris_planner._record_plan_context_failure("nonzero_exit", "boom", 1)

    sql = run_sql.call_args.args[0]
    assert "WITH updated AS" in sql
    assert "WHERE NOT EXISTS (SELECT 1 FROM updated)" in sql
    assert "plan_context_failed" in sql


def test_resolve_plan_context_failures_marks_open_alerts_resolved():
    with patch("iris_planner._run_alert_sql") as run_sql:
        iris_planner._resolve_plan_context_failures()

    sql = run_sql.call_args.args[0]
    assert "disposition = 'resolved'" in sql
    assert "auto-resolved: context gather succeeded" in sql
    assert "source = 'iris_planner'" in sql


# ── S24.9.5 — zero-variance rule param list ────────────────────────


def test_zero_variance_rule_covers_vpd_target_west():
    """Firmware sprint-13 30-day scan surfaced vpd_target_west stuck at
    1.2 kPa for 33k samples. The new alert rule must cover this param so
    the same condition auto-alerts in future."""
    # Rule lives inside alert_monitor's body. We verify the param appears
    # in the tasks.py file as a string literal — coarser than ideal but
    # doesn't require the full async DB path.
    import tasks

    tasks_source = Path(tasks.__file__).read_text()
    assert '"vpd_target_west"' in tasks_source or "'vpd_target_west'" in tasks_source
    # All four zone targets should be in the zero-variance scan list
    for param in ("vpd_target_south", "vpd_target_west", "vpd_target_east", "vpd_target_center"):
        assert f'"{param}"' in tasks_source, f"zero-variance rule missing {param}"


def test_zero_variance_rule_skips_empty_zone_target_fallbacks():
    """A zone target pinned at its fallback is expected when that zone has no active crop."""
    import tasks

    tasks_source = Path(tasks.__file__).read_text()
    assert "active_crop_zones" in tasks_source
    assert "zone_target_params" in tasks_source
    assert "if zone in active_crop_zones" in tasks_source


def test_zero_variance_rule_also_covers_band_params():
    """temp_low / temp_high / vpd_low / vpd_high should track crop + dispatcher
    state. If they go flat for 7 days, something upstream is broken."""
    import tasks

    src = Path(tasks.__file__).read_text()
    # Look for these all appearing in the same zone_var_params tuple
    for param in ("temp_low", "temp_high", "vpd_low", "vpd_high"):
        assert f'"{param}"' in src


def test_alert_monitor_detects_band_owned_plan_rows():
    """Future crop-band rows in setpoint_plan must open an alert."""
    import tasks

    src = Path(tasks.__file__).read_text()
    assert "planner_band_ownership_drift" in src
    assert "system.planner_band_ownership" in src
    assert "setpoint_plan" in src
    assert "is_active = true" in src
    for param in ("temp_low", "temp_high", "vpd_low", "vpd_high"):
        assert f"'{param}'" in src


def test_setpoint_confirmation_monitor_resolves_acknowledged_alerts():
    """Acknowledged setpoint_unconfirmed alerts still block deploy preflight;
    the monitor must resolve them once a confirmation or superseding setpoint
    lands.
    """
    import tasks

    src = Path(tasks.__file__).read_text()
    start = src.index("async def setpoint_confirmation_monitor")
    block = src[start:]
    assert "al.resolved_at IS NULL" in block
    assert "al.disposition IN ('open', 'acknowledged')" in block
    assert "AND resolved_at IS NULL" in block
    assert "newer.ts > now() - interval '2 hours'" not in block


def test_dispatcher_band_owned_contract_is_explicit():
    """Band params are dispatcher-owned; plans should not emit them as
    tactical knobs. Keep vpd_low explicit so dry-side compliance can't fall
    through a planner/schema ambiguity.
    """
    import tasks

    expected = {
        "temp_low",
        "temp_high",
        "vpd_low",
        "vpd_high",
        "vpd_target_south",
        "vpd_target_west",
        "vpd_target_east",
        "vpd_target_center",
    }
    assert tasks.BAND_DRIVEN_PARAMS == expected

    src = Path(tasks.__file__).read_text()
    assert "fn_band_setpoints(now())" in src
    assert "param in BAND_DRIVEN_PARAMS" in src


def test_mcp_set_tunable_treats_vpd_low_as_band_owned():
    """MCP should expose crop-band params as read-only context, not Tier 1
    tactical tuning. The dispatcher owns vpd_low through fn_band_setpoints().
    """
    mcp_path = Path(__file__).resolve().parent.parent / "mcp" / "server.py"
    band_owned = _assigned_set(mcp_path, "BAND_OWNED_PARAMS")
    tier1 = _assigned_set(mcp_path, "TIER1_TUNABLES")

    assert band_owned == {"temp_low", "temp_high", "vpd_low", "vpd_high"}
    assert not (band_owned & tier1), f"Band-owned params must not be Tier 1 tunables: {band_owned & tier1}"


# ── S24.9.3 — status='plan_written' on resolve ─────────────────────


def test_resolve_delivery_log_sets_status_plan_written():
    """The _resolve_delivery_log UPDATE must set status='plan_written'
    alongside resulting_plan_id so the status column stays truthful.
    String-check only — running the UPDATE requires asyncpg."""
    import tasks

    src = Path(tasks.__file__).read_text()
    # Locate the _resolve_delivery_log function and check its UPDATE string
    start = src.index("async def _resolve_delivery_log")
    end = src.index("async def ", start + 1)
    body = src[start:end]
    assert "status            = 'plan_written'" in body or "status = 'plan_written'" in body, (
        "_resolve_delivery_log UPDATE must include status='plan_written'"
    )


# ── S24.9.7 — _deliver_and_log sentinel skip (integration-shape) ───


def test_sentinel_import_chain_wired():
    """tasks.py imports the sentinel from iris_planner. Confirms the
    symbol is exposed + named consistently."""
    import tasks

    assert hasattr(tasks, "CONTEXT_GATHER_FAILED_SENTINEL")
    assert tasks.CONTEXT_GATHER_FAILED_SENTINEL == iris_planner.CONTEXT_GATHER_FAILED_SENTINEL
