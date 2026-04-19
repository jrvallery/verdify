"""MCP read-tool response schema tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from verdify_schemas.mcp_responses import (
    ClimateSnapshot,
    EquipmentStateRow,
    ForecastSummaryRow,
    HistoryRow,
    LessonSummary,
    PlanRunResponse,
    PlanStatusJournal,
    PlanStatusResponse,
    PlanStatusWaypoint,
    ScorecardResponse,
    SetpointSummary,
    ToolError,
)


class TestClimateSnapshot:
    def test_valid(self):
        s = ClimateSnapshot(temp_f=72.5, vpd_kpa=0.8, mode="VENTILATE", age_seconds=12)
        assert s.mode == "VENTILATE"

    def test_minimal(self):
        s = ClimateSnapshot()
        assert s.mode is None


class TestScorecard:
    def test_open_dict(self):
        # Permissive — variable metric set per day
        s = ScorecardResponse.model_validate({"planner_score": 72, "compliance_pct": 88, "anything_new": 1})
        assert s.model_dump()["planner_score"] == 72


class TestEquipmentStateRow:
    def test_valid(self):
        r = EquipmentStateRow(equipment="fan1", state=True, since="14:32:01")
        assert r.state is True

    def test_rejects_missing_state(self):
        with pytest.raises(ValidationError):
            EquipmentStateRow(equipment="fan1", since="14:32:01")


class TestForecastSummaryRow:
    def test_valid(self):
        f = ForecastSummaryRow(time="Sun 14:00", temp=82, rh=12, vpd=2.3, cloud=10, solar=900)
        assert f.solar == 900


class TestHistoryRow:
    def test_open_extra(self):
        h = HistoryRow(time="2026-04-19T01:00:00+00:00", temp_f=72, rh_pct=55)
        assert h.model_dump().get("temp_f") == 72


class TestSetpointSummary:
    def test_valid(self):
        s = SetpointSummary(parameter="temp_low", value=58.0, source="plan", updated="06:18")
        assert s.source == "plan"


class TestPlanStatus:
    def test_with_plan(self):
        j = PlanStatusJournal(
            plan_id="iris-20260418-0618",
            created="04-18 06:18",
            hypothesis="x",
        )
        wp = PlanStatusWaypoint(time="Sun 14:00", params=10)
        r = PlanStatusResponse(plan=j, future_waypoints=[wp])
        assert r.plan.plan_id.startswith("iris-")
        assert r.future_waypoints[0].params == 10

    def test_no_active_plan(self):
        r = PlanStatusResponse()
        assert r.plan is None
        assert r.future_waypoints == []

    def test_rejects_negative_params(self):
        with pytest.raises(ValidationError):
            PlanStatusWaypoint(time="x", params=-1)


class TestLessonSummary:
    def test_valid(self):
        ls = LessonSummary(
            category="misting",
            condition="dry day <20% RH",
            lesson="engage 1.3, gap 30s",
            confidence="medium",
            times_validated=4,
        )
        assert ls.confidence == "medium"

    def test_rejects_bad_confidence(self):
        with pytest.raises(ValidationError):
            LessonSummary(
                category="x",
                condition="x",
                lesson="x",
                confidence="maybe",
                times_validated=1,
            )


class TestPlanRunResponse:
    def test_ok(self):
        r = PlanRunResponse(ok=True, note="sent")
        assert r.ok is True

    def test_error(self):
        r = PlanRunResponse(ok=False, error="OpenClaw unreachable")
        assert r.error.startswith("OpenClaw")


class TestToolError:
    def test_with_details(self):
        e = ToolError(error="validation failed", details={"field": "x"})
        assert e.details["field"] == "x"
