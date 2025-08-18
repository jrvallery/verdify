"""Telemetry and idempotency models for request deduplication."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, UniqueConstraint
from sqlmodel import Field, SQLModel

from .enums import ButtonAction, ButtonKind, SensorKind, SensorScope

if TYPE_CHECKING:
    pass


# -------------------------------------------------------
# TELEMETRY DTO MODELS (OpenAPI v2 Spec Compliance)
# -------------------------------------------------------


class TelemetrySensorsReading(SQLModel):
    """Individual sensor reading within a telemetry batch - spec compliant."""

    sensor_id: uuid.UUID = Field(..., description="Sensor UUID")
    kind: SensorKind = Field(..., description="Sensor kind from spec")
    value: float = Field(..., description="Sensor reading value")
    ts_utc: datetime = Field(..., description="Timestamp of reading")
    scope: SensorScope | None = Field(None, description="Sensor scope")
    zone_ids: list[uuid.UUID] | None = Field(None, description="Associated zone IDs")


class TelemetrySensors(SQLModel):
    """Sensor telemetry batch from device - spec compliant."""

    batch_id: str | None = Field(None, description="Optional batch identifier")
    ts_utc: datetime | None = Field(None, description="Batch timestamp")
    readings: list[TelemetrySensorsReading] = Field(
        ..., description="Array of sensor readings"
    )


class TelemetryActuatorsEvent(SQLModel):
    """Individual actuator event within a telemetry batch - spec compliant."""

    actuator_id: uuid.UUID = Field(..., description="Actuator UUID")
    ts_utc: datetime = Field(..., description="Timestamp of event")
    state: bool = Field(..., description="Actuator state (on/off)")
    reason: str = Field(..., description="Reason for state change")


class TelemetryActuators(SQLModel):
    """Actuator telemetry batch from device - spec compliant."""

    events: list[TelemetryActuatorsEvent] = Field(
        ..., description="Array of actuator events"
    )


class TelemetryStatus(SQLModel):
    """Controller status telemetry - spec compliant flat structure."""

    ts_utc: datetime = Field(..., description="Status timestamp")
    temp_stage: int = Field(..., ge=-3, le=3, description="Temperature stage")
    humi_stage: int = Field(..., ge=-3, le=3, description="Humidity stage")
    avg_interior_temp_c: float | None = Field(None, description="Average interior temp")
    avg_interior_rh_pct: float | None = Field(None, description="Average interior RH")
    avg_interior_pressure_hpa: float | None = Field(
        None, description="Average interior pressure"
    )
    avg_exterior_temp_c: float | None = Field(None, description="Average exterior temp")
    avg_exterior_rh_pct: float | None = Field(None, description="Average exterior RH")
    avg_exterior_pressure_hpa: float | None = Field(
        None, description="Average exterior pressure"
    )
    avg_vpd_kpa: float | None = Field(None, description="Average VPD")
    enthalpy_in_kj_per_kg: float | None = Field(None, description="Enthalpy in")
    enthalpy_out_kj_per_kg: float | None = Field(None, description="Enthalpy out")
    override_active: bool = Field(default=False, description="Override active")
    plan_version: int | None = Field(None, description="Plan version")
    plan_stale: bool = Field(
        default=False, description="Plan expired beyond grace period"
    )
    offline_sensors: list[uuid.UUID] = Field(
        default_factory=list, description="Offline sensor IDs"
    )
    fallback_active: bool = Field(
        default=False, description="Controller in fallback mode"
    )
    uptime_s: int | None = Field(None, description="Controller uptime in seconds")
    loop_ms: int | None = Field(
        None, description="Main control loop execution time in milliseconds"
    )
    config_version: int | None = Field(None, description="Current config version")


class TelemetryInputsEvent(SQLModel):
    """Individual input/button event - spec compliant."""

    button_kind: ButtonKind = Field(..., description="Button kind from spec")
    ts_utc: datetime = Field(..., description="Timestamp of event")
    action: ButtonAction = Field(..., description="Action: pressed or released")
    latched: bool = Field(default=False, description="Whether button is latched")


class TelemetryInputs(SQLModel):
    """Input/button telemetry batch from device - spec compliant."""

    inputs: list[TelemetryInputsEvent] = Field(..., description="Array of input events")


class TelemetryBatch(SQLModel):
    """Mixed telemetry batch containing multiple types - spec compliant."""

    sensors: TelemetrySensors | None = Field(None, description="Sensor readings if any")
    actuators: TelemetryActuators | None = Field(
        None, description="Actuator events if any"
    )
    status: TelemetryStatus | None = Field(None, description="Status update if any")
    inputs: TelemetryInputs | None = Field(None, description="Input events if any")


class IngestResult(SQLModel):
    """Result of telemetry ingestion - spec compliant."""

    accepted: int = Field(..., description="Number of accepted records")
    rejected: int = Field(..., description="Number of rejected records")
    errors: list[dict] = Field(
        default_factory=list, description="Array of ErrorResponse objects"
    )


# -------------------------------------------------------
# IDEMPOTENCY KEY MODELS
# -------------------------------------------------------
class IdempotencyKeyBase(SQLModel):
    key: str = Field(..., description="Idempotency key string")
    body_hash: str = Field(..., description="Hash of request body")
    response_status: int = Field(..., description="HTTP response status code")
    response_body: str | None = Field(default=None, description="Response body")


class IdempotencyKey(IdempotencyKeyBase, table=True):
    __tablename__ = "idempotency_key"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(..., description="When this key expires")
    controller_id: uuid.UUID = Field(
        sa_column=Column(
            "controller_id",
            ForeignKey("controller.id", ondelete="CASCADE"),
            nullable=False,
        )
    )

    # 🚫 No Relationship() here - use explicit foreign keys and manual queries

    __table_args__ = (
        UniqueConstraint("key", "controller_id", name="uq_idempotency_key_controller"),
    )


class IdempotencyKeyCreate(IdempotencyKeyBase):
    controller_id: uuid.UUID = Field(
        ..., description="Controller that submitted the request"
    )
    expires_at: datetime


class IdempotencyKeyPublic(IdempotencyKeyBase):
    id: uuid.UUID
    controller_id: uuid.UUID  # Include for public representation
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
