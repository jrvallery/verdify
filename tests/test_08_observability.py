"""
Test 08: Tier 1 observability — override_events, setpoint_clamps, /setpoints fail-loud.

Smoke tests covering the 96h-review Tier 1 changes (migration 080 + dispatcher
clamp logging + ESP32 push retry + /setpoints 503 on NULL band). Pre-migration,
every query in TestSchema below fails — that's the "would fail without the
change" gate per the fleet DoD.
"""

import ast
import subprocess
import sys
from pathlib import Path

from conftest import db_query

sys.path.insert(0, "/srv/verdify/ingestor")

REPO_ROOT = Path(__file__).resolve().parents[1]


def _assigned_frozenset(path: Path, name: str) -> set[str]:
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


def _repo_entity_map():
    ingestor_path = str(REPO_ROOT / "ingestor")
    if ingestor_path in sys.path:
        sys.path.remove(ingestor_path)
    sys.path.insert(0, ingestor_path)
    sys.modules.pop("entity_map", None)
    import entity_map

    return entity_map


class TestSchema:
    """Migration 080 artifacts must exist."""

    def test_override_events_table_exists(self):
        val = db_query("SELECT to_regclass('public.override_events')::text")
        assert val == "override_events", f"override_events table missing: {val!r}"

    def test_override_events_is_hypertable(self):
        val = db_query(
            "SELECT count(*) FROM timescaledb_information.hypertables WHERE hypertable_name = 'override_events'"
        )
        assert int(val) == 1, "override_events is not a hypertable"

    def test_setpoint_clamps_table_exists(self):
        val = db_query("SELECT to_regclass('public.setpoint_clamps')::text")
        assert val == "setpoint_clamps", f"setpoint_clamps table missing: {val!r}"

    def test_setpoint_clamps_is_hypertable(self):
        val = db_query(
            "SELECT count(*) FROM timescaledb_information.hypertables WHERE hypertable_name = 'setpoint_clamps'"
        )
        assert int(val) == 1, "setpoint_clamps is not a hypertable"

    def test_override_activity_view_queryable(self):
        val = db_query("SELECT count(*) FROM v_override_activity_24h")
        assert val is not None

    def test_clamp_activity_view_queryable(self):
        val = db_query("SELECT count(*) FROM v_clamp_activity_24h")
        assert val is not None


class TestDispatcherWiring:
    """Dispatcher code must contain the Tier 1 audit hooks."""

    TASKS_PATH = "/srv/verdify/ingestor/tasks.py"

    def _read(self) -> str:
        with open(self.TASKS_PATH) as f:
            return f.read()

    def test_dispatcher_inserts_clamp_rows(self):
        body = self._read()
        assert "INSERT INTO setpoint_clamps" in body, (
            "setpoint_dispatcher must INSERT into setpoint_clamps when planner values are clamped (Tier 1 #2)"
        )

    def test_dispatcher_retries_esp32_push(self):
        body = self._read()
        assert "attempt %d/3" in body or "attempt 1/3" in body, "ESP32 direct push must retry on failure (Tier 1 #4)"

    def test_dispatcher_suppresses_duplicate_notify_pushes(self):
        body = self._read()
        push_helper = (REPO_ROOT / "ingestor" / "esp32_push.py").read_text()
        assert "shared.recently_pushed[param] = time.time()" in body
        assert "LISTEN/NOTIFY real-time listener" in body
        assert "_BATCH_PAUSE_EVERY" in push_helper
        assert "_MIN_COMMAND_INTERVAL_S" in push_helper
        assert "async with _PUSH_LOCK" in push_helper
        assert "await asyncio.sleep(_BATCH_PAUSE_S)" in push_helper

    def test_realtime_listener_validates_outbound_registry_bounds(self):
        ingestor = (REPO_ROOT / "ingestor" / "ingestor.py").read_text()
        assert "from verdify_schemas.tunable_registry import get as get_tunable" in ingestor
        assert "def _accept_outbound_setpoint" in ingestor
        assert "Rejecting outbound setpoint" in ingestor
        assert "if not _accept_outbound_setpoint(param, val)" in ingestor

    def test_dispatcher_escalates_push_failure(self):
        body = self._read()
        assert "'esp32_push_failed'" in body, (
            "Exhausted ESP32 push retries must INSERT alert_log alert_type='esp32_push_failed' (Tier 1 #4)"
        )


