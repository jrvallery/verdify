"""MCP read-tool response envelopes.

The 8 read-only MCP tools (climate, scorecard, equipment_state, forecast,
history, get_setpoints, plan_status, lessons) all return JSON strings. Until
Sprint 23 these were free-form dicts — Iris received whatever the SQL
happened to project. Now each tool builds its response through the matching
model below + `.model_dump_json()`, so a future SQL refactor that drops a
column fails at the boundary instead of silently returning a smaller shape.

Skipped intentionally:
- `query` — generic SELECT escape hatch; cannot be typed.
- `set_*` and `*_evaluate` write tools — already typed via Plan / PlanEvaluation.
- `plan_run` — fire-and-forget trigger, returns {"ok", "note"}; trivial.
- `alerts list` — already structured; can add later if useful.
"""

from __future__ import annotations

from datetime import date as DateType
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from .lessons import LessonConfidence


class ClimateSnapshot(BaseModel):
    """`climate()` tool response — one current reading + greenhouse mode."""

    model_config = ConfigDict(extra="ignore")

    temp_f: Decimal | None = None
    vpd_kpa: Decimal | None = None
    rh_pct: Decimal | None = None
    dew_point_f: Decimal | None = None
    dp_margin_f: Decimal | None = None
    vpd_south: Decimal | None = None
    vpd_west: Decimal | None = None
    vpd_east: Decimal | None = None
    outdoor_temp: Decimal | None = None
    outdoor_rh: Decimal | None = None
    lux: Decimal | None = None
    solar_w: Decimal | None = None
    age_seconds: int | None = None
    mode: str | None = None


class ScorecardResponse(BaseModel):
    """`scorecard(target_date)` tool response — flat metric→value dict.

    Permissive (extra='allow') because fn_planner_scorecard returns a
    variable set of metrics depending on data availability.
    """

    model_config = ConfigDict(extra="allow")


class EquipmentStateRow(BaseModel):
    """One row of the `equipment_state()` tool response."""

    model_config = ConfigDict(extra="ignore")

    equipment: str
    state: bool
    since: str  # HH:MM:SS — Denver-local time string


class ForecastSummaryRow(BaseModel):
    """One hour of the `forecast(hours)` tool response."""

    model_config = ConfigDict(extra="ignore")

    time: str  # "Sun 14:00" Denver-local
    temp: Decimal | None = None
    rh: Decimal | None = None
    vpd: Decimal | None = None
    cloud: Decimal | None = None
    solar: Decimal | None = None


class HistoryRow(BaseModel):
    """One bucket of the `history(metric, hours, resolution_min)` tool response.

    Permissive — different metrics project different columns.
    """

    model_config = ConfigDict(extra="allow")

    time: AwareDatetime | str


class SetpointSummary(BaseModel):
    """One row of the `get_setpoints()` tool response."""

    model_config = ConfigDict(extra="ignore")

    parameter: str
    value: Decimal
    source: str
    updated: str  # HH:MM Denver-local


class PlanStatusJournal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    plan_id: str
    created: str
    hypothesis: str | None = None
    experiment: str | None = None
    expected_outcome: str | None = None


class PlanStatusWaypoint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    time: str
    params: int = Field(..., ge=0)


class PlanStatusResponse(BaseModel):
    """`plan_status()` tool response — current plan + future waypoints."""

    model_config = ConfigDict(extra="ignore")

    plan: PlanStatusJournal | None = None
    future_waypoints: list[PlanStatusWaypoint] = Field(default_factory=list)


class LessonSummary(BaseModel):
    """One row of the `lessons()` tool response."""

    model_config = ConfigDict(extra="ignore")

    category: str
    condition: str
    lesson: str
    confidence: LessonConfidence
    times_validated: int = Field(..., ge=0)


# Generic envelopes for tool errors / fire-and-forget acks.
ToolStatus = Literal["ok", "error"]


class ToolError(BaseModel):
    model_config = ConfigDict(extra="ignore")

    error: str
    details: list | dict | None = None


class PlanRunResponse(BaseModel):
    """`plan_run(mode)` tool response — fire-and-forget trigger."""

    model_config = ConfigDict(extra="ignore")

    ok: bool
    note: str | None = None
    error: str | None = None


# ── Date stub used only to keep the import block tidy ─
_unused_date_alias: type = DateType  # noqa: F841
