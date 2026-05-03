"""API response envelopes.

These are the **wire shapes** FastAPI returns — separate from the DB row
models because responses often fold in joined fields (e.g. `latest_health`
off of recent observations, `active_crops` count on zones).

Applied via `response_model=X` on the top 8 endpoints in `api/main.py`.
FastAPI coerces asyncpg Record → dict → Pydantic model at response time
and auto-populates the OpenAPI spec at /docs.
"""

from __future__ import annotations

from datetime import date as DateType
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from .crops import Observation


class APIStatus(BaseModel):
    """GET /api/v1/status — health check."""

    model_config = ConfigDict(extra="ignore")

    status: str
    active_crops: int = Field(..., ge=0)
    observations: int = Field(..., ge=0)
    latest_climate_ts: AwareDatetime | None = None


class PublicDataHealthCheck(BaseModel):
    """One public-safe data-health check row."""

    model_config = ConfigDict(extra="ignore")

    name: str
    status: Literal["ok", "warn", "fail"]
    metric_value: float | None = None
    threshold_value: float | None = None
    details: str | None = None


class PublicPipelineHealthSource(BaseModel):
    """Freshness/null-rate summary for one telemetry source."""

    model_config = ConfigDict(extra="ignore")

    source: str
    rows_1h: int = Field(..., ge=0)
    rows_24h: int = Field(..., ge=0)
    age_s: int | None = Field(default=None, ge=0)
    null_pct_1h: float | None = Field(default=None, ge=0, le=100)


class PublicDataHealthResponse(BaseModel):
    """GET /api/v1/public/data-health."""

    model_config = ConfigDict(extra="ignore")

    generated_at: AwareDatetime
    overall_status: Literal["ok", "warn", "fail"]
    checks: list[PublicDataHealthCheck]
    pipeline_sources: list[PublicPipelineHealthSource]


class PublicHomeMetrics(BaseModel):
    """GET /api/v1/public/home-metrics — launch-safe proof counters."""

    model_config = ConfigDict(extra="ignore")

    generated_at: AwareDatetime
    greenhouse_id: str
    climate_rows: int = Field(..., ge=0)
    climate_days: float = Field(..., ge=0)
    active_crops: int = Field(..., ge=0)
    plan_count: int = Field(..., ge=0)
    lesson_count: int = Field(..., ge=0)
    latest_climate_ts: AwareDatetime | None = None
    latest_climate_age_s: int | None = Field(default=None, ge=0)
    indoor_temp_f: float | None = None
    indoor_vpd_kpa: float | None = None
    outdoor_temp_f: float | None = None
    outdoor_rh_pct: float | None = None
    last_plan_id: str | None = None
    last_plan_created_at: AwareDatetime | None = None
    last_plan_age_s: int | None = Field(default=None, ge=0)
    planner_score_today: float | None = None
    compliance_pct_today: float | None = None
    cost_today_usd: float | None = None
    water_today_gal: float | None = None
    open_critical_high_alerts: int = Field(..., ge=0)
    data_health_status: Literal["ok", "warn", "fail"]
    data_health_warnings: list[PublicDataHealthCheck] = Field(default_factory=list)


class ZoneListItem(BaseModel):
    """GET /api/v1/zones — one row per zone."""

    model_config = ConfigDict(extra="ignore")

    zone: str
    active_crops: int = Field(..., ge=0)
    current_temp: float | None = None


class ZoneObservation(BaseModel):
    """Nested observation row for zone detail response."""

    model_config = ConfigDict(extra="ignore")

    ts: AwareDatetime
    obs_type: str
    health_score: float | None = None
    notes: str | None = None
    crop_name: str | None = None


class ZoneDetail(BaseModel):
    """GET /api/v1/zones/{zone}."""

    model_config = ConfigDict(extra="ignore")

    zone: str
    crops: list[dict]  # Permissive — zone-detail returns a mix of crop fields
    recent_observations: list[ZoneObservation]


class CropListItem(BaseModel):
    """GET /api/v1/crops — crop row + joined `latest_health`."""

    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    variety: str | None = None
    position: str
    zone: str
    planted_date: DateType
    expected_harvest: DateType | None = None
    stage: str = "seed"
    count: int | None = None
    seed_lot_id: str | None = None
    supplier: str | None = None
    base_temp_f: float = 50.0
    target_dli: float | None = None
    target_vpd_low: float | None = None
    target_vpd_high: float | None = None
    notes: str | None = None
    is_active: bool = True
    created_at: AwareDatetime | None = None
    updated_at: AwareDatetime | None = None
    greenhouse_id: str = "vallery"
    latest_health: float | None = Field(default=None, ge=0, le=1)


class CropRecentObservation(BaseModel):
    """Lightweight observation summary for crop-detail responses."""

    model_config = ConfigDict(extra="ignore")

    ts: AwareDatetime
    obs_type: str
    health_score: float | None = None
    notes: str | None = None
    source: str | None = None


class CropDetail(CropListItem):
    """GET /api/v1/crops/{id} — crop row + recent observations."""

    recent_observations: list[CropRecentObservation] = Field(default_factory=list)


class CropHealthSummaryItem(BaseModel):
    """GET /api/v1/health/summary — one row per active crop."""

    model_config = ConfigDict(extra="ignore")

    name: str
    zone: str
    position: str
    stage: str
    avg_health: float | None = Field(default=None, ge=0, le=1)
    obs_count: int = Field(..., ge=0)
    last_observed: AwareDatetime | None = None


class HealthTrendPoint(BaseModel):
    """GET /api/v1/crops/{id}/health — one observation on the health timeline."""

    model_config = ConfigDict(extra="ignore")

    ts: AwareDatetime
    health_score: float | None = Field(default=None, ge=0, le=1)
    obs_type: str
    notes: str | None = None
    source: str | None = None


class ObservationWithCrop(Observation):
    """GET /api/v1/observations/recent — observation row joined with crop fields."""

    model_config = ConfigDict(extra="ignore")

    crop_name: str | None = None
    crop_zone: str | None = None


# GET /setpoints returns a flat dict[str, float] — FastAPI handles that
# natively; no response model needed (the endpoint returns a plain dict).
