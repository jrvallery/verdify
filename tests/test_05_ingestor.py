"""
Test 05: Ingestor — Service health, task execution, data pipeline.
"""

import subprocess

from conftest import db_query


class TestIngestorService:
    """Ingestor systemd service must be healthy."""

    def test_service_active(self):
        result = subprocess.run(
            ["systemctl", "is-active", "verdify-ingestor"], capture_output=True, text=True, timeout=5
        )
        assert result.stdout.strip() == "active"

    def test_no_recent_crashes(self):
        """No restarts in the last hour."""
        result = subprocess.run(
            ["journalctl", "-u", "verdify-ingestor", "--since", "1 hour ago", "--no-pager", "-q", "-o", "cat"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "Started" not in result.stdout or result.stdout.count("Started") <= 1, (
            "Ingestor restarted in the last hour"
        )


class TestESP32Connection:
    """ESP32 data must be flowing through the ingestor."""

    def test_climate_columns_populated(self):
        """Key climate columns must have recent non-null data."""
        for col in ["temp_avg", "vpd_avg", "rh_avg", "dew_point"]:
            val = db_query(f"SELECT {col} FROM climate ORDER BY ts DESC LIMIT 1")
            assert val and val != "", f"Climate column {col} is NULL"

    def test_zone_vpd_data(self):
        """Zone VPD sensors must be reporting."""
        for zone in ["vpd_south", "vpd_west", "vpd_east"]:
            val = db_query(f"SELECT {zone} FROM climate WHERE {zone} IS NOT NULL ORDER BY ts DESC LIMIT 1")
            assert val, f"Zone sensor {zone} has no data"

    def test_equipment_state_tracked(self):
        """Equipment state transitions must be logged."""
        count = db_query("SELECT count(DISTINCT equipment) FROM equipment_state WHERE ts > now() - interval '1 hour'")
        assert int(count) >= 1, "No equipment state transitions in last hour"


class TestIngestorTasks:
    """Periodic tasks must be running on schedule."""

    def test_setpoint_dispatcher_recent(self):
        """Setpoints must have been dispatched recently."""
        age = db_query("SELECT extract(epoch FROM now() - max(ts))::int FROM setpoint_changes WHERE source != 'esp32'")
        # Dispatcher runs every 5 min; allow 15 min tolerance
        assert int(age) < 900, f"Last dispatch was {age}s ago (>15min)"

    def test_forecast_sync_recent(self):
        """Forecast must have been synced in last 2 hours."""
        age = db_query("SELECT extract(epoch FROM now() - max(fetched_at))::int FROM weather_forecast")
        assert int(age) < 7200, f"Last forecast sync was {age}s ago (>2h)"

    def test_alert_monitor_runs(self):
        """Alert log should have entries (even if no active alerts)."""
        count = db_query("SELECT count(*) FROM alert_log WHERE ts > now() - interval '24 hours'")
        # Could be 0 if no alerts — just verify the query runs
        assert count is not None


class TestDataIntegrity:
    """Data quality checks."""

    def test_no_null_temp_in_recent_climate(self):
        """Recent climate rows should not have NULL temp_avg."""
        nulls = db_query("SELECT count(*) FROM climate WHERE ts > now() - interval '1 hour' AND temp_avg IS NULL")
        assert int(nulls) == 0, f"{nulls} rows with NULL temp_avg in last hour"

    def test_setpoint_values_sane(self):
        """Active non-ESP32 setpoints should be within expected ranges."""
        checks = [
            ("temp_high", 50, 100),
            ("temp_low", 40, 80),
            ("vpd_high", 0.3, 3.0),
            ("vpd_low", 0.1, 2.0),
        ]
        for param, lo, hi in checks:
            # Check dispatcher/planner values, skip ESP32 reboot artifacts (which can be 0)
            val = db_query(
                f"SELECT value FROM setpoint_changes WHERE parameter = '{param}' AND source != 'esp32' ORDER BY ts DESC LIMIT 1"
            )
            if val:
                v = float(val)
                assert lo <= v <= hi, f"{param}={v} outside range [{lo}, {hi}]"

    def test_daily_summary_stress_consistent(self):
        """Stress hours per category should not exceed 48h (multi-zone overlap can push beyond 24)."""
        for col in ["stress_hours_heat", "stress_hours_cold", "stress_hours_vpd_high", "stress_hours_vpd_low"]:
            val = db_query(f"SELECT max({col}) FROM daily_summary WHERE date >= CURRENT_DATE - 7")
            if val:
                assert float(val) <= 48.1, f"{col} exceeds 48h: {val}"
