"""
Sensor models for Verdify API.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, func
from sqlmodel import Field, SQLModel

from app.utils_paging import Paginated

from .enums import SensorKind, SensorScope, SensorValueType

# TYPE_CHECKING imports only - no runtime circular imports
if TYPE_CHECKING:
    pass


# -------------------------------------------------------
# SENSOR MODELS
# -------------------------------------------------------
class SensorBase(SQLModel):
    name: str = Field(..., description="Sensor name/identifier")
    kind: SensorKind = Field(..., description="Sensor kind from OpenAPI spec")
    scope: SensorScope = Field(
        ..., description="Sensor scope: zone, greenhouse, external"
    )
    include_in_climate_loop: bool = Field(
        default=False, description="Include in climate control"
    )

    # Modbus configuration
    modbus_slave_id: int | None = Field(default=None, description="Modbus slave ID")
    modbus_reg: int | None = Field(default=None, description="Modbus register")
    value_type: SensorValueType | None = Field(
        default=None, description="Value type: float or int"
    )
    scale_factor: float = Field(default=1.0, description="Scale factor for raw values")
    offset: float = Field(default=0.0, description="Offset for raw values")
    poll_interval_s: int = Field(default=10, description="Polling interval in seconds")


class Sensor(SensorBase, table=True):
    __tablename__ = "sensor"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    controller_id: uuid.UUID = Field(
        sa_column=Column(
            "controller_id",
            ForeignKey("controller.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    created_at: datetime = Field(
        sa_column=Column(
            "created_at",
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        )
    )
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 🚫 No Relationship() here - use explicit foreign keys and manual queries


class SensorCreate(SensorBase):
    controller_id: uuid.UUID


class SensorPublic(SensorBase):
    id: uuid.UUID
    controller_id: uuid.UUID
    # Removed: created_at, updated_at per OpenAPI spec


class SensorUpdate(SQLModel):
    name: str | None = None
    include_in_climate_loop: bool | None = None
    modbus_slave_id: int | None = None
    modbus_reg: int | None = None
    value_type: SensorValueType | None = None
    scale_factor: float | None = None
    offset: float | None = None
    poll_interval_s: int | None = None


# ===============================================
# PAGINATED TYPES
# ===============================================
SensorsPaginated = Paginated[SensorPublic]