class TestHeapPressureObservability:
    """Heap-pressure firmware sensors must become live DB alerts."""

    def test_firmware_declares_heap_pressure_problem_sensors(self):
        body = (REPO_ROOT / "firmware/greenhouse.yaml").read_text()
        assert "id: bs_heap_pressure_warning" in body
        assert 'name: "Heap Pressure Warning"' in body
        assert "id: bs_heap_pressure_critical" in body
        assert 'name: "Heap Pressure Critical"' in body
        assert "Heap pressure WARNING" in body
        assert "Heap pressure CRITICAL" in body

    def test_entity_map_routes_heap_pressure_binary_sensors(self):
        body = (REPO_ROOT / "ingestor/entity_map.py").read_text()
        assert '"heap_pressure_warning": "heap_pressure_warning"' in body
        assert '"heap_pressure_critical": "heap_pressure_critical"' in body

    def test_alert_monitor_checks_heap_pressure_state(self):
        body = (REPO_ROOT / "ingestor/tasks.py").read_text()
        assert "'heap_pressure_warning', 'heap_pressure_critical'" in body
        assert "recent_true" in body
        assert "latest_state" in body
        assert "last_critical_event_ts" in body
        assert "healthy_after_critical" in body
        assert "healthy_heap_samples_after_event" in body
        assert "critical_logs_30m" in body
        assert "SELECT heap_bytes, ts" in body
        assert '"alert_type": "heap_pressure_warning"' in body
        assert '"alert_type": "heap_pressure_critical"' in body
        assert '"sensor_id": "equipment.heap_pressure_critical"' in body

    def test_greenhouse_state_refresh_registered(self):
        body = (REPO_ROOT / "ingestor/tasks.py").read_text()
        migration = (REPO_ROOT / "db/migrations/098-greenhouse-state-refresh.sql").read_text()
        assert "refresh_greenhouse_state" in body
        assert "CREATE OR REPLACE FUNCTION refresh_greenhouse_state" in migration
        assert "CREATE OR REPLACE VIEW v_greenhouse_state" in migration
        assert "interval '14 days'" in migration
        assert "Compatibility no-op" in migration
        assert "ORDER BY equipment, ts DESC, state ASC" in migration

    def test_alert_monitor_refreshes_existing_alert_payloads(self):
        body = (REPO_ROOT / "ingestor/tasks.py").read_text()
        assert "alert refresh skipped" in body
        assert "threshold_value=$5" in body
        assert "Same-severity updates intentionally stay quiet" in body
        assert "disposition IN ('open', 'acknowledged')" in body

    def test_vpd_stress_alert_requires_recent_active_stress(self):
        body = (REPO_ROOT / "ingestor/tasks.py").read_text()
        assert "recent_high_fraction" in body
        assert "last 15m" in body
        assert 'float(row["recent_high_fraction"] or 0.0) >= 0.5' in body


class TestV2ControlDiagnostics:
    """Controller v2 timers and assist flags must be observable."""

    def test_migration_094_applied(self):
        cols = db_query(
            "SELECT string_agg(column_name, ',' ORDER BY column_name) "
            "FROM information_schema.columns "
            "WHERE table_name='diagnostics' AND column_name IN ("
            "'sealed_timer_s','vpd_watch_timer_s','mist_backoff_timer_s','vent_mist_assist_active')"
        )
        assert cols == "mist_backoff_timer_s,sealed_timer_s,vent_mist_assist_active,vpd_watch_timer_s"

    def test_firmware_declares_v2_diagnostic_sensors(self):
        body = (REPO_ROOT / "firmware/greenhouse/sensors.yaml").read_text()
        assert "id: ctl_sealed_timer_s" in body
        assert "id: ctl_vpd_watch_timer_s" in body
        assert "id: ctl_mist_backoff_timer_s" in body
        assert "id: ctl_vent_mist_assist_active" in body

    def test_controls_publishes_v2_diagnostics_and_assist_override(self):
        body = (REPO_ROOT / "firmware/greenhouse/controls.yaml").read_text()
        assert "ctl_state.vent_mist_assist_active" in body
        assert 'add("vent_mist_assist")' in body
        assert 'add("fog_heat_assist")' in body
        assert "id(ctl_mist_backoff_timer_s).publish_state(" in body
        assert "id(ctl_vent_mist_assist_active).publish_state(" in body

    def test_entity_map_and_ingestor_route_v2_diagnostics(self):
        entity_map = (REPO_ROOT / "ingestor/entity_map.py").read_text()
        ingestor = (REPO_ROOT / "ingestor/ingestor.py").read_text()
        for col in ("sealed_timer_s", "vpd_watch_timer_s", "mist_backoff_timer_s", "vent_mist_assist_active"):
            assert f'"{col}": "{col}"' in entity_map
            assert col in ingestor


