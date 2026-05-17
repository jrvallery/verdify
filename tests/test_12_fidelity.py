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
import asyncio
import importlib.util
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
from verdify_schemas.plan import PlanDeliveryLogRow  # noqa: E402
from verdify_schemas.tunable_registry import PLANNER_PUSHABLE_REG, REGISTRY  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


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


def test_mcp_alert_ack_does_not_unresolve_resolved_alerts():
    src = Path("mcp/server.py").read_text()
    start = src.index('elif action == "acknowledge"')
    block = src[start : src.index('elif action == "resolve"', start)]
    assert "resolved_at IS NULL" in block
    assert "already_resolved" in block


def test_forecast_action_engine_completes_due_outcomes():
    src = Path("scripts/forecast-action-engine.py").read_text()
    assert "async def evaluate_due_outcomes" in src
    assert "fl.triggered_at <= now() - interval '6 hours'" in src
    assert "'no_action_required'" in src
    assert "'pending'" in src


def test_public_health_forecast_outcomes_ignore_evaluated_ok_noops():
    src = Path("db/migrations/106-public-health-ledger-calibration.sql").read_text()
    start = src.index("SELECT 'forecast_action_outcomes_7d'")
    block = src[start : src.index("UNION ALL", start)]
    assert "action_taken <> 'evaluated_ok'" in block


def test_daily_summary_live_total_water_floors_known_mister_subset():
    src = Path("ingestor/tasks.py").read_text()
    start = src.index("async def _refresh_daily_summary_for_date")
    end = src.index("async def daily_summary_live", start)
    block = src[start:end]
    assert 'mister_water_gal = float(climate["mister_water_gal"])' in block
    assert "meter_water_gal" in block
    assert "water_gal = max(float(meter_water_gal), mister_water_gal)" in block


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
    """Future dispatcher-owned policy rows in setpoint_plan must open an alert."""
    import tasks

    src = Path(tasks.__file__).read_text()
    assert "planner_band_ownership_drift" in src
    assert "system.planner_band_ownership" in src
    assert "setpoint_plan" in src
    assert "is_active = true" in src
    for param in (
        "temp_low",
        "temp_high",
        "vpd_low",
        "vpd_high",
        "gl_dli_target",
        "gl_sunrise_hour",
        "gl_sunset_hour",
        "sw_gl_auto_mode",
    ):
        assert f"'{param}'" in src


def test_forecast_action_engine_does_not_write_dispatcher_owned_setpoints():
    """Legacy forecast rules may still target policy values; the writer must skip them."""
    script = Path("scripts/forecast-action-engine.py").read_text()
    band_owned = _assigned_set(Path("scripts/forecast-action-engine.py"), "BAND_OWNED_PARAMS")
    assert {
        "temp_low",
        "temp_high",
        "vpd_low",
        "vpd_high",
        "gl_dli_target",
        "gl_sunrise_hour",
        "gl_sunset_hour",
        "sw_gl_auto_mode",
    } <= band_owned
    assert "skipped_band_owned" in script
    assert "band_owned_dispatcher_contract" in script
    start = script.index('if action_type == "setpoint" and param in BAND_OWNED_PARAMS')
    end = script.index('if action_type == "setpoint" and param and adj_value is not None', start + 1)
    body = script[start:end]
    assert "INSERT INTO setpoint_plan" not in body
    assert "INSERT INTO setpoint_changes" not in body


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
        "gl_dli_target",
        "gl_sunrise_hour",
        "gl_sunset_hour",
        "sw_gl_auto_mode",
    }
    assert tasks.BAND_DRIVEN_PARAMS == expected

    src = Path(tasks.__file__).read_text()
    assert "fn_band_setpoints(now())" in src
    assert "fn_house_vpd_control_band(now())" in src
    assert "fn_lighting_policy(now())" in src
    assert "fn_lighting_circuit_policy(now())" in src
    assert "LIGHTING_CIRCUIT_DEFAULT_PARAMS" in src
    assert "LIGHTING_POLICY_PARAMS" in src
    assert "param in BAND_DRIVEN_PARAMS" in src


def test_api_setpoint_fallback_uses_computed_band_not_planner_band_rows():
    """The ESP32 HTTP fallback must match the dispatcher for band-owned
    values. Active-plan rows for crop bands are drift signals, not authority.
    """
    api = Path("api/main.py").read_text()
    start = api.index("async def get_setpoints")
    end = api.index("        # Per-zone VPD targets", start)
    body = api[start:end]

    assert 'BAND_COMPUTED = {"temp_high", "temp_low", "vpd_high", "vpd_low"}' in body
    assert "LIGHTING_COMPUTED" in body
    assert "SELECT * FROM fn_band_setpoints(now())" in body
    assert "SELECT * FROM fn_house_vpd_control_band(now())" in body
    assert "SELECT * FROM fn_lighting_policy(now(), $1)" in body
    assert "fn_lighting_circuit_policy(now(), $1)" in body
    assert "planner_band" not in body
    assert "params[param] = _round_half_up(band_val, precision)" in body
    assert "params[param] = lighting_values[param]" in body
    assert "if param not in plan_params" in body


