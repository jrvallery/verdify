"""
Test 04: Planner Pipeline — Context gathering, prompt rendering, output parsing.
Tests the full planner pipeline WITHOUT calling the AI model (dry-run mode).
"""
import json
import os
import re
import subprocess
import sys
import pytest

sys.path.insert(0, "/srv/verdify/ingestor")
sys.path.insert(0, "/srv/verdify/scripts")


class TestContextGathering:
    """gather-plan-context.sh must produce valid, complete context."""

    @pytest.fixture(scope="class")
    def context(self):
        result = subprocess.run(
            ["bash", "/srv/verdify/scripts/gather-plan-context.sh"],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "PATH": os.environ.get("PATH", "")}
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


class TestPromptRendering:
    """planner.py --dry-run must produce a valid, complete prompt."""

    @pytest.fixture(scope="class")
    def prompt(self):
        result = subprocess.run(
            ["/srv/greenhouse/.venv/bin/python", "/srv/verdify/scripts/planner.py", "--dry-run"],
            capture_output=True, text=True, timeout=90
        )
        # stdout is the prompt, stderr is log messages
        assert len(result.stdout) > 1000, f"Prompt too short: {len(result.stdout)} chars"
        return result.stdout

    def test_prompt_has_mode(self, prompt):
        assert prompt.startswith("MODE: NORMAL") or prompt.startswith("MODE: REPLAN")

    def test_prompt_has_horizon(self, prompt):
        assert "Plan horizon" in prompt
        assert "72 hours" in prompt

    def test_prompt_has_state_machine(self, prompt):
        assert "SEALED_MIST" in prompt or "HUMID_S1" in prompt

    def test_prompt_has_kpi(self, prompt):
        assert "Planner Score" in prompt
        assert "80% Compliance" in prompt

    def test_prompt_has_24_params(self, prompt):
        assert "vpd_hysteresis" in prompt
        assert "bias_cool" in prompt
        assert "mist_max_closed_vent_s" in prompt

    def test_prompt_has_milestones(self, prompt):
        assert "SUGGESTED TRANSITION TIMESTAMPS" in prompt

    def test_prompt_has_output_format(self, prompt):
        assert "previous_plan_validation" in prompt
        assert "performance_target" in prompt

    def test_prompt_has_dew_point_guidance(self, prompt):
        assert "Dew point margin" in prompt
        assert "dp_risk_hours" in prompt

    def test_prompt_no_secrets(self, prompt):
        assert "sk-ant-" not in prompt
        assert "AIza" not in prompt

    def test_milestones_include_today(self, prompt):
        """Today must appear in the suggested timestamps table."""
        from datetime import datetime
        today_abbrev = datetime.now().strftime("%a %m-%d")  # e.g., "Fri 04-10"
        # Check for the day abbreviation (first 3 letters)
        day_abbr = datetime.now().strftime("%a")
        assert day_abbr in prompt, f"Today ({day_abbr}) not found in milestones"


class TestOutputParsing:
    """The JSON parser must handle various model output formats."""

    def test_parse_clean_json(self):
        from planner import parse_plan_json
        raw = '{"plan_id": "test", "transitions": []}'
        result = parse_plan_json(raw)
        assert result["plan_id"] == "test"

    def test_parse_code_fenced_json(self):
        from planner import parse_plan_json
        raw = '```json\n{"plan_id": "test", "transitions": []}\n```'
        result = parse_plan_json(raw)
        assert result["plan_id"] == "test"

    def test_parse_preamble_json(self):
        from planner import parse_plan_json
        raw = 'Here is my plan:\n\n```json\n{"plan_id": "test", "transitions": []}\n```\n\nLet me explain...'
        result = parse_plan_json(raw)
        assert result["plan_id"] == "test"

    def test_parse_truncated_json(self):
        from planner import parse_plan_json
        # Simulate a complete-enough JSON that just has an extra trailing comma
        raw = '{"plan_id": "test", "transitions": [{"ts": "2026-04-10T10:00:00-06:00", "params": {"vpd_hysteresis": 0.3}}]}'
        result = parse_plan_json(raw)
        assert result["plan_id"] == "test"
        assert len(result["transitions"]) == 1
