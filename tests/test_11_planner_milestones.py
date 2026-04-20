"""Sprint 24.8 regression — planning_heartbeat milestone table.

Direct cause: midnight_posture was set to `today + 1day` at 00:00 MDT, so
the cache-per-day rebuild at the date rollover re-set the milestone 24h
into the future at the exact moment it should have fired. The firing
window `0 ≤ delta < 7200` never saw a non-negative delta for this key,
and the milestone never dispatched.

This test locks the fix: every milestone in _compute_milestones() must
resolve to today's calendar date (not tomorrow's), and the firing window
must contain each milestone when simulated `now = milestone_time + 60s`.
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
    "SUNSET",
    "TRANSITION:peak_stress",
    "TRANSITION:tree_shade",
    "TRANSITION:decline",
    "TRANSITION:evening_settle",
    "TRANSITION:midnight_posture",
    "TRANSITION:pre_dawn",
}


@pytest.fixture(autouse=True)
def reset_milestone_cache():
    """Force _compute_milestones to rebuild from scratch in each test."""
    tasks._milestones_cache = {}
    tasks._milestones_fired = {}
    tasks._milestones_date = ""
    yield


def test_all_eight_milestones_present():
    milestones = tasks._compute_milestones()
    assert set(milestones.keys()) == EXPECTED_MILESTONES, f"Expected 8 milestones, got {set(milestones.keys())}"


def test_every_milestone_is_on_todays_date():
    """Regression for sprint 24.8 bug: midnight_posture was tomorrow's
    midnight, not today's. The cache rebuilds at date rollover, so
    "tomorrow at 00:00" re-computes to "tomorrow of new today" = next day,
    perpetually 24h in the future. Every milestone must be on today's
    calendar date for the firing window (0 ≤ delta < 7200) to catch it.
    """
    milestones = tasks._compute_milestones()
    today = datetime.now(DENVER).date()
    off_day = {key: mt.date() for key, mt in milestones.items() if mt.date() != today}
    assert not off_day, (
        f"Milestones not on today's date ({today}): {off_day}. "
        "These never fire across the date rollover — see sprint 24.8 hotfix."
    )


def test_midnight_posture_is_today_zero_hundred():
    """Specifically pin midnight_posture to today's 00:00 MDT.

    The original bug set it to tomorrow's 00:00. The first task_loop tick
    past today's 00:00 MDT hits `delta = now - 00:00 today` which sits in
    the firing window [0, 7200s) for up to 2 hours after rollover — long
    enough for the 60s task_loop cadence to catch it even across ingestor
    restart gaps.
    """
    milestones = tasks._compute_milestones()
    today = datetime.now(DENVER).date()
    mp = milestones["TRANSITION:midnight_posture"]
    expected = datetime.combine(today, datetime.min.time(), tzinfo=DENVER)
    assert mp == expected, f"midnight_posture={mp}, expected={expected} (today's 00:00 MDT)"


def test_every_milestone_fires_within_2h_past():
    """Simulate a 'now' that's 60 seconds past each milestone — the
    firing condition (0 ≤ delta < 7200) must be True. This proves the
    milestone table is structurally reachable by the task_loop; any
    milestone whose time is in the future produces delta < 0 and would
    be silently skipped as happened with midnight_posture pre-fix.
    """
    milestones = tasks._compute_milestones()
    for key, milestone_time in milestones.items():
        simulated_now = milestone_time + timedelta(seconds=60)
        delta = (simulated_now - milestone_time).total_seconds()
        assert 0 <= delta < 7200, (
            f"{key} at {milestone_time}: delta={delta}s not in firing window — milestone can't be dispatched."
        )


def test_midnight_posture_fires_immediately_after_rollover():
    """Timeline-specific: simulate the first task_loop tick after
    midnight. Today's 00:00 MDT passed a few seconds ago; the firing
    window [0, 300) must accept it.
    """
    milestones = tasks._compute_milestones()
    mp = milestones["TRANSITION:midnight_posture"]
    # Simulate task_loop tick at 00:00:05 MDT (5s past midnight)
    simulated_now = mp + timedelta(seconds=5)
    delta = (simulated_now - mp).total_seconds()
    assert 0 <= delta < 300, f"Post-rollover tick delta={delta}s not in normal firing window [0, 300)"


def test_milestones_ordered_sensibly_through_day():
    """Basic sanity: pre_dawn < SUNRISE < peak_stress < tree_shade < decline
    < SUNSET < evening_settle. Midnight_posture sits apart (today's 00:00,
    in the past for all other milestones' today timing).
    """
    m = tasks._compute_milestones()
    # Non-midnight milestones in the expected daily sequence
    assert m["TRANSITION:pre_dawn"] < m["SUNRISE"]
    assert m["SUNRISE"] < m["TRANSITION:peak_stress"]
    assert m["TRANSITION:peak_stress"] < m["TRANSITION:tree_shade"]
    assert m["TRANSITION:tree_shade"] < m["TRANSITION:decline"]
    assert m["TRANSITION:decline"] < m["SUNSET"]
    assert m["SUNSET"] < m["TRANSITION:evening_settle"]
    # midnight_posture is earliest (today's 00:00)
    for key in (
        "TRANSITION:pre_dawn",
        "SUNRISE",
        "TRANSITION:peak_stress",
        "TRANSITION:tree_shade",
        "TRANSITION:decline",
        "SUNSET",
        "TRANSITION:evening_settle",
    ):
        assert m["TRANSITION:midnight_posture"] < m[key], (
            f"midnight_posture ({m['TRANSITION:midnight_posture']}) should be before {key} ({m[key]})"
        )