def test_setpoint_server_fallback_does_not_overlay_band_owned_plan_rows():
    """The legacy ESP32 pull server should keep crop-band params on the
    dispatcher-pushed or DB-computed values.
    """
    script = Path("scripts/setpoint-server.py").read_text()

    for param in (
        "temp_low",
        "temp_high",
        "vpd_low",
        "vpd_high",
        "vpd_target_south",
        "vpd_target_west",
        "vpd_target_east",
        "vpd_target_center",
    ):
        assert f'"{param}"' in script
    assert "LIGHTING_POLICY_PARAMS" in script
    assert "fn_band_setpoints(now())" in script
    assert "fn_house_vpd_control_band(now())" in script
    assert "fn_zone_vpd_targets(now())" in script
    assert "'gl_dli_target','gl_sunrise_hour','gl_sunset_hour','sw_gl_auto_mode'" in script
    assert "fn_lighting_policy(now(), 'vallery')" in script
    assert "fn_lighting_circuit_policy(now(), 'vallery')" in script
    assert "if k.strip() not in plan_params" in script


def test_setpoint_server_controls_real_lutron_switch_entities_and_confirms_state():
    """The Lutron proxy must command the real switch entities and confirm HA
    state before recording success. The light.* wrappers accept service calls
    but do not reliably report state.
    """
    script = Path("scripts/setpoint-server.py").read_text()

    assert '"main": {"ha_entity": "switch.greenhouse_main", "equipment": "grow_light_main"}' in script
    assert '"grow": {"ha_entity": "switch.greenhouse_grow", "equipment": "grow_light_grow"}' in script
    assert "ha_confirm_state" in script
    assert "asyncio.run_coroutine_threadsafe" in script
    assert "asyncio.new_event_loop" not in script


def test_ha_light_sync_reads_real_lutron_switch_entities():
    """DB equipment_state should trace the same Lutron switch entities the
    proxy commands, not stale light.* wrappers.
    """
    tasks = Path("ingestor/tasks.py").read_text()
    sync = Path("scripts/ha-sensor-sync.py").read_text()

    for src in (tasks, sync):
        assert '"switch.greenhouse_main": "grow_light_main"' in src
        assert '"switch.greenhouse_grow": "grow_light_grow"' in src
        assert '"light.greenhouse_main": "grow_light_main"' not in src
        assert '"light.greenhouse_grow": "grow_light_grow"' not in src


def test_planner_context_surfaces_band_source_trace():
    """The planning prompt should show the read-only crop -> dispatcher/API
    -> firmware -> cfg_readback chain for the four compliance-band edges.
    """
    script = Path("scripts/gather-plan-context.sh").read_text()

    assert "BAND SETPOINT PROVENANCE" in script
    assert "fn_band_setpoint_provenance(now(), '${GREENHOUSE_ID}')" in script
    assert "Do not set band-driven or lighting-policy params in your plan" in script
    assert "LIGHTING POLICY (read-only; dispatcher pushes these to ESP32)" in script
    assert "fn_lighting_policy(now(), '${GREENHOUSE_ID}')" in script
    assert "Do not set gl_dli_target, gl_sunrise_hour, gl_sunset_hour, or sw_gl_auto_mode" in script
    assert "PER-CIRCUIT LIGHTING POLICY" in script
    assert "fn_lighting_circuit_policy(now(), '${GREENHOUSE_ID}')" in script
    assert "TEMPEST LUX THRESHOLD RECOMMENDATION" in script
    assert "fn_lighting_lux_threshold_recommendation(now(), '${GREENHOUSE_ID}')" in script
    assert "lux_hysteresis" in script
    assert "ESP32 cfg readbacks are excluded from this source-of-truth view" in script
    assert (
        "Set gl_main_lux_threshold/gl_main_lux_hysteresis and gl_grow_lux_threshold/gl_grow_lux_hysteresis from this evidence"
        in script
    )


def test_lighting_policy_sql_excludes_esp32_readbacks_from_source_of_truth():
    """Planner/band/manual setpoints are policy; ESP32 rows are acknowledgements."""
    policy = Path("db/migrations/123-lighting-per-circuit-state-machines.sql").read_text()
    recommendation = Path("db/migrations/122-lighting-lux-threshold-recommendation.sql").read_text()

    assert "AND COALESCE(source, '') <> 'esp32'" in policy
    assert "AND COALESCE(source, '') <> 'esp32'" in recommendation
    assert "per-circuit gl_main_*/gl_grow_* lux tunables" in recommendation


def test_lighting_status_and_timeline_follow_firmware_hysteresis():
    """Graphs must show the same ON/OFF band behavior that firmware enforces."""
    status = Path("db/migrations/123-lighting-per-circuit-state-machines.sql").read_text()
    timeline = Path("db/migrations/124-lighting-timeline-performance.sql").read_text()

    assert "state_row.value" in status
    assert "p.lux_off_threshold" in status
    assert "WITH RECURSIVE bounds AS" in timeline
    assert "main_seed_on" in timeline
    assert "grow_seed_on" in timeline
    assert "o.natural_lux < o.main_lux_off_threshold" in timeline
    assert "o.natural_lux < o.grow_lux_off_threshold" in timeline
    assert "t.dli_today < t.main_dli_target" in timeline
    assert "expected-on projection follows firmware ON/OFF hysteresis" in timeline


def test_house_vpd_control_band_uses_zone_median_not_strictest_crop():
    """The firmware controls one air mass; zone targets still drive misters."""
    import tasks

    band = {"vpd_low": 0.375, "vpd_high": 0.635}
    zones = {
        "vpd_target_south": 1.15,
        "vpd_target_west": 1.20,
        "vpd_target_east": 0.70,
        "vpd_target_center": 0.635,
    }

    control = tasks._house_vpd_control_band(band, zones)

    assert control["vpd_high"] > band["vpd_high"]
    assert 0.90 <= control["vpd_high"] <= 1.00
    assert control["vpd_low"] >= band["vpd_low"]
    assert control["vpd_high"] - control["vpd_low"] >= 0.55
    assert control["vpd_high"] <= max(zones.values())


