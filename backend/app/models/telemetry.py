"""Telemetry and idempotency models for request deduplication."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey, UniqueConstraint
from sqlmodel import Field, SQLModel

if TYPE_CHECKING:
    pass


# -------------------------------------------------------
# TELEMETRY DTO MODELS
# -------------------------------------------------------


class TelemetrySensorsReading(SQLModel):
    """Individual sensor reading within a telemetry batch."""

    sensor_index: int = Field(..., description="0-based sensor index")
    timestamp: str = Field(..., description="ISO 8601 timestamp of reading")
    value: float = Field(..., description="Sensor reading value")
    unit: str = Field(..., description="Unit of measurement")


class TelemetrySensors(SQLModel):
    """Sensor telemetry batch from device."""

    readings: list[TelemetrySensorsReading] = Field(
        ..., description="Array of sensor readings"
    )


class TelemetryActuatorsEvent(SQLModel):
    """Individual actuator event within a telemetry batch."""

    actuator_index: int = Field(..., description="0-based actuator index")
    timestamp: str = Field(..., description="ISO 8601 timestamp of event")
    action: str = Field(..., description="Action performed (on/off/adjust)")
    value: float | None = Field(None, description="Value if action was adjust")


class TelemetryActuators(SQLModel):
    """Actuator telemetry batch from device."""

    events: list[TelemetryActuatorsEvent] = Field(
        ..., description="Array of actuator events"
    )


class TelemetryStatusData(SQLModel):
    """Controller status data."""

    uptime_seconds: int = Field(..., description="Controller uptime in seconds")
    memory_usage_kb: int = Field(..., description="Memory usage in kilobytes")
    cpu_usage_percent: float = Field(..., description="CPU usage percentage")
    network_connected: bool = Field(..., description="Network connectivity status")
    last_reboot_reason: str = Field(..., description="Reason for last reboot")


class TelemetryStatus(SQLModel):
    """Controller status telemetry."""

    timestamp: str = Field(..., description="ISO 8601 timestamp")
    status: TelemetryStatusData = Field(..., description="Status data")


class TelemetryInputsEvent(SQLModel):
    """Individual input/button event."""

    input_index: int = Field(..., description="0-based input index")
    timestamp: str = Field(..., description="ISO 8601 timestamp of event")
    event_type: str = Field(..., description="Event type (press/release)")
    duration_ms: int | None = Field(None, description="Duration if applicable")


class TelemetryInputs(SQLModel):
    """Input/button telemetry batch from device."""

    events: list[TelemetryInputsEvent] = Field(..., description="Array of input events")


class TelemetryBatch(SQLModel):
    """Mixed telemetry batch containing multiple types."""

    sensors: TelemetrySensors | None = Field(None, description="Sensor readings if any")
    actuators: TelemetryActuators | None = Field(
        None, description="Actuator events if any"
    )
    status: TelemetryStatus | None = Field(None, description="Status update if any")
    inputs: TelemetryInputs | None = Field(None, description="Input events if any")


class IngestResult(SQLModel):
    """Result of telemetry ingestion."""

    success: bool = Field(..., description="Whether ingestion was successful")
    message: str = Field(..., description="Human-readable result message")
    records_processed: int = Field(..., description="Number of records processed")
    request_id: str = Field(..., description="Request ID for tracking")


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
