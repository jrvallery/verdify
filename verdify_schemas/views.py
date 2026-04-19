"""Read-only view projection schemas.

Each model mirrors exactly what the underlying VIEW emits. Consumers
(website renderers, MCP scorecard tool, backfill script) validate through
these so a view refactor that drops a column fails loud at the caller
instead of appearing as None or KeyError in the website HTML.

Views covered:
- v_planner_performance       → PlannerPerformance   (daily KPI scorecard)
- v_plan_accuracy             → PlanAccuracy         (per-plan compliance rollup)
- v_dew_point_risk            → DewPointRiskRow
- v_water_budget              → WaterBudgetRow
- v_daily_oscillation         → DailyOscillation     (per-equipment peak hourly
                                                      transition count)
- v_daily_oscillation_summary → DailyOscillationSummary (single worst hour/day)
- v_override_activity_24h     → OverrideActivity24h
- v_clamp_activity_24h        → ClampActivity24h
"""

from __future__ import annotations

from datetime import date as DateType
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class PlannerPerformance(BaseModel):
    """v_planner_performance row — the Planner Score for a given date.

    planner_score = 80% compliance + 20% cost efficiency (0–100). Target: >70.
    """

    model_config = ConfigDict(extra="ignore")

    date: DateType
    heat_stress_h: float | None = Field(default=None, ge=0, le=24)
    cold_stress_h: float | None = Field(default=None, ge=0, le=24)
    vpd_high_stress_h: float | None = Field(default=None, ge=0, le=24)
    vpd_low_stress_h: float | None = Field(default=None, ge=0, le=24)
    total_stress_h: float | None = Field(default=None, ge=0, le=96)  # 4 axes, max 4×24
    compliance_pct: Decimal | None = Field(default=None, ge=0, le=100)
    temp_compliance_pct: Decimal | None = Field(default=None, ge=0, le=100)
    vpd_compliance_pct: Decimal | None = Field(default=None, ge=0, le=100)
    cost_total: float | None = Field(default=None, ge=0)
    cost_electric: float | None = Field(default=None, ge=0)
    cost_gas: float | None = Field(default=None, ge=0)
    cost_water: float | None = Field(default=None, ge=0)
    cost_per_stress_hour: Decimal | None = None
    planner_score: Decimal | None = Field(default=None, ge=0, le=100)


class PlanAccuracy(BaseModel):
    """v_plan_accuracy row — retrospective compliance rollup for one plan."""

    model_config = ConfigDict(extra="ignore")

    plan_id: str
    waypoints: int = Field(..., ge=0)
    achieved: int = Field(..., ge=0)
    accuracy_pct: Decimal | None = Field(default=None, ge=0, le=100)
    mean_abs_error: Decimal | None = Field(default=None, ge=0)
    worst_ceiling_overshoot: Decimal | None = None
    worst_floor_undershoot: Decimal | None = None
    plan_start: AwareDatetime | None = None
    plan_end: AwareDatetime | None = None


class DewPointRiskRow(BaseModel):
    """v_dew_point_risk row — per-day condensation risk.

    <5°F margin = risk; <3°F margin = critical.
    """

    model_config = ConfigDict(extra="ignore")

    date: DateType
    min_margin_f: Decimal | None = None
    avg_margin_f: Decimal | None = None
    risk_hours: Decimal | None = Field(default=None, ge=0, le=24)
    critical_hours: Decimal | None = Field(default=None, ge=0, le=24)


class WaterBudgetRow(BaseModel):
    """v_water_budget row — per-day water decomposition."""

    model_config = ConfigDict(extra="ignore")

    date: DateType
    total_gal: float | None = Field(default=None, ge=0)
    mister_gal: float | None = Field(default=None, ge=0)
    drip_gal: float | None = Field(default=None, ge=0)
    unaccounted_gal: float | None = None
    gal_per_vpd_stress_hour: Decimal | None = None


class DailyOscillation(BaseModel):
    """v_daily_oscillation row — per-equipment peak hourly transitions.

    FW-2 (Sprint 18). Target post-DI-1: peak_transitions_per_hour << 170.
    """

    model_config = ConfigDict(extra="ignore")

    date: DateType
    equipment: str
    peak_transitions_per_hour: int = Field(..., ge=0)
    peak_hour: AwareDatetime | None = None
    avg_transitions_per_hour: Decimal | None = Field(default=None, ge=0)
    active_hours: int = Field(..., ge=0, le=24)


