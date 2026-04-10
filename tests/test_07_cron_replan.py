"""
Test 07: Cron Jobs & Replan Flow — Scheduled tasks and deviation-triggered replanning.
"""

import os
import subprocess

import pytest
from conftest import db_query


class TestCronJobs:
    """All expected cron jobs must be configured."""

    @pytest.fixture(scope="class")
    def crontab(self):
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
        return result.stdout

    def test_planner_cron(self, crontab):
        assert "planner.py" in crontab, "Planner cron not found"
        assert "6,12,18" in crontab, "Planner schedule not 6/12/18"

    def test_replan_trigger_cron(self, crontab):
        assert "check-replan-trigger.sh" in crontab, "Replan trigger cron not found"
        assert "*/5" in crontab, "Replan trigger not every 5 min"

    def test_daily_snapshot_cron(self, crontab):
        assert "daily-summary-snapshot" in crontab, "Daily snapshot cron not found"

    def test_backup_cron(self, crontab):
        assert "pg_dump" in crontab or "backup" in crontab.lower(), "Backup cron not found"


class TestReplanFlow:
    """Deviation detection → replan trigger → planner invocation chain."""

    def test_deviation_thresholds_configured(self):
        """Deviation thresholds must be in the DB."""
        rows = db_query("SELECT count(*) FROM forecast_deviation_thresholds WHERE enabled = true")
        assert int(rows) >= 3, f"Only {rows} active deviation thresholds"

    def test_replan_trigger_script_exists(self):
        assert os.path.isfile("/srv/verdify/scripts/check-replan-trigger.sh")

    def test_replan_trigger_references_planner(self):
        with open("/srv/verdify/scripts/check-replan-trigger.sh") as f:
            content = f.read()
        assert "planner.py" in content, "Replan trigger doesn't reference planner.py"

    def test_planner_journal_has_recent_entries(self):
        """At least one plan should have been generated today."""
        count = db_query("SELECT count(*) FROM plan_journal WHERE created_at::date = CURRENT_DATE")
        assert int(count) >= 1, "No plans generated today"

    def test_plan_has_waypoints(self):
        """Most recent plan must have waypoints in setpoint_plan."""
        plan_id = db_query(
            "SELECT plan_id FROM plan_journal WHERE plan_id NOT LIKE 'iris-reactive%' ORDER BY created_at DESC LIMIT 1"
        )
        if plan_id:
            count = db_query(f"SELECT count(*) FROM setpoint_plan WHERE plan_id = '{plan_id}' AND is_active = true")
            assert int(count) >= 24, f"Plan {plan_id} has only {count} waypoints (expected >=24)"


class TestPlannerConfig:
    """Planner configuration must be correct."""

    def test_ai_config_loads(self):
        import sys

        sys.path.insert(0, "/srv/verdify/ingestor")
        from ai_config import ai

        assert ai.model_name("planner") == "claude-opus-4-6"
        assert ai.config["models"]["planner"]["provider"] == "anthropic"

    def test_anthropic_key_exists(self):
        key_path = "/mnt/jason/agents/shared/credentials/anthropic_api_key.txt"
        assert os.path.isfile(key_path), "Anthropic API key file missing"
        with open(key_path) as f:
            key = f.read().strip()
        assert key.startswith("sk-ant-"), "Anthropic key doesn't start with sk-ant-"

    def test_planner_lessons_not_excessive(self):
        """Active lessons should be <= 25 (query caps at 10, but DB may have more)."""
        count = db_query("SELECT count(*) FROM planner_lessons WHERE is_active = true")
        assert int(count) <= 25, f"{count} active lessons (>25 = needs cleanup)"
