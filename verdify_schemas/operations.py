"""Operations row schemas — audit trail for hands-on greenhouse work.

Every grower/operator action lands in one of these:
- Treatment: pesticide / fungicide / fertigation application with rate + PHI/REI
- Harvest: yield event with weight, count, revenue
- IrrigationLog / IrrigationSchedule: water events + recurring rules
- LabResult: full nutrient panel from external lab
- MaintenanceLog: equipment service, cost, next-due
- ConsumablesLog: inventory (fertilizer, growing media, pest control)
"""

from __future__ import annotations

from datetime import date as DateType
from datetime import time as TimeType
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class Treatment(BaseModel):
    """treatments table row — one per pesticide/fungicide/nutrient application."""

    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    ts: AwareDatetime | None = None
    product: str = Field(..., min_length=1)
    active_ingredient: str | None = None
    concentration: float | None = Field(default=None, ge=0)
    rate: float | None = Field(default=None, ge=0)
    rate_unit: str | None = None
    method: str | None = None
    zone: str | None = None
    crop_id: int | None = None
    target_pest: str | None = None
    phi_days: int | None = Field(default=None, ge=0)  # pre-harvest interval
    rei_hours: int | None = Field(default=None, ge=0)  # restricted-entry interval
    applicator: str | None = None
    observation_id: int | None = None
    notes: str | None = None


class Harvest(BaseModel):
    """harvests table row — yield event."""

    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    ts: AwareDatetime | None = None
    crop_id: int | None = None
    weight_kg: float | None = Field(default=None, ge=0)
    unit_count: int | None = Field(default=None, ge=0)
    quality_grade: str | None = None
    zone: str | None = None
    destination: str | None = None
    unit_price: float | None = Field(default=None, ge=0)
    revenue: float | None = Field(default=None, ge=0)
    operator: str | None = None
    notes: str | None = None


class IrrigationLog(BaseModel):
    """irrigation_log table row — one row per irrigation event."""

    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    ts: AwareDatetime
    zone: str = Field(..., min_length=1)
    schedule_id: int | None = None
    scheduled_time: TimeType | None = None
    actual_start: AwareDatetime
    actual_end: AwareDatetime | None = None
    volume_gal: Decimal | None = Field(default=None, ge=0)
    source: str = "manual"
    notes: str | None = None
    created_at: AwareDatetime | None = None


class IrrigationSchedule(BaseModel):
    """irrigation_schedule table row — recurring weekly rule."""

    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    zone: str = Field(..., min_length=1)
    start_time: TimeType
    duration_s: int = Field(..., ge=0)
    days_of_week: list[int] = Field(..., min_length=1)  # 0-6 ISO
    enabled: bool = True
    notes: str | None = None
    created_at: AwareDatetime | None = None
    updated_at: AwareDatetime | None = None


class LabResult(BaseModel):
    """lab_results table row — full nutrient panel from an external lab."""

    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    ts: AwareDatetime | None = None
    sample_type: str = Field(..., min_length=1)
    zone: str | None = None
    crop_id: int | None = None
    lab_name: str | None = None
    sampled_at: DateType | None = None
    ph: float | None = Field(default=None, ge=0, le=14)
    ec_ms_cm: float | None = Field(default=None, ge=0)
    n_pct: float | None = Field(default=None, ge=0)
    p_pct: float | None = Field(default=None, ge=0)
    k_pct: float | None = Field(default=None, ge=0)
    ca_pct: float | None = Field(default=None, ge=0)
    mg_pct: float | None = Field(default=None, ge=0)
    fe_ppm: float | None = Field(default=None, ge=0)
    mn_ppm: float | None = Field(default=None, ge=0)
    zn_ppm: float | None = Field(default=None, ge=0)
    b_ppm: float | None = Field(default=None, ge=0)
    cu_ppm: float | None = Field(default=None, ge=0)
    na_ppm: float | None = Field(default=None, ge=0)
    cl_ppm: float | None = Field(default=None, ge=0)
    notes: str | None = None


class MaintenanceLog(BaseModel):
    """maintenance_log table row."""

    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    ts: AwareDatetime | None = None
    equipment: str | None = None
    service_type: str | None = None
    description: str | None = None
    cost: float | None = Field(default=None, ge=0)
    technician: str | None = None
    next_due: DateType | None = None
    notes: str | None = None


class ConsumablesLog(BaseModel):
    """consumables_log table row — inventory purchase."""

    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    purchased_date: DateType
    category: str = Field(..., min_length=1)
    item_name: str = Field(..., min_length=1)
    quantity: Decimal | None = Field(default=None, ge=0)
    unit: str | None = None
    cost_usd: Decimal = Field(..., ge=0)
    zone: str | None = None
    notes: str | None = None
    created_at: AwareDatetime | None = None