def test_band_trace_params_have_sensor_registry_readbacks():
    """The canonical band trace depends on cfg_* readbacks for all band params."""
    import entity_map

    from verdify_schemas.tunable_registry import REGISTRY

    for param in ("temp_low", "temp_high", "vpd_low", "vpd_high"):
        assert param in REGISTRY
        assert REGISTRY[param].push_owner == "band"
        assert param in set(entity_map.SETPOINT_MAP.values())
        assert param in set(entity_map.CFG_READBACK_MAP.values())


def test_vpd_high_moisture_guardrail_tracks_active_band():
    import tasks

    guardrails = tasks._vpd_high_moisture_guardrails(
        {"vpd_low": 0.26, "vpd_high": 0.81},
        {"temp_avg": 66.3, "dew_point": 53.5, "vpd_avg": 0.95},
    )

    assert guardrails["mister_engage_kpa"] == 0.86
    assert guardrails["mister_all_kpa"] == 1.06
    assert guardrails["mister_engage_delay_s"] == 45.0
    assert guardrails["mister_all_delay_s"] == 90.0
    assert guardrails["mister_pulse_gap_s"] == 30.0
    assert guardrails["fog_escalation_kpa"] == 0.30
    assert guardrails["min_fog_off_s"] == 60.0


def test_vpd_high_moisture_guardrail_respects_dew_risk():
    import tasks

    guardrails = tasks._vpd_high_moisture_guardrails(
        {"vpd_low": 0.26, "vpd_high": 0.81},
        {"temp_avg": 66.3, "dew_point": 61.0, "vpd_avg": 0.95},
    )

    assert guardrails == {}


def test_vpd_high_moisture_guardrail_stays_preemptive_in_ventilate():
    import tasks

    guardrails = tasks._vpd_high_moisture_guardrails(
        {"vpd_low": 0.26, "vpd_high": 0.81},
        {"temp_avg": 66.3, "dew_point": 53.5, "vpd_avg": 0.76, "greenhouse_mode": "VENTILATE"},
    )

    assert guardrails["mister_engage_kpa"] == 0.86
    assert guardrails["fog_escalation_kpa"] == 0.20


def test_vpd_high_moisture_guardrail_tightens_hot_dry_ventilate_fog():
    import tasks

    guardrails = tasks._vpd_high_moisture_guardrails(
        {"vpd_low": 0.52, "vpd_high": 1.07},
        {
            "temp_avg": 76.8,
            "sp_temp_high": 72.9,
            "dew_point": 60.0,
            "vpd_avg": 1.38,
            "greenhouse_mode": "VENTILATE",
            "outdoor_rh_pct": 18.0,
        },
    )

    assert guardrails["fog_escalation_kpa"] == 0.15
    assert guardrails["min_fog_off_s"] == 45.0


def test_vpd_high_moisture_guardrail_stays_sticky_until_recent_recovery():
    import tasks

    guardrails = tasks._vpd_high_moisture_guardrails(
        {"vpd_low": 0.52, "vpd_high": 1.07},
        {
            "temp_avg": 72.0,
            "sp_temp_high": 72.9,
            "dew_point": 58.0,
            "vpd_avg": 0.93,
            "greenhouse_mode": "VENTILATE",
            "recent_samples": 12,
            "recent_near_high_fraction": 0.75,
            "recent_avg_vpd": 1.04,
        },
    )

    assert guardrails["fog_escalation_kpa"] == 0.20
    assert guardrails["min_fog_off_s"] == 60.0


def test_vpd_high_moisture_guardrail_does_not_run_when_idle_below_band():
    import tasks

    guardrails = tasks._vpd_high_moisture_guardrails(
        {"vpd_low": 0.26, "vpd_high": 0.81},
        {"temp_avg": 66.3, "dew_point": 53.5, "vpd_avg": 0.76, "greenhouse_mode": "IDLE"},
    )

    assert guardrails == {}


def test_mcp_set_tunable_treats_vpd_low_as_band_owned():
    """MCP should expose crop-band params as read-only context, not Tier 1
    tactical tuning. The dispatcher owns vpd_low through fn_band_setpoints().
    """
    mcp_path = Path(__file__).resolve().parent.parent / "mcp" / "server.py"
    band_owned = _assigned_set(mcp_path, "BAND_OWNED_PARAMS")
    tier1 = _assigned_set(mcp_path, "TIER1_TUNABLES")

    assert band_owned == {
        "temp_low",
        "temp_high",
        "vpd_low",
        "vpd_high",
        "gl_dli_target",
        "gl_sunrise_hour",
        "gl_sunset_hour",
        "sw_gl_auto_mode",
    }
    assert not (band_owned & tier1), f"Band-owned params must not be Tier 1 tunables: {band_owned & tier1}"


def test_plan_required_params_match_registry_tier1_and_have_readback():
    """The mandatory full-horizon surface must be only effectful Tier 1 knobs.

    Reserved/no-op firmware globals may remain in the registry for operator
    visibility, but they must not be required in every Hermes plan.
    """
    mcp_path = Path(__file__).resolve().parent.parent / "mcp" / "server.py"
    required = _assigned_set(mcp_path, "PLAN_REQUIRED_PARAMS")
    tier1 = _assigned_set(mcp_path, "TIER1_TUNABLES")
    registry_tier1 = {n for n, d in REGISTRY.items() if d.planner_pushable and d.tier == 1}

    assert required == tier1 == registry_tier1
    assert not {"mist_vent_close_lead_s", "mist_vent_reopen_delay_s", "summer_vent_min_runtime_s"} & required
    missing_readback = sorted(p for p in required if not REGISTRY[p].cfg_readback_object_id)
    assert not missing_readback


