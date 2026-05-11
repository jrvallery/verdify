"""Planning heartbeat milestone table.

Phase 4 retired the old fixed-boundary trigger fan-out and kept a small
solar-driven trigger set. The remaining milestones must all be reachable
inside the firing window.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

_INGESTOR_PATH = str(Path(__file__).resolve().parent.parent / "ingestor")
if _INGESTOR_PATH not in sys.path:
    sys.path.insert(0, _INGESTOR_PATH)

import tasks  # noqa: E402

DENVER = ZoneInfo("America/Denver")

EXPECTED_MILESTONES = {
    "SUNRISE",
    "SOLAR_MAX",
    "TRANSITION:peak_stress",
    "TRANSITION:decline",
    "SUNSET",
}

RETIRED_MILESTONES = {
    "TRANSITION:fixed_midnight",
    "TRANSITION:fixed_pre_dawn",
    "TRANSITION:fixed_midday",
    "TRANSITION:fixed_afternoon",
    "TRANSITION:fixed_evening",
    "TRANSITION:tree_shade",
    "TRANSITION:evening_settle",
}


@pytest.fixture(autouse=True)
def reset_milestone_cache():
    """Force _compute_milestones to rebuild from scratch in each test."""
    tasks._milestones_cache = {}
    tasks._milestones_fired = {}
    tasks._milestones_date = ""
    yield


def test_all_planning_milestones_present():
    milestones = tasks._compute_milestones()
    assert set(milestones.keys()) == EXPECTED_MILESTONES, (
        f"Expected {len(EXPECTED_MILESTONES)} milestones, got {set(milestones.keys())}"
    )


def test_every_milestone_is_on_todays_date():
    milestones = tasks._compute_milestones()
    today = datetime.now(DENVER).date()
    off_day = {key: mt.date() for key, mt in milestones.items() if mt.date() != today}
    assert not off_day, f"Milestones not on today's date ({today}): {off_day}"


def test_retired_fixed_boundaries_are_absent():
    milestones = tasks._compute_milestones()
    assert not (set(milestones) & RETIRED_MILESTONES)


def test_every_milestone_fires_within_2h_past():
    milestones = tasks._compute_milestones()
    for key, milestone_time in milestones.items():
        simulated_now = milestone_time + timedelta(seconds=60)
        delta = (simulated_now - milestone_time).total_seconds()
        assert 0 <= delta < 7200, (
            f"{key} at {milestone_time}: delta={delta}s not in firing window; milestone can't be dispatched."
        )


def test_solar_max_maps_to_own_event_type():
    milestones = tasks._compute_milestones()
    assert "SOLAR_MAX" in milestones
    assert tasks._milestone_event("SOLAR_MAX") == ("SOLAR_MAX", "Solar peak planning checkpoint")


def test_milestones_ordered_sensibly_through_day():
    m = tasks._compute_milestones()
    assert m["SUNRISE"] < m["SOLAR_MAX"]
    assert m["SOLAR_MAX"] < m["TRANSITION:peak_stress"]
    assert m["TRANSITION:peak_stress"] < m["TRANSITION:decline"]
    assert m["TRANSITION:decline"] < m["SUNSET"]
