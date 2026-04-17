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