def test_per_circuit_lighting_thresholds_are_planner_pushable_but_not_required_tier1():
    """Iris should tune Tempest lux cutoffs through per-circuit knobs from
    observation evidence without making them mandatory every-waypoint Tier 1
    params. Legacy shared gl_lux_* values remain dispatcher/default context.
    """
    assert not REGISTRY["gl_lux_threshold"].planner_pushable
    assert REGISTRY["gl_lux_threshold"].tier == 2
    assert REGISTRY["gl_lux_threshold"].push_owner == "dispatcher_default"
    assert not REGISTRY["gl_lux_hysteresis"].planner_pushable
    assert REGISTRY["gl_lux_hysteresis"].tier == 2
    assert REGISTRY["gl_lux_hysteresis"].push_owner == "dispatcher_default"
    for param in (
        "gl_main_dli_target",
        "gl_main_lux_threshold",
        "gl_main_lux_hysteresis",
        "gl_main_sunrise_hour",
        "gl_main_sunset_hour",
        "gl_main_min_on_s",
        "gl_main_min_off_s",
        "gl_grow_dli_target",
        "gl_grow_lux_threshold",
        "gl_grow_lux_hysteresis",
        "gl_grow_sunrise_hour",
        "gl_grow_sunset_hour",
        "gl_grow_min_on_s",
        "gl_grow_min_off_s",
        "sw_gl_main_auto_mode",
        "sw_gl_grow_auto_mode",
    ):
        assert param in REGISTRY
        assert REGISTRY[param].planner_pushable
        assert REGISTRY[param].tier == 2
        assert param in PLANNER_PUSHABLE_REG


