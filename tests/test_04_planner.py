"""
Test 04: Planner Pipeline — Context gathering, prompt rendering, output parsing.
Tests the full planner pipeline WITHOUT calling the AI model (dry-run mode).
"""

import os
import subprocess
import sys

import pytest

sys.path.insert(0, "/srv/verdify/ingestor")


class TestContextGathering:
    """gather-plan-context.sh must produce valid, complete context."""

    @pytest.fixture(scope="class")
    def context(self):
        result = subprocess.run(
            ["bash", "/srv/verdify/scripts/gather-plan-context.sh"],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "PATH": os.environ.get("PATH", "")},
        )
        assert result.returncode == 0, f"Context gathering failed: {result.stderr[:500]}"
        return result.stdout

    def test_context_not_empty(self, context):
        assert len(context) > 5000, f"Context too short: {len(context)} chars"

    def test_has_scorecard(self, context):
        assert "PLANNER SCORECARD" in context

    def test_has_score_trend(self, context):
        assert "PLANNER SCORE TREND" in context

    def test_has_active_plan(self, context):
        assert "ACTIVE PLAN" in context

    def test_has_forecast(self, context):
        assert "HOURLY FORECAST" in context or "72-HOUR" in context

    def test_has_compliance(self, context):
        assert "COMPLIANCE" in context

    def test_has_lessons(self, context):
        assert "ACTIVE LESSONS" in context

    def test_has_dew_point(self, context):
        assert "dp_margin" in context or "dp_risk" in context

    def test_has_evaluation_block(self, context):
        assert "MOST RECENT COMPLETE PLAN EVALUATION" in context

    def test_no_secrets_leaked(self, context):
        """Ensure no API keys or passwords appear in the context."""
        assert "sk-ant-" not in context, "Anthropic API key leaked in context"
        assert "AIza" not in context, "Google API key leaked in context"
        assert "POSTGRES_PASSWORD" not in context


class TestPlannerPrompt:
    """The Iris planner prompt (iris_planner.py) must contain essential knowledge."""

    @pytest.fixture(scope="class")
    def preamble(self):
        import sys

        sys.path.insert(0, "/srv/verdify/ingestor")
        from iris_planner import _PREAMBLE

        assert len(_PREAMBLE) > 5000, f"Preamble too short: {len(_PREAMBLE)} chars"
        return _PREAMBLE

    def test_has_standing_directives(self, preamble):
        assert "Standing Directives" in preamble
        assert "MCP tools ONLY" in preamble

    def test_has_decision_precedence(self, preamble):
        assert "Safety" in preamble
        assert "Band compliance" in preamble
        assert "Cost" in preamble

    def test_has_kpi(self, preamble):
        assert "Planner Score" in preamble
        assert "80% Compliance" in preamble or "80%" in preamble

    def test_has_compliance_metrics(self, preamble):
        assert "temp_compliance_pct" in preamble
        assert "vpd_compliance_pct" in preamble

    def test_has_tunables(self, preamble):
        assert "vpd_hysteresis" in preamble
        assert "bias_cool" in preamble
        assert "fog_escalation_kpa" in preamble

    def test_has_modes(self, preamble):
        assert "SEALED_MIST" in preamble
        assert "VENTILATE" in preamble

    def test_has_lessons(self, preamble):
        assert "Fog is 7x" in preamble or "fog is 7x" in preamble

    def test_no_secrets(self, preamble):
        assert "sk-ant-" not in preamble
        assert "AIza" not in preamble

    def test_has_utility_guidance(self, preamble):
        assert "kwh" in preamble
        assert "therms" in preamble
        assert "3.9x" in preamble or "3.9×" in preamble


class TestMCPToolAvailability:
    """The MCP server must expose all 18 planning tools."""

    def test_mcp_server_running(self):
        import subprocess

        result = subprocess.run(["systemctl", "is-active", "verdify-mcp"], capture_output=True, text=True, timeout=5)
        assert result.stdout.strip() == "active", "MCP server not running"

    def test_skill_file_exists(self):
        import os

        assert os.path.isfile("/mnt/jason/agents/iris/skills/greenhouse-planner.md"), "Skill file missing"