class TestContractDriftGuardrails:
    """Static checks for firmware/planner contracts that have drifted before."""

    def test_dispatcher_declares_vpd_low_band_owned(self):
        band_params = _assigned_frozenset(REPO_ROOT / "ingestor" / "tasks.py", "BAND_DRIVEN_PARAMS")
        assert {"temp_low", "temp_high", "vpd_low", "vpd_high"} <= band_params

        tasks_source = (REPO_ROOT / "ingestor" / "tasks.py").read_text()
        assert "fn_band_setpoints(now())" in tasks_source
        assert "param in BAND_DRIVEN_PARAMS" in tasks_source

    def test_alert_monitor_covers_obs3_relief_and_latch(self):
        tasks_source = (REPO_ROOT / "ingestor" / "tasks.py").read_text()
        assert '"alert_type": "firmware_relief_ceiling"' in tasks_source
        assert '"alert_type": "firmware_vent_latched"' in tasks_source
        assert 'sensor_id": "diag.relief_cycle_count"' in tasks_source
        assert 'sensor_id": "diag.vent_latch_timer_s"' in tasks_source
        assert "relief >= 2" in tasks_source
        assert "relief >= 3" in tasks_source
        assert "latch >= 600" in tasks_source
        assert "latch >= 1200" in tasks_source

    def test_alert_monitor_checks_expected_firmware_pin(self):
        config_source = (REPO_ROOT / "ingestor" / "config.py").read_text()
        tasks_source = (REPO_ROOT / "ingestor" / "tasks.py").read_text()
        makefile = (REPO_ROOT / "Makefile").read_text()

        assert "EXPECTED_FIRMWARE_VERSION" in config_source
        assert "EXPECTED_FIRMWARE_VERSION_FILE" in config_source
        assert "firmware_version_mismatch" in tasks_source
        assert "diag.firmware_version" in tasks_source
        assert "/srv/verdify/state/expected-firmware-version" in config_source
        assert "/srv/verdify/state/expected-firmware-version" in makefile
        assert "pending-fw-version.txt" in makefile

    def test_sw_mister_closes_vent_routes_end_to_end(self):
        entity_map = _repo_entity_map()
        assert entity_map.SETPOINT_MAP["mister_closes_vent"] == "sw_mister_closes_vent"
        assert entity_map.CFG_READBACK_MAP["sw_mister_closes_vent"] == "sw_mister_closes_vent"
        assert entity_map.SWITCH_TO_ENTITY["sw_mister_closes_vent"] == "mister_closes_vent"

        from verdify_schemas.tunables import ALL_TUNABLES, SWITCH_TUNABLES

        assert "sw_mister_closes_vent" in SWITCH_TUNABLES
        assert "sw_mister_closes_vent" in ALL_TUNABLES

        tier1 = _assigned_frozenset(REPO_ROOT / "mcp" / "server.py", "TIER1_TUNABLES")
        assert "sw_mister_closes_vent" in tier1

        controls_source = (REPO_ROOT / "firmware" / "greenhouse" / "controls.yaml").read_text()
        tunables_source = (REPO_ROOT / "firmware" / "greenhouse" / "tunables.yaml").read_text()
        assert 'key == "sw_mister_closes_vent"' in controls_source
        assert "id: sw_mister_closes_vent" in tunables_source


class TestFirmwareCheckTargets:
    """Firmware validation should compile from the active git worktree."""

    def test_makefile_has_worktree_firmware_compile_target(self):
        body = (REPO_ROOT / "Makefile").read_text()
        assert "firmware-check-worktree:" in body
        assert "FIRMWARE_ESPHOME := scripts/firmware-esphome-worktree.sh" in body
        assert "$(FIRMWARE_ESPHOME) compile" in body
        assert "cd /srv/greenhouse/esphome" not in body