def test_lighting_automation_audit_static_passes():
    """The lighting audit is the prompt-to-artifact guard for the per-circuit
    lighting control story. Static mode must stay green without requiring live
    services or an ESP32 OTA.
    """
    import subprocess

    result = subprocess.run(
        ["/srv/greenhouse/.venv/bin/python", "scripts/audit-lighting-automation.py", "--static-only"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_lighting_automation_audit_enforces_post_ota_proof():
    """The strict live lighting gate must require more than source wiring.
    Completion needs readbacks, confirmed setpoint delivery, firmware telemetry,
    and Lutron state evidence after OTA.
    """
    src = Path("scripts/audit-lighting-automation.py").read_text()

    assert "post-OTA cfg readbacks" in src
    assert "post-OTA setpoint confirmations" in src
    assert "post-OTA Lutron state evidence" in src
    assert "confirmed_at IS NOT NULL" in src
    assert "firmware_state/firmware_reason blank until OTA" in src
    assert "bool_or(state) AS saw_on" in src
    assert "bool_or(NOT state) AS saw_off" in src
    assert "per-circuit cfg readbacks are live; firmware supports per-circuit lighting pushes" in src
    assert "confirmed_at >= COALESCE(latest_fw.first_ts" in src
    assert "'cfg_readback' AS kind" in src


def test_firmware_lighting_telemetry_fails_closed_when_time_invalid():
    controls = Path("firmware/greenhouse/controls.yaml").read_text()
    greenhouse = Path("firmware/greenhouse.yaml").read_text()
    hardware = Path("firmware/greenhouse/hardware.yaml").read_text()

    time_block = greenhouse[greenhouse.index("time:") : greenhouse.index("# ───────────────────── BINARY SENSORS")]
    assert "platform: homeassistant" in time_block
    assert "id: sntp_time" in time_block
    assert "platform: sntp" not in time_block
    assert 'name: "Controller Time Status"' in greenhouse
    assert 'name: "SNTP Status"' not in greenhouse
    assert 'ESP_LOGW("grow_light","main OFF: time_invalid")' in controls
    assert 'ESP_LOGW("grow_light","grow OFF: time_invalid")' in controls
    assert 'id(gl_main_reason).publish_state("time_invalid")' in controls
    assert 'id(gl_grow_reason).publish_state("time_invalid")' in controls
    assert "id(grow_light_main).turn_off()" in controls
    assert "id(grow_light_grow).turn_off()" in controls
    lighting_text_block = hardware[hardware.index("id: gl_main_state_text") : hardware.index("id: ts_lead_fan")]
    assert lighting_text_block.count("update_interval: never") == 4


def test_lighting_automation_audit_renders_public_panels():
    """The live audit should prove the public lighting embeds render, not just
    that Grafana dashboard JSON contains the expected SQL.
    """
    src = Path("scripts/audit-lighting-automation.py").read_text()

    assert "def render_panel(" in src
    assert 'body.startswith(b"\\x89PNG")' in src
    assert '("site-home", 36, 1680, 420)' in src
    assert '("site-climate-lighting", 16, 1360, 340)' in src
    assert '("site-climate-lighting", 17, 1680, 420)' in src
    assert "rendered Grafana panel" in src


def test_lighting_completion_make_target_requires_ota_proof():
    """The final lighting proof command should fail missing post-OTA evidence
    instead of accepting a BLOCKED result as close-enough.
    """
    makefile = Path("Makefile").read_text()

    assert "lighting-audit-complete:" in makefile
    assert "scripts/audit-lighting-automation.py --live --require-ota" in makefile


def test_lighting_automation_audit_checks_live_public_site():
    """The live lighting proof should verify the served verdify.ai pages, not
    only local build artifacts.
    """
    src = Path("scripts/audit-lighting-automation.py").read_text()

    assert "https://verdify.ai/" in src
    assert "https://verdify.ai/greenhouse/lighting/" in src
    assert "https://verdify.ai/reference/ai-tunables/" in src
    assert "live public home page" in src
    assert "live public lighting page" in src
    assert "live public tunables page" in src
    assert "Circuit Policy And Forecast Bands" in src
    assert "Firmware state and reason fields appear after the next ESP32 OTA" in src
    assert "gl_main_lux_threshold" in src
    assert "MCP rejects planner writes" in src


def test_lighting_automation_audit_checks_forecast_graph_labels():
    """The forecast-band graph proof should include the user-facing labels and
    shaded hysteresis fills, not only the backing SQL function.
    """
    src = Path("scripts/audit-lighting-automation.py").read_text()

    assert "lighting forecast graph labels and fills" in src
    for token in (
        "Tempest/Forecast Lux",
        "Main ON Threshold",
        "Main OFF Threshold",
        "Grow ON Threshold",
        "Grow OFF Threshold",
        "Main Expected On",
        "Grow Expected On",
        "custom.fillBelowTo",
    ):
        assert token in src


def test_lighting_automation_audit_checks_policy_source_and_hysteresis_contracts():
    src = Path("scripts/audit-lighting-automation.py").read_text()

    assert "lighting policy source-of-truth guard" in src
    assert "lighting graph hysteresis contract" in src
    assert "ESP32 readbacks are excluded" in src
    assert "WITH RECURSIVE bounds AS" in src
    assert "main_seed_on" in src
    assert "grow_seed_on" in src


def test_lighting_automation_audit_checks_tunable_and_lutron_contracts():
    """The proof gate should cover planner ownership of per-circuit tunables
    and the real Lutron switch path, because those are enforcement boundaries.
    """
    src = Path("scripts/audit-lighting-automation.py").read_text()

    assert "tunable registry per-circuit lighting contract" in src
    assert 'REGISTRY[param].push_owner != "planner"' in src
    assert "param not in PLANNER_PUSHABLE_REG" in src
    assert "REGISTRY[param].tier != 2" in src
    assert "legacy shared lighting params are read-only" in src
    assert 'REGISTRY[param].push_owner != "dispatcher_default"' in src
    assert "Lutron switch enforcement path" in src
    assert '"switch.greenhouse_main": "grow_light_main"' in src
    assert '"switch.greenhouse_grow": "grow_light_grow"' in src
    assert '"light.greenhouse_main"' in src
    assert '"light.greenhouse_grow"' in src


def test_lighting_automation_audit_checks_live_planner_context():
    """The live audit should prove the planner prompt receives the per-circuit
    policy rows and Tempest threshold evidence, not only that the shell script
    contains those SQL snippets.
    """
    src = Path("scripts/audit-lighting-automation.py").read_text()

    assert "live planner lighting context" in src
    assert 'run(["bash", "scripts/gather-plan-context.sh"], timeout=90)' in src
    assert "PER-CIRCUIT LIGHTING POLICY" in src
    assert "grow|grow_light_grow" in src
    assert "main|grow_light_main" in src
    assert "TEMPEST LUX THRESHOLD RECOMMENDATION" in src
    assert "ESP32 cfg readbacks are excluded from this source-of-truth view" in src
    assert "Set gl_main_lux_threshold/gl_main_lux_hysteresis and gl_grow_lux_threshold/gl_grow_lux_hysteresis" in src


def test_lighting_automation_audit_checks_mcp_set_tunable_gate():
    """The live audit should prove the MCP gate accepts the new per-circuit
    lighting knobs and rejects the retired shared lighting threshold.
    """
    src = Path("scripts/audit-lighting-automation.py").read_text()

    assert "MCP lighting set_tunable gate" in src
    assert "gl_main_lux_threshold" in src
    assert "sw_gl_main_auto_mode" in src
    assert "gl_lux_threshold" in src
    assert "trigger_id not found in plan_delivery_log" in src
    assert "not planner-pushable" in src


def test_mcp_set_plan_rejects_non_policy_tunables():
    server = (Path(iris_planner.__file__).resolve().parent.parent / "mcp" / "server.py").read_text()
    start = server.index("async def set_plan")
    end = server.index("@mcp.tool()", start + 1)
    body = server[start:end]
    assert "non_policy_params" in body
    assert "param not in BAND_OWNED_PARAMS and param not in PLANNER_PUSHABLE_REG" in body
    assert "Plan contains non-policy tunables" in body


def test_alert_monitor_detects_planner_delivery_outages():
    """Hermes outages and missed required plans must be visible alerts."""
    import tasks

    src = Path(tasks.__file__).read_text()
    assert "planner_gateway_delivery_failed" in src
    assert "system.hermes" in src
    assert "WITH last_success AS" in src
    assert "gateway_status = 0" in src
    assert "planner_required_plan_missed" in src
    assert "system.planner_required_plan" in src
    assert "planner_trigger_ledger" in src
    assert "event_type IN ('SUNRISE', 'SUNSET', 'MIDNIGHT')" in src
    assert "row_number() OVER (PARTITION BY event_type ORDER BY expected_at DESC)" in src
    assert "status <> 'plan_written'" in src


def test_planning_milestones_use_phase4_trigger_set():
    import tasks

    src = Path(tasks.__file__).read_text()
    start = src.index("def _compute_milestones")
    end = src.index("async def _log_plan_delivery", start)
    body = src[start:end]
    cache_start = body.index("_milestones_cache = {")
    cache_end = body.index("}", cache_start)
    milestone_table = body[cache_start:cache_end]
    for key in ("SUNRISE", "SOLAR_MAX", "TRANSITION:peak_stress", "TRANSITION:decline", "SUNSET"):
        assert key in milestone_table
    for retired in ("fixed_midnight", "fixed_pre_dawn", "fixed_midday", "fixed_afternoon", "fixed_evening"):
        assert retired not in milestone_table


def test_prompt_builder_events_validate_delivery_log_schema():
    """Every emitted planner event must be accepted by PlanDeliveryLogRow."""
    for event_type in iris_planner._PROMPT_BUILDERS:
        PlanDeliveryLogRow.model_validate(
            {
                "event_type": event_type,
                "event_label": "<label>",
                "session_key": "hermes:iris:main:trigger:00000000-0000-0000-0000-000000000000",
                "wake_mode": "now"
                if event_type in {"SUNRISE", "SUNSET", "FORECAST_DEVIATION", "MANUAL"}
                else "next-heartbeat",
                "gateway_status": 200,
                "gateway_body": "{}",
            }
        )


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
    assert "pdl.gateway_status BETWEEN 200 AND 299" in body, (
        "_resolve_delivery_log must not correlate failed gateway deliveries to later plans"
    )


def test_resolve_delivery_log_fallback_is_legacy_null_uuid_only():
    """Rows with trigger_id must never use the old 2h time-window fallback."""
    import tasks

    src = Path(tasks.__file__).read_text()
    start = src.index("async def _resolve_delivery_log")
    end = src.index("async def ", start + 1)
    body = src[start:end]
    assert "pj.trigger_id = pdl.trigger_id" in body
    fallback = body.split("Legacy fallback for pre-v1.4 rows only", 1)[1]
    assert "pdl.trigger_id IS NULL" in fallback
    assert "pj.trigger_id IS NULL" in fallback


def test_failed_plan_delivery_logs_delivery_failed_status():
    import tasks

    src = Path(tasks.__file__).read_text()
    start = src.index("async def _log_plan_delivery")
    end = src.index("async def _deliver_and_log", start)
    body = src[start:end]
    assert 'result.get("delivered") is False' in body
    assert 'result.get("gateway_status") is not None' in body
    assert 'explicit_status = "delivery_failed"' in body


def test_deliver_and_log_precreates_delivery_row_before_post():
    import tasks

    src = Path(tasks.__file__).read_text()
    start = src.index("async def _deliver_and_log")
    end = src.index("async def _resolve_delivery_log", start)
    body = src[start:end]
    assert "prepare_delivery_result(event_type, label, instance=instance)" in body
    assert "delivery_id = await _log_plan_delivery(pool, pre_result)" in body
    assert 'trigger_id=pre_result["trigger_id"]' in body


def test_planner_expected_trigger_ledger_is_materialized_before_delivery():
    import tasks

    src = Path(tasks.__file__).read_text()
    assert "async def _ensure_expected_planner_triggers" in src
    assert "planner_trigger_ledger" in src
    assert "ON CONFLICT (greenhouse_id, event_type, expected_at)" in src
    assert "expected trigger was not delivered before due_at" in src
    assert "plan_delivery_log_id" in src


def test_planner_sla_lifecycle_uses_configured_pair_timeout():
    import tasks

    src = Path(tasks.__file__).read_text()
    start = src.index("async def _expire_planner_trigger_slas")
    end = src.index("async def _log_plan_delivery", start)
    body = src[start:end]
    assert '_sla_seconds(row["event_type"], row["instance"])' in body
    assert "status = 'timed_out'" in body
    assert "status      = 'missed'" in body
    assert "await _sync_planner_trigger_ledger(conn)" in body


def test_active_future_plan_range_guard_uses_tunable_registry():
    import tasks

    src = Path(tasks.__file__).read_text()
    assert "planner_tunable_range_drift" in src
    assert "registry_value_error(parameter, value)" in src
    assert "controller_locked_on" in src
    assert "system.planner_tunable_range" in src
    start = src.index("# 7d. Active/future tunable range drift")
    end = src.index("# 7e. Future plan horizon guard", start)
    body = src[start:end]
    assert "now() - interval '10 minutes'" not in body
    assert "LIMIT 10000" in body


def test_alert_monitor_detects_missing_future_plan_horizon():
    import tasks

    src = Path(tasks.__file__).read_text()
    assert "planner_plan_horizon_missing" in src
    assert "system.planner_plan_horizon" in src
    assert "ts > now()" in src
    assert "plan_id NOT LIKE 'iris-oneshot-%'" in src


def test_dispatcher_coerces_registry_bounds_before_insert_and_push():
    import tasks

    high_value, high_reason = tasks._coerce_registry_value("mister_all_kpa", 2.8)
    assert high_value == 2.5
    assert high_reason is not None
    assert "nearest_safe=2.5" in high_reason

    low_value, low_reason = tasks._coerce_registry_value("mister_engage_delay_s", 0)
    assert low_value == 30.0
    assert low_reason is not None
    assert "nearest_safe=30" in low_reason

    switch_value, switch_reason = tasks._coerce_registry_value("sw_dwell_gate_enabled", 2.0)
    assert switch_value is None
    assert switch_reason is not None
    assert "outside registry switch values [0, 1]" in switch_reason


def test_dispatcher_direct_push_uses_dispatchable_changes_only():
    import tasks

    src = Path(tasks.__file__).read_text()
    start = src.index("async def setpoint_dispatcher")
    end = src.index("def _fetch_forecast", start)
    body = src[start:end]
    assert "dispatchable_changes: list[tuple[str, float, str]] = []" in body
    assert "dispatchable_changes.append((param, float(val), source))" in body
    assert "for param, val, _source in dispatchable_changes:" in body
    assert "for param, val in changes:" in body


def test_dispatcher_propagates_plan_audit_to_setpoint_changes():
    import tasks

    src = Path(tasks.__file__).read_text()
    start = src.index("async def setpoint_dispatcher")
    end = src.index("def _fetch_forecast", start)
    body = src[start:end]
    assert "trigger_id, planner_instance FROM v_active_plan" in body
    assert "planner_meta =" in body
    assert "trigger_id=change_trigger_id" in body
    assert "(ts, parameter, value, source, trigger_id, planner_instance, delivery_status)" in body
    assert "VALUES (now(), $1, $2, $3, $4::uuid, $5, 'pending')" in body


def test_dispatcher_writes_guardrail_hold_audits_without_setpoint_push():
    import tasks

    src = Path(tasks.__file__).read_text()
    start = src.index("async def setpoint_dispatcher")
    end = src.index("def _fetch_forecast", start)
    body = src[start:end]
    assert "_write_clamp_audit_rows(conn, clamps_to_log, set())" in body
    assert "guardrail hold/audit row(s) with no ESP32 push" in body
    assert "plan_id" in body
    assert "plan_ts" in body


def test_dispatcher_clamp_audit_rows_carry_plan_metadata():
    import tasks

    src = Path(tasks.__file__).read_text()
    assert "INSERT INTO setpoint_clamps" in src
    assert "status, plan_id, plan_ts, trigger_id, planner_instance" in src
    assert '"plan_id": r["plan_id"]' in src
    assert '"plan_ts": r["ts"]' in src


def test_write_clamp_audit_rows_marks_unchanged_guardrail_holds():
    import tasks

    class FakeConn:
        def __init__(self):
            self.calls = []

        async def execute(self, sql, *args):
            self.calls.append((sql, args))

    conn = FakeConn()
    rows = [
        {
            "parameter": "fog_escalation_kpa",
            "requested": 0.9,
            "applied": 0.2,
            "band_lo": 0.0,
            "band_hi": 0.2,
            "reason": "vpd_high_moisture_guardrail",
            "plan_id": "iris-test",
            "plan_ts": None,
            "trigger_id": None,
            "planner_instance": "opus",
        }
    ]

    written = asyncio.run(tasks._write_clamp_audit_rows(conn, rows, set()))

    assert written == 1
    assert len(conn.calls) == 1
    args = conn.calls[0][1]
    assert args[0] == "fog_escalation_kpa"
    assert args[6] == "held_by_guardrail"
    assert args[7] == "iris-test"
    assert args[10] == "opus"


def test_plan_transition_audit_migration_penalizes_guardrail_dependence():
    migration = (REPO_ROOT / "db" / "migrations" / "120-plan-transition-guardrail-audit.sql").read_text()
    assert "fn_plan_transition_audit" in migration
    assert "v_plan_guardrail_scorecard" in migration
    assert "held_by_guardrail" in migration
    assert "v_anchor - COALESCE(v_penalty, 0)" in migration


def test_plan_context_surfaces_transition_audit_and_corrected_vpd_forecast():
    script = (REPO_ROOT / "scripts" / "gather-plan-context.sh").read_text()
    assert "GUARDRAIL-AWARE TRANSITION AUDIT" in script
    assert "fn_plan_transition_audit" in script
    assert "corrected_vpd_kpa" in script
    assert "'00-06h', '0-6h', '06-24h', '6-24h'" in script
    assert "HOT/DRY VENTILATE UTILIZATION" in script


def test_plan_evaluate_returns_guardrail_scorecard():
    server = (REPO_ROOT / "mcp" / "server.py").read_text()
    start = server.index("async def plan_evaluate")
    end = server.index("@mcp.tool()", start + 1) if "@mcp.tool()" in server[start + 1 :] else len(server)
    body = server[start:end]
    assert "v_plan_guardrail_scorecard" in body
    assert '"guardrail_scorecard": dict(guardrail_row)' in body


def test_send_to_iris_targets_hermes_gateway():
    src = Path(iris_planner.__file__).read_text()
    start = src.index("def send_to_iris")
    body = src[start:]
    assert 'instance: PlannerInstance = "local"' in body
    assert "OPENCLAW" not in body
    assert "/v1/runs" in body
    assert "HERMES_URL" in body
    assert "HERMES_API_KEY" in body
    assert "hermes_run_id" in body
    assert '"MANUAL"' in src
    assert "prepare_delivery_result" in src


def test_mcp_plan_run_uses_manual_trigger_and_delivery_log():
    server = (Path(iris_planner.__file__).resolve().parent.parent / "mcp" / "server.py").read_text()
    start = server.index("async def plan_run")
    end = server.index("@mcp.tool()", start + 1)
    body = server[start:end]
    assert "send_to_iris(" in body
    assert '"MANUAL",' in body
    assert "_insert_plan_delivery_log" in body
    assert "prepare_delivery_result" in body
    assert "trigger_id" in body
    assert "acknowledge-only smoke" in body


def test_replan_fallback_uses_audited_helper_not_direct_post():
    script = Path("scripts/check-replan-trigger.sh").read_text()
    assert "hermes-trigger.py" in script
    assert "curl" not in script
    helper = Path("scripts/hermes-trigger.py").read_text()
    assert "prepare_delivery_result" in helper
    assert "ON CONFLICT (trigger_id)" in helper
    assert "send_to_iris(" in helper


def test_knowledge_search_defaults_to_full_embedding_corpus():
    server = (Path(iris_planner.__file__).resolve().parent.parent / "mcp" / "server.py").read_text()
    start = server.index("async def knowledge_search")
    end = server.index("# ═══════════════════════════════════════════════════════════════", start)
    body = server[start:end]
    assert 'source_types: str = "lesson,plan,site_doc,playbook,observation"' in body
    assert '{"lesson", "plan", "site_doc", "playbook", "observation"}' in body
    assert "planner_lessons pl" in body
    assert "pl.is_active = true" in body
    assert "pl.superseded_by IS NULL" in body


def test_firmware_misters_have_no_standalone_zone_stress_path():
    controls = Path("firmware/greenhouse/controls.yaml").read_text()
    assert "bool zone_mister_demand = humidity_demand && mister_vent_ok;" in controls
    assert "&& humidity_demand" in controls
    assert "&& (humidity_demand || any_zone_stressed)" not in controls


def test_site_content_populator_indexes_public_website_markdown():
    script = Path("scripts/populate-site-content.py").read_text()
    assert 'WEBSITE_ROOT = Path("/mnt/iris/verdify-vault/website")' in script
    assert "(WEBSITE_ROOT, WEBSITE_ROOT.parent)" in script
    assert "Walks /mnt/iris/verdify-vault/website/**/*.md" in script


def test_embedding_chunker_hard_splits_oversized_blocks():
    script_path = Path("scripts/embed-corpora.py")
    spec = importlib.util.spec_from_file_location("embed_corpora_script", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    chunks = module._chunk_text("x" * 10000, max_bytes=2048)
    assert len(chunks) > 1
    assert all(len(chunk.encode("utf-8")) <= 2048 for chunk in chunks)


def test_mcp_set_plan_requires_audited_trigger():
    server = (Path(iris_planner.__file__).resolve().parent.parent / "mcp" / "server.py").read_text()
    start = server.index("async def set_plan")
    end = server.index("@mcp.tool()", start + 1)
    body = server[start:end]
    assert "normalized_trigger_id" in body
    assert "trigger_id is required for set_plan MCP writes" in body
    assert "Copy trigger_id exactly from the planning prompt audit headers" in body
    assert "plan_id is required" in body
    assert "transitions is required" in body
    assert "include_input=False" in body
    assert "trigger_id not found in plan_delivery_log" in body
    assert "planner_instance does not match plan_delivery_log" in body


def test_mcp_set_plan_updates_delivery_log_by_trigger_id_immediately():
    server = (Path(iris_planner.__file__).resolve().parent.parent / "mcp" / "server.py").read_text()
    start = server.index("async def set_plan")
    end = server.index("@mcp.tool()", start + 1)
    body = server[start:end]
    assert "UPDATE plan_delivery_log" in body
    assert "resulting_plan_id = $2" in body
    assert "plan_written_at   = $3" in body
    assert "status            = 'plan_written'" in body
    assert '"delivery_status": "plan_written" if normalized_trigger_id else None' in body


def test_mcp_set_plan_populates_plan_journal_feedback_fields():
    server = (Path(iris_planner.__file__).resolve().parent.parent / "mcp" / "server.py").read_text()
    start = server.index("async def set_plan")
    end = server.index("@mcp.tool()", start + 1)
    body = server[start:end]
    assert "params_seen = sorted" in body
    assert "conditions_summary" in body
    assert "params_changed" in body
    assert "$9::text[]" in body


def test_mcp_set_tunable_resolves_trigger_ledger_with_oneshot_plan():
    server = (Path(iris_planner.__file__).resolve().parent.parent / "mcp" / "server.py").read_text()
    start = server.index("async def set_tunable")
    end = server.index("# ═══════════════════════════════════════════════════════════════", start + 1)
    body = server[start:end]
    assert "trigger_id is required for set_tunable MCP writes" in body
    assert "Copy trigger_id exactly from the planning prompt audit headers into set_tunable" in body
    assert "parameter is required" in body
    assert "value is required" in body
    assert "trigger_id not found in plan_delivery_log" in body
    assert "planner_instance does not match plan_delivery_log" in body
    assert "UPDATE plan_delivery_log" in body
    assert "resulting_plan_id = $2" in body
    assert "plan_written_at   = $3" in body
    assert "status            = 'plan_written'" in body
    assert '"delivery_status": "plan_written" if normalized_trigger_id else None' in body


def test_mcp_rejects_non_validation_solar_acknowledgement():
    server = (Path(iris_planner.__file__).resolve().parent.parent / "mcp" / "server.py").read_text()
    start = server.index("async def acknowledge_trigger")
    body = server[start:]
    assert 'existing["event_type"] in {"SUNRISE", "SUNSET"}' in body
    assert "SUNRISE/SUNSET triggers require set_plan" in body
    assert "validation ack-only" in body


def test_required_plan_alert_ignores_validation_ack_only_rows():
    import tasks

    src = Path(tasks.__file__).read_text()
    start = src.index("WITH latest_required AS")
    end = src.index("if required_misses:", start)
    body = src[start:end]
    assert "event_label NOT ILIKE 'validation%ack-only%'" in body


# ── S24.9.7 — _deliver_and_log sentinel skip (integration-shape) ───


def test_sentinel_import_chain_wired():
    """tasks.py imports the sentinel from iris_planner. Confirms the
    symbol is exposed + named consistently."""
    import tasks

    assert hasattr(tasks, "CONTEXT_GATHER_FAILED_SENTINEL")
    assert tasks.CONTEXT_GATHER_FAILED_SENTINEL == iris_planner.CONTEXT_GATHER_FAILED_SENTINEL