class DailyOscillationSummary(BaseModel):
    """v_daily_oscillation_summary — one row per day, worst-case snapshot."""

    model_config = ConfigDict(extra="ignore")

    date: DateType
    total_peak_per_hour: Decimal | None = None
    worst_equipment_peak: int | None = Field(default=None, ge=0)
    worst_equipment: str | None = None
    worst_hour: AwareDatetime | None = None
    avg_across_equipment: Decimal | None = None


class OverrideActivity24h(BaseModel):
    """v_override_activity_24h row — one row per override_type."""

    model_config = ConfigDict(extra="ignore")

    override_type: str
    events: int = Field(..., ge=0)
    first_seen: AwareDatetime | None = None
    last_seen: AwareDatetime | None = None
    distinct_modes: int = Field(..., ge=0)


class ClampActivity24h(BaseModel):
    """v_clamp_activity_24h row — one row per clamped parameter."""

    model_config = ConfigDict(extra="ignore")

    parameter: str
    clamp_events: int = Field(..., ge=0)
    avg_clamp_delta: Decimal | None = None
    max_clamp_delta: Decimal | None = None
    first_seen: AwareDatetime | None = None
    last_seen: AwareDatetime | None = None


# ── Sprint 23: crop history views ──────────────────────────────────────


class PositionCurrentEntry(BaseModel):
    """v_position_current row — one per active position + optional crop.

    Empty slots show `is_occupied=False` with all crop_* fields NULL.
    """

    model_config = ConfigDict(extra="ignore")

    position_id: int
    greenhouse_id: str
    position_label: str
    shelf_slug: str
    shelf_kind: str
    zone_id: int
    zone_slug: str
    zone_name: str
    crop_id: int | None = None
    crop_name: str | None = None
    crop_variety: str | None = None
    crop_stage: str | None = None
    crop_planted_date: DateType | None = None
    crop_expected_harvest: DateType | None = None
    crop_catalog_slug: str | None = None
    crop_days_in_place: int | None = Field(default=None, ge=0)
    is_occupied: bool


class CropHistoryEntry(BaseModel):
    """v_crop_history row — a crop that has lived at a position.

    Ordered by planted_date DESC within a position. Unassigned-position
    rows (position_id NULL) also surface; caller can filter by position_id.
    """

    model_config = ConfigDict(extra="ignore")

    position_id: int | None = None
    greenhouse_id: str
    position_label: str | None = None
    zone_slug: str | None = None
    crop_id: int
    crop_name: str
    crop_variety: str | None = None
    final_stage: str | None = None
    planted_date: DateType
    cleared_at: AwareDatetime | None = None
    is_active: bool
    days_in_place: int | None = None
    crop_catalog_slug: str | None = None
    crop_common_name: str | None = None
    event_count: int = Field(..., ge=0)
    observation_count: int = Field(..., ge=0)
    harvest_count: int = Field(..., ge=0)


class CropLifecycleEvent(BaseModel):
    """One element of the v_crop_lifecycle.events JSONB array."""

    model_config = ConfigDict(extra="ignore")

    ts: AwareDatetime
    event_type: str
    old_stage: str | None = None
    new_stage: str | None = None
    position_id: int | None = None
    notes: str | None = None
    source: str | None = None


class CropLifecycle(BaseModel):
    """v_crop_lifecycle row — a crop's full timeline.

    Includes event history (as typed CropLifecycleEvent list), harvest
    totals, observation summary. The single-call shape for the crop
    detail page on the website + MCP tool.
    """

    model_config = ConfigDict(extra="ignore")

    crop_id: int
    greenhouse_id: str
    crop_name: str
    variety: str | None = None
    current_stage: str
    is_active: bool
    planted_date: DateType
    cleared_at: AwareDatetime | None = None
    days_alive: int | None = None
    current_zone_slug: str | None = None
    current_position_label: str | None = None
    crop_catalog_slug: str | None = None
    catalog_name: str | None = None
    catalog_category: str | None = None
    events: list[CropLifecycleEvent] = Field(default_factory=list)
    total_weight_kg: Decimal = Field(default=Decimal("0"))
    total_units: Decimal = Field(default=Decimal("0"))
    total_revenue_usd: Decimal = Field(default=Decimal("0"))
    observation_count: int = Field(..., ge=0)
    avg_health_score: Decimal | None = Field(default=None, ge=0, le=1)
    latest_observation_ts: AwareDatetime | None = None