class TestSprint18Wiring:
    """Sprint 18: deterministic dispatch — DI-1, PL-5, FW-2, FW-3, OBS-3."""

    TASKS_PATH = "/srv/verdify/ingestor/tasks.py"
    SENSORS_PATH = "/srv/verdify/firmware/greenhouse/sensors.yaml"
    CONTROLS_PATH = "/srv/verdify/firmware/greenhouse/controls.yaml"
    ENTITY_MAP_PATH = "/srv/verdify/ingestor/entity_map.py"
    INGESTOR_PATH = "/srv/verdify/ingestor/ingestor.py"

    @staticmethod
    def _read(path: str) -> str:
        with open(path) as f:
            return f.read()

    # ── DI-1: proportional dead-bands ──
    def test_di1_proportional_dead_band_helper_defined(self):
        body = self._read(self.TASKS_PATH)
        assert "_should_skip" in body, "DI-1 _should_skip() helper must be defined in tasks.py"
        assert "abs(last - val) / max(abs(val), abs_floor)" in body, (
            "DI-1 helper must compute a relative dead-band (abs(delta)/max(|val|, floor))"
        )

    def test_di1_absolute_dead_bands_removed(self):
        body = self._read(self.TASKS_PATH)
        # None of the old magic numbers should survive as standalone dead-band checks.
        for stale in ["abs(last - val) < 0.1", "abs(last - val) < 0.05", "abs(last - val) < 0.02"]:
            assert stale not in body, f"DI-1 left behind an old absolute dead-band check: {stale}"

    # ── PL-5: replan dampening ──
    def test_pl5_sigma_gate_present(self):
        body = self._read(self.TASKS_PATH)
        assert "SIGMA_MULTIPLIER" in body, "PL-5 σ-gate constant must be defined"
        assert "SIGMA_HISTORY_DAYS" in body, "PL-5 σ-history window constant must be defined"
        assert "STDDEV(delta)" in body, "PL-5 must compute STDDEV over forecast_deviation_log"

    # ── FW-2: oscillation views ──
    def test_fw2_view_v_daily_oscillation(self):
        from conftest import db_query

        val = db_query("SELECT to_regclass('v_daily_oscillation')::text")
        assert val == "v_daily_oscillation", "FW-2: v_daily_oscillation view missing"

    def test_fw2_view_summary(self):
        from conftest import db_query

        val = db_query("SELECT to_regclass('v_daily_oscillation_summary')::text")
        assert val == "v_daily_oscillation_summary", "FW-2: v_daily_oscillation_summary view missing"

    # ── FW-3: physics invariants ──
    def test_fw3_invariants_table_defined(self):
        body = self._read(self.TASKS_PATH)
        assert "_PHYSICS_INVARIANTS" in body, "FW-3 invariants table must be defined"
        # Sprint 24 renamed keys to canonical ALL_TUNABLES names and removed
        # non-tunable entries (max_relief_cycles, vpd_max_safe, etc.). Assert
        # representatives from each remaining category: fog window, safety
        # rail, resource budget.
        assert '"fog_time_window_start"' in body, "FW-3 must cover fog_time_window_start bounds"
        assert '"safety_vpd_max"' in body, "FW-3 must cover safety_vpd_max bounds"
        assert '"mister_water_budget_gal"' in body, "FW-3 must cover mister_water_budget_gal bounds"

    def test_fw3_validator_invoked_in_dispatcher(self):
        body = self._read(self.TASKS_PATH)
        assert "_validate_physics" in body, "FW-3 _validate_physics() helper must exist"
        assert "invariant_violation" in body, "FW-3 must tag violations with invariant_violation prefix"

    # ── OBS-3: relief-cycle state to DB ──
    def test_obs3_migration_082_applied(self):
        from conftest import db_query

        cols = db_query(
            "SELECT string_agg(column_name, ',' ORDER BY column_name) "
            "FROM information_schema.columns "
            "WHERE table_name='diagnostics' AND column_name IN ('relief_cycle_count', 'vent_latch_timer_s')"
        )
        assert cols == "relief_cycle_count,vent_latch_timer_s", (
            f"OBS-3 migration 082 did not apply cleanly (got: {cols!r})"
        )

    def test_obs3_sensors_declared(self):
        body = self._read(self.SENSORS_PATH)
        assert "id: ctl_relief_cycle_count" in body, "OBS-3: ctl_relief_cycle_count sensor missing"
        assert "id: ctl_vent_latch_timer_s" in body, "OBS-3: ctl_vent_latch_timer_s sensor missing"

    def test_obs3_controls_publishes_state(self):
        body = self._read(self.CONTROLS_PATH)
        assert "id(ctl_relief_cycle_count).publish_state(" in body, (
            "OBS-3: controls.yaml must publish relief_cycle_count every cycle"
        )
        assert "id(ctl_vent_latch_timer_s).publish_state(" in body, (
            "OBS-3: controls.yaml must publish vent_latch_timer_s every cycle"
        )

    def test_obs3_entity_map_routes(self):
        body = self._read(self.ENTITY_MAP_PATH)
        assert '"relief_cycle_count": "relief_cycle_count"' in body
        assert '"vent_latch_timer_s": "vent_latch_timer_s"' in body

    def test_obs3_ingestor_writes_columns(self):
        body = self._read(self.INGESTOR_PATH)
        assert "relief_cycle_count" in body and "vent_latch_timer_s" in body, (
            "OBS-3: ingestor INSERT must cover new columns"
        )


