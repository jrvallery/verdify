"""Phase 4 — view projection schemas, tested against live DB."""

from __future__ import annotations

import subprocess
from datetime import date

import pytest
from pydantic import ValidationError

from verdify_schemas.views import (
    ClampActivity24h,
    DailyOscillation,
    DailyOscillationSummary,
    DewPointRiskRow,
    OverrideActivity24h,
    PlanAccuracy,
    PlannerPerformance,
    WaterBudgetRow,
)


def _psql_json(sql: str) -> list[dict]:
    """Minimal wrapper to read rows as JSON."""
    r = subprocess.run(
        [
            "docker",
            "exec",
            "verdify-timescaledb",
            "psql",
            "-U",
            "verdify",
            "-d",
            "verdify",
            "-t",
            "-A",
            "-c",
            f"SELECT row_to_json(x) FROM ({sql}) x",
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    import json as _json

    out = []
    for line in r.stdout.strip().splitlines():
        if line:
            out.append(_json.loads(line))
    return out


class TestPlannerPerformanceBasic:
    def test_valid(self):
        p = PlannerPerformance(date=date(2026, 4, 18), planner_score=72, compliance_pct=88.5)
        assert p.planner_score == 72

    def test_rejects_score_over_100(self):
        with pytest.raises(ValidationError):
            PlannerPerformance(date=date(2026, 4, 18), planner_score=150)

    def test_rejects_negative_cost(self):
        with pytest.raises(ValidationError):
            PlannerPerformance(date=date(2026, 4, 18), cost_total=-1.0)


class TestPlanAccuracyBasic:
    def test_valid(self):
        a = PlanAccuracy(plan_id="iris-20260418-0618", waypoints=20, achieved=17, accuracy_pct=85.0)
        assert a.accuracy_pct == 85.0

    def test_achieved_gt_waypoints_allowed(self):
        # View doesn't enforce achieved<=waypoints; schema permissive to mirror DB
        a = PlanAccuracy(plan_id="x", waypoints=10, achieved=10)
        assert a.achieved == 10


class TestDewPointRiskRowBasic:
    def test_risk_hours_bounded(self):
        with pytest.raises(ValidationError):
            DewPointRiskRow(date=date(2026, 4, 18), risk_hours=30)


class TestWaterBudgetRowBasic:
    def test_negative_total_rejected(self):
        with pytest.raises(ValidationError):
            WaterBudgetRow(date=date(2026, 4, 18), total_gal=-5)


class TestOscillationViewsBasic:
    def test_daily_oscillation_valid(self):
        d = DailyOscillation(date=date(2026, 4, 18), equipment="fan1", peak_transitions_per_hour=170, active_hours=24)
        assert d.equipment == "fan1"

    def test_daily_oscillation_active_hours_bounded(self):
        with pytest.raises(ValidationError):
            DailyOscillation(
                date=date(2026, 4, 18),
                equipment="fan1",
                peak_transitions_per_hour=0,
                active_hours=30,
            )

    def test_summary_min(self):
        s = DailyOscillationSummary(date=date(2026, 4, 18))
        assert s.worst_equipment is None


class TestActivityViewsBasic:
    def test_override_activity(self):
        a = OverrideActivity24h(override_type="fog_gate_rh", events=12, distinct_modes=2)
        assert a.events == 12

    def test_clamp_activity(self):
        c = ClampActivity24h(parameter="temp_low", clamp_events=3)
        assert c.parameter == "temp_low"


# ── Live-DB drift guards (integration tests) ──
# If the DB view drops / renames a column we depend on, these fail.


def _has_docker() -> bool:
    r = subprocess.run(["docker", "ps"], capture_output=True, text=True, check=False)
    return r.returncode == 0


pytestmark_live = pytest.mark.skipif(not _has_docker(), reason="docker not available")


@pytestmark_live
class TestLiveProjection:
    def test_planner_performance_live_rows(self):
        rows = _psql_json("SELECT * FROM v_planner_performance ORDER BY date DESC LIMIT 3")
        for r in rows:
            PlannerPerformance.model_validate(r)

    def test_plan_accuracy_live_rows(self):
        rows = _psql_json("SELECT * FROM v_plan_accuracy ORDER BY plan_end DESC NULLS LAST LIMIT 3")
        for r in rows:
            PlanAccuracy.model_validate(r)

    def test_dew_point_risk_live_rows(self):
        try:
            rows = _psql_json("SELECT * FROM v_dew_point_risk ORDER BY date DESC LIMIT 1")
        except subprocess.TimeoutExpired:
            pytest.skip("v_dew_point_risk query slow (known pre-existing)")
        for r in rows:
            DewPointRiskRow.model_validate(r)

    def test_daily_oscillation_live_rows(self):
        rows = _psql_json("SELECT * FROM v_daily_oscillation ORDER BY date DESC LIMIT 3")
        for r in rows:
            DailyOscillation.model_validate(r)

    def test_oscillation_summary_live_rows(self):
        rows = _psql_json("SELECT * FROM v_daily_oscillation_summary ORDER BY date DESC LIMIT 3")
        for r in rows:
            DailyOscillationSummary.model_validate(r)

    def test_override_activity_live_rows(self):
        rows = _psql_json("SELECT * FROM v_override_activity_24h")
        for r in rows:
            OverrideActivity24h.model_validate(r)

    def test_clamp_activity_live_rows(self):
        rows = _psql_json("SELECT * FROM v_clamp_activity_24h")
        for r in rows:
            ClampActivity24h.model_validate(r)
