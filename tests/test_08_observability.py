"""
Test 08: Tier 1 observability — override_events, setpoint_clamps, /setpoints fail-loud.

Smoke tests covering the 96h-review Tier 1 changes (migration 080 + dispatcher
clamp logging + ESP32 push retry + /setpoints 503 on NULL band). Pre-migration,
every query in TestSchema below fails — that's the "would fail without the
change" gate per the fleet DoD.
"""

import subprocess

from conftest import db_query


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

    def test_dispatcher_escalates_push_failure(self):
        body = self._read()
        assert "'esp32_push_failed'" in body, (
            "Exhausted ESP32 push retries must INSERT alert_log alert_type='esp32_push_failed' (Tier 1 #4)"
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

    def test_ingestor_writes_active_probe_count(self):
        body = self._read(self.INGESTOR_PATH)
        assert "active_probe_count" in body, "ingestor diagnostics INSERT must include active_probe_count"


class TestOverrideEventsWiring:
    """OBS-1e (Sprint 16): firmware override event emission end-to-end wiring."""

    TYPES_PATH = "/srv/verdify/firmware/lib/greenhouse_types.h"
    LOGIC_PATH = "/srv/verdify/firmware/lib/greenhouse_logic.h"
    HARDWARE_PATH = "/srv/verdify/firmware/greenhouse/hardware.yaml"
    CONTROLS_PATH = "/srv/verdify/firmware/greenhouse/controls.yaml"
    ENTITY_MAP_PATH = "/srv/verdify/ingestor/entity_map.py"
    INGESTOR_PATH = "/srv/verdify/ingestor/ingestor.py"

    @staticmethod
    def _read(path: str) -> str:
        with open(path) as f:
            return f.read()

    def test_override_flags_struct_has_seven_fields(self):
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