class TestProbeStalenessWiring:
    """FW-10 (Sprint 17): active_probe_count column + ingestor routing."""

    SENSORS_PATH = "/srv/verdify/firmware/greenhouse/sensors.yaml"
    ENTITY_MAP_PATH = "/srv/verdify/ingestor/entity_map.py"
    INGESTOR_PATH = "/srv/verdify/ingestor/ingestor.py"

    @staticmethod
    def _read(path: str) -> str:
        with open(path) as f:
            return f.read()

    def test_migration_081_applied(self):
        from conftest import db_query

        val = db_query(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='diagnostics' AND column_name='active_probe_count'"
        )
        assert val == "active_probe_count", "migration 081 did not apply — active_probe_count column missing"

    def test_averaging_lambdas_check_probe_staleness(self):
        body = self._read(self.SENSORS_PATH)
        # All three averages must now gate on the per-probe last_*_ms
        # timestamps to avoid stale-cached-value contamination.
        assert (
            "last_north_ms" in body and "last_south_ms" in body and "last_east_ms" in body and "last_west_ms" in body
        ), "averaging lambdas must reference the per-probe last_*_ms timestamps"
        # Count how many averaging contexts the staleness threshold appears in — expect >= 4 (3 averages + active_probe_count sensor)
        count = body.count("STALE = 300000")
        assert count >= 4, f"expected >= 4 stale-guard constants in sensors.yaml, found {count}"

    def test_active_probe_count_sensor_declared(self):
        body = self._read(self.SENSORS_PATH)
        assert "id: active_probe_count" in body, "active_probe_count template sensor missing from sensors.yaml"

    def test_entity_map_routes_active_probe_count(self):
        body = self._read(self.ENTITY_MAP_PATH)
        assert '"active_probe_count": "active_probe_count"' in body, (
            "DIAGNOSTIC_MAP must route active_probe_count to the diagnostics column"
        )

    def test_sensor_health_allows_startup_probe_settling(self):
        body = (REPO_ROOT / "scripts" / "sensor-health-sweep.sh").read_text()
        assert "uptime_s::text" in body
        assert "STARTUP_SETTLING" in body
        assert "startup settling" in body

    def test_firmware_deploy_waits_for_expected_version(self):
        makefile = (REPO_ROOT / "Makefile").read_text()
        sweep = (REPO_ROOT / "scripts" / "sensor-health-sweep.sh").read_text()
        wait_script = (REPO_ROOT / "scripts" / "wait-for-firmware-version.sh").read_text()
        assert "scripts/wait-for-firmware-version.sh" in makefile
        assert "EXPECTED_FW_VERSION" in makefile
        assert "--expected-fw" in sweep
        assert "'heap_pressure_critical'" in sweep
        assert "diagnostics.firmware_version" in wait_script
        assert "Timed out waiting for firmware_version" in wait_script

    def test_ingestor_writes_active_probe_count(self):
        body = self._read(self.INGESTOR_PATH)
        assert "active_probe_count" in body, "ingestor diagnostics INSERT must include active_probe_count"


class TestOverrideEventsWiring:
    """OBS-1e (Sprint 16): firmware override event emission end-to-end wiring."""

    TYPES_PATH = REPO_ROOT / "firmware/lib/greenhouse_types.h"
    LOGIC_PATH = REPO_ROOT / "firmware/lib/greenhouse_logic.h"
    HARDWARE_PATH = REPO_ROOT / "firmware/greenhouse/hardware.yaml"
    CONTROLS_PATH = REPO_ROOT / "firmware/greenhouse/controls.yaml"
    ENTITY_MAP_PATH = REPO_ROOT / "ingestor/entity_map.py"
    INGESTOR_PATH = REPO_ROOT / "ingestor/ingestor.py"

    @staticmethod
    def _read(path: Path) -> str:
        with open(path) as f:
            return f.read()

    def test_override_flags_struct_has_expected_fields(self):
        body = self._read(self.TYPES_PATH)
        assert "struct OverrideFlags" in body, "OverrideFlags struct missing"
        required = [
            "occupancy_blocks_moisture",
            "fog_gate_rh",
            "fog_gate_temp",
            "fog_gate_window",
            "relief_cycle_breaker",
            "seal_blocked_temp",
            "vpd_dry_override",
            "summer_vent_active",
            "vent_mist_assist",
            "fog_heat_assist",
        ]
        for field in required:
            assert field in body, f"OverrideFlags missing field: {field}"

    def test_evaluate_overrides_function_exists(self):
        body = self._read(self.LOGIC_PATH)
        assert "evaluate_overrides(" in body, "evaluate_overrides() pure function must be defined in greenhouse_logic.h"

    def test_gh_overrides_text_sensor_declared(self):
        body = self._read(self.HARDWARE_PATH)
        assert "gh_overrides" in body, "gh_overrides text_sensor missing from hardware.yaml"
        assert "Active Overrides" in body, "gh_overrides name must be 'Active Overrides'"

    def test_controls_publishes_override_state(self):
        body = self._read(self.CONTROLS_PATH)
        assert "evaluate_overrides(" in body, "controls.yaml must call evaluate_overrides() each cycle"
        assert "id(gh_overrides).publish_state(" in body, "controls.yaml must publish to gh_overrides text_sensor"

    def test_entity_map_routes_active_overrides(self):
        body = self._read(self.ENTITY_MAP_PATH)
        assert '"active_overrides"' in body, 'STATE_MAP must include "active_overrides" entity'

    def test_ingestor_writes_override_events(self):
        body = self._read(self.INGESTOR_PATH)
        assert "INSERT INTO override_events" in body, "ingestor must INSERT rows into override_events on override start"
        assert "_parse_override_set" in body, "ingestor needs a parser for the comma-separated override payload"
        assert "pending_override_events" in body, "ingestor State must track pending override events for flush"


class TestSetpointConfirmation:
    """FW-4 + FB-1 (Sprint 20): setpoint_changes.confirmed_at wiring."""

    def test_migration_084_applied(self):
        val = db_query(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='setpoint_changes' AND column_name='confirmed_at'"
        )
        assert val == "confirmed_at", "migration 084 did not apply — setpoint_changes.confirmed_at missing"

    def test_plan_journal_structured_column(self):
        val = db_query(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='plan_journal' AND column_name='hypothesis_structured'"
        )
        assert val == "hypothesis_structured", (
            "migration 084 did not apply — plan_journal.hypothesis_structured missing"
        )

    def test_confirmations_happening_in_real_time(self):
        """After ingestor restart + a full cfg_snapshot cycle (~60s), recent
        setpoint_changes rows for readbackable params should be confirmed."""
        confirmed = int(
            db_query(
                "SELECT count(*) FROM setpoint_changes "
                "WHERE confirmed_at IS NOT NULL AND ts > now() - interval '30 minutes'"
            )
            or "0"
        )
        assert confirmed > 0, (
            "No setpoint_changes rows confirmed in the last 30 min. "
            "Is the ingestor writing confirmed_at? Is setpoint_snapshot cycle running?"
        )

    def test_confirmation_monitor_task_wired(self):
        import subprocess

        # tasks.py registers setpoint_confirmation_monitor
        result = subprocess.run(
            ["grep", "-c", "setpoint_confirmation_monitor", "/srv/verdify/ingestor/tasks.py"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert int(result.stdout.strip() or "0") >= 1, "tasks.py missing setpoint_confirmation_monitor function"
        result2 = subprocess.run(
            ["grep", "-c", "setpoint_confirmation", "/srv/verdify/ingestor/ingestor.py"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert int(result2.stdout.strip() or "0") >= 1, (
            "ingestor.py must register setpoint_confirmation_monitor in TASKS list"
        )

    def test_late_phase_tunables_have_cfg_readbacks(self):
        entity_map = _repo_entity_map()
        sensors_source = (REPO_ROOT / "firmware" / "greenhouse" / "sensors.yaml").read_text()
        expected = {
            "mister_engage_delay_s",
            "mister_all_delay_s",
            "min_fog_on_s",
            "min_fog_off_s",
            "sw_dwell_gate_enabled",
            "dwell_gate_ms",
        }
        assert expected <= set(entity_map.CFG_READBACK_MAP.values())
        for param in expected:
            assert param in sensors_source

    def test_dwell_gate_direct_push_uses_number_slug(self):
        entity_map = _repo_entity_map()
        assert entity_map.PARAM_TO_ENTITY["dwell_gate_ms"] == "dwell_gate__ms_"

    def test_mister_selection_uses_zone_temp_stress(self):
        controls_source = (REPO_ROOT / "firmware" / "greenhouse" / "controls.yaml").read_text()
        assert "zone_temp_stress" in controls_source
        assert "target_temp_high_f" in controls_source
        assert "east_temp" in controls_source

    def test_confirmation_monitor_ignores_superseded_rows(self):
        body = Path("/srv/verdify/ingestor/tasks.py").read_text()
        assert "auto-resolved: superseded by newer setpoint" in body
        assert "newer.ts > COALESCE(NULLIF(al.details->>'pushed_at', '')::timestamptz, al.ts)" in body
        assert "AND NOT EXISTS (" in body
        assert "newer.ts > sc.ts" in body

    def test_confirmation_loop_backfills_new_readback_history(self):
        ingestor = (REPO_ROOT / "ingestor" / "ingestor.py").read_text()
        migration = (REPO_ROOT / "db" / "migrations" / "099-backfill-readback-confirmations.sql").read_text()
        assert "interval '7 days'" in ingestor
        assert "newer.value" in ingestor
        assert "latest_readback" in migration
        assert "confirmed_at = latest_readback.ts" in migration
        assert "newer.ts <= latest_readback.ts" in migration


class TestForecastPageGeneration:
    """Phase 7 (Sprint 20): forecast website page exists + non-empty."""

    PAGE_PATH = "/mnt/iris/verdify-vault/website/forecast/index.md"

    def test_forecast_page_exists(self):
        import os

        assert os.path.isfile(self.PAGE_PATH), (
            f"forecast page missing at {self.PAGE_PATH} — run generate-forecast-page.py"
        )

    def test_forecast_page_has_sections(self):
        with open(self.PAGE_PATH) as f:
            body = f.read()
        for section in ("# Forecast", "## Hourly — next 72 h", "## Days 4\u20137 outlook"):
            assert section in body, f"forecast page missing section: {section!r}"


class TestEntityMapCoverage:
    """TE-1 (Sprint 19): every dispatcher-emitted param must have an ESP32 route.

    Would've caught silent drops — if the dispatcher adds a tunable that has no
    PARAM_TO_ENTITY entry, the value never reaches the ESP32 and no error fires.
    """

    # Every non-switch param the dispatcher emits from static code paths. The
    # planner-driven tactical knobs come from v_active_plan and are too dynamic
    # to fully enumerate here — but ANY new static addition should extend this
    # set AND be cross-checked against PARAM_TO_ENTITY.
    STATIC_PARAMS = frozenset(
        {
            # Band-driven outer envelope
            "temp_low",
            "temp_high",
            "vpd_low",
            "vpd_high",
            # Per-zone VPD (from crop band)
            "vpd_target_south",
            "vpd_target_west",
            "vpd_target_east",
            "vpd_target_center",
            # Safety rails
            "safety_min",
            "safety_max",
            # Mister defaults
            "mister_engage_kpa",
            "mister_all_kpa",
            "mister_engage_delay_s",
            "mister_all_delay_s",
            "mister_center_penalty",
        }
    )

    def test_every_static_param_has_entity_mapping(self):
        from entity_map import PARAM_TO_ENTITY

        missing = sorted(p for p in self.STATIC_PARAMS if p not in PARAM_TO_ENTITY)
        assert not missing, (
            f"Dispatcher emits these params but PARAM_TO_ENTITY has no route: {missing}. "
            "ESP32 would silently drop them."
        )

    def test_dispatcher_still_emits_the_static_set(self):
        """If the dispatcher renames/removes a param, force re-review of this list."""
        with open("/srv/verdify/ingestor/tasks.py") as f:
            body = f.read()
        stale = sorted(p for p in self.STATIC_PARAMS if f'"{p}"' not in body)
        assert not stale, (
            f"TE-1 claims these are dispatched but they're not in tasks.py: {stale}. "
            "Either the dispatcher dropped them (silent drop!) or this test list is stale."
        )

    def test_switches_all_routed(self):
        """Every sw_* param in SETPOINT_MAP must land in SWITCH_TO_ENTITY."""
        from entity_map import SETPOINT_MAP, SWITCH_TO_ENTITY

        sw_params = {v for v in SETPOINT_MAP.values() if v.startswith("sw_")}
        missing = sorted(p for p in sw_params if p not in SWITCH_TO_ENTITY)
        assert not missing, f"sw_* params missing from SWITCH_TO_ENTITY: {missing}"

    def test_setpoint_map_has_no_duplicate_params(self):
        """Two entity object_ids mapping to same DB param = one silently overwrites the other."""
        from entity_map import SETPOINT_MAP

        values = list(SETPOINT_MAP.values())
        dupes = sorted({v for v in values if values.count(v) > 1})
        assert not dupes, f"Duplicate param names in SETPOINT_MAP (silent-overwrite risk): {dupes}"


class TestPlannerToDispatcherE2E:
    """TE-2 (Sprint 19): seed a setpoint_plan row → run dispatcher → assert a
    setpoint_changes row lands with source='plan' and the correct value.

    Exercises the full v_active_plan → setpoint_dispatcher → DB path.
    Mocks push_to_esp32 so the test doesn't drive real hardware.
    """

    TEST_PARAM = "mister_vpd_weight"
    TEST_VALUE = 0.423  # Arbitrary, unlikely to match the live planner value
    TEST_PLAN_ID = "te2-smoke-test"

    def _cleanup(self):
        for sql in (
            f"DELETE FROM setpoint_plan WHERE plan_id = '{self.TEST_PLAN_ID}'",
            # Remove any setpoint_changes row created by the test
            f"DELETE FROM setpoint_changes WHERE parameter = '{self.TEST_PARAM}' "
            f"AND abs(value - {self.TEST_VALUE}) < 1e-6 AND ts > now() - interval '5 min'",
        ):
            subprocess.run(
                [
                    "docker",
                    "exec",
                    "verdify-timescaledb",
                    "psql",
                    "-U",
                    "verdify",
                    "-d",
                    "verdify",
                    "-c",
                    sql,
                ],
                check=False,
                capture_output=True,
            )

    def test_plan_row_becomes_setpoint_change_with_plan_source(self):
        import asyncio

        import asyncpg
        import tasks as tasks_mod

        import ingestor as ing_mod
        from ingestor import State  # noqa: F401  (ensure ingestor module importable)

        # Intercept ESP32 push so the test doesn't drive real hardware
        async def _fake_push(changes):
            return len(changes)

        original_push = getattr(ing_mod, "push_to_esp32", None)
        ing_mod.push_to_esp32 = _fake_push

        # Clear the dispatcher's in-memory dedup for our test param
        tasks_mod._last_pushed.pop(self.TEST_PARAM, None)

        # Build DSN from the ingestor .env so the test uses real creds
        env = {}
        with open("/srv/verdify/ingestor/.env") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k] = v
        dsn = f"postgresql://{env['DB_USER']}:{env['DB_PASSWORD']}@localhost:{env['DB_PORT']}/{env['DB_NAME']}"

        async def run():
            pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
            try:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO setpoint_plan "
                        "(ts, parameter, value, plan_id, source, reason, is_active) "
                        "VALUES (now(), $1, $2, $3, 'iris', 'TE-2 smoke test', true)",
                        self.TEST_PARAM,
                        self.TEST_VALUE,
                        self.TEST_PLAN_ID,
                    )

                await tasks_mod.setpoint_dispatcher(pool)

                async with pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT value, source FROM setpoint_changes "
                        "WHERE parameter = $1 AND ts > now() - interval '1 minute' "
                        "ORDER BY ts DESC LIMIT 1",
                        self.TEST_PARAM,
                    )
                return row
            finally:
                await pool.close()

        try:
            row = asyncio.run(run())
            assert row is not None, f"No setpoint_changes row landed for {self.TEST_PARAM}"
            assert abs(row["value"] - self.TEST_VALUE) < 1e-6, (
                f"setpoint_changes.value mismatch: got {row['value']}, expected {self.TEST_VALUE}"
            )
            assert row["source"] == "plan", (
                f"setpoint_changes.source must be 'plan' for planner-driven param, got {row['source']!r}"
            )
        finally:
            if original_push is not None:
                ing_mod.push_to_esp32 = original_push
            self._cleanup()


class TestSetpointsFailLoud:
    """API /setpoints must fail-loud on NULL band (Tier 1 #3)."""

    API_PATH = "/srv/verdify/api/main.py"

    def test_api_raises_on_null_band(self):
        with open(self.API_PATH) as f:
            body = f.read()
        assert "'band_fn_null'" in body, (
            "/setpoints must insert alert_log row with alert_type='band_fn_null' "
            "when fn_band_setpoints returns NULL (Tier 1 #3)"
        )
        assert "status_code=503" in body, "/setpoints must raise HTTP 503 when band_row is NULL (Tier 1 #3)"

    def test_setpoints_still_200_under_normal_conditions(self):
        """Under normal operation the endpoint must not regress to 503."""
        result = subprocess.run(
            [
                "curl",
                "-sk",
                "https://127.0.0.1/setpoints",
                "-H",
                "Host: api.verdify.ai",
                "-w",
                "\n%{http_code}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        status = int(result.stdout.strip().rsplit("\n", 1)[-1])
        assert status == 200, (
            f"/setpoints returned {status} under normal operation — Tier 1 #3 should only 503 when band_row IS NULL"
        )

    def test_null_band_row_raises_503(self):
        """TE-3 (Sprint 19): direct-invoke the route handler with a mocked pool
        that returns band_row=None. Must raise HTTPException(503) and insert a
        band_fn_null alert_log row. Complements the structural test above by
        proving the runtime path actually fires."""
        import asyncio

        sys.path.insert(0, "/srv/verdify/api")
        import main as api_mod
        from fastapi import HTTPException

        alerts_inserted: list[tuple] = []

        class FakeConn:
            async def fetch(self, *_a, **_kw):
                return []

            async def fetchrow(self, sql, *_a, **_kw):
                # fn_band_setpoints + fn_zone_vpd_targets both return None
                if "fn_band_setpoints" in sql or "fn_zone_vpd_targets" in sql:
                    return None
                return None

            async def fetchval(self, *_a, **_kw):
                return None  # No existing open band_fn_null alert

            async def execute(self, sql, *args):
                if "INSERT INTO alert_log" in sql:
                    alerts_inserted.append((sql, args))

        class FakeAcquire:
            async def __aenter__(self):
                return FakeConn()

            async def __aexit__(self, *_exc):
                return False

        class FakePool:
            def acquire(self):
                return FakeAcquire()

        original_pool = api_mod.pool
        api_mod.pool = FakePool()
        try:
            raised: list[HTTPException] = []

            async def run():
                try:
                    await api_mod.get_setpoints()
                except HTTPException as e:
                    raised.append(e)

            asyncio.run(run())

            assert raised, "get_setpoints() should have raised HTTPException when band_row is NULL"
            assert raised[0].status_code == 503, (
                f"expected HTTP 503, got {raised[0].status_code} (detail={raised[0].detail!r})"
            )
            assert alerts_inserted, "/setpoints must insert a band_fn_null alert_log row on NULL band"
            assert any("'band_fn_null'" in sql for sql, _ in alerts_inserted), (
                "alert_log insert must use alert_type='band_fn_null'"
            )
        finally:
            api_mod.pool = original_pool
