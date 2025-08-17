"""
Actuator, FanGroup, and Button models for Verdify API.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey
from sqlmodel import Field, SQLModel

from app.utils_paging import Paginated

from .enums import ActuatorKind, ButtonKind, FailSafeState

# TYPE_CHECKING imports only - no runtime circular imports
if TYPE_CHECKING:
    pass


# -------------------------------------------------------
# ACTUATOR MODELS
# -------------------------------------------------------
class ActuatorBase(SQLModel):
    name: str = Field(..., description="Actuator name")
    kind: ActuatorKind = Field(..., description="Actuator kind")
    relay_channel: int | None = Field(default=None, description="Relay channel number")
    min_on_ms: int = Field(default=60000, description="Minimum on time in milliseconds")
    min_off_ms: int = Field(
        default=60000, description="Minimum off time in milliseconds"
    )
    fail_safe_state: FailSafeState = Field(
        default=FailSafeState.OFF, description="Fail-safe state: on or off"
    )
    zone_id: uuid.UUID | None = Field(default=None, description="Associated zone ID")


class Actuator(ActuatorBase, table=True):
    __tablename__ = "actuator"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    controller_id: uuid.UUID = Field(
        sa_column=Column(
            "controller_id",
            ForeignKey("controller.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    zone_id: uuid.UUID | None = Field(
        sa_column=Column(
            "zone_id",
            ForeignKey("zone.id", ondelete="SET NULL"),
            nullable=True,
        )
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 🚫 No Relationship() here - use explicit foreign keys and manual queries


class ActuatorCreate(ActuatorBase):
    controller_id: uuid.UUID


class ActuatorPublic(ActuatorBase):
    id: uuid.UUID
    controller_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ActuatorUpdate(SQLModel):
    name: str | None = None
    kind: ActuatorKind | None = None
    relay_channel: int | None = None
    min_on_ms: int | None = None
    min_off_ms: int | None = None
    fail_safe_state: FailSafeState | None = None
    zone_id: uuid.UUID | None = None


# -------------------------------------------------------
# FAN GROUP MODELS
# -------------------------------------------------------
class FanGroupBase(SQLModel):
    name: str = Field(..., description="Fan group name")


class FanGroup(FanGroupBase, table=True):
    __tablename__ = "fan_group"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    controller_id: uuid.UUID = Field(
        sa_column=Column(
            "controller_id",
            ForeignKey("controller.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 🚫 No Relationship() here - use explicit foreign keys and manual queries


class FanGroupCreate(FanGroupBase):
    controller_id: uuid.UUID


class FanGroupPublic(FanGroupBase):
    id: uuid.UUID
    controller_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class FanGroupUpdate(SQLModel):
    name: str | None = None


# -------------------------------------------------------
# CONTROLLER BUTTON MODELS
# -------------------------------------------------------
class ControllerButtonBase(SQLModel):
    button_kind: ButtonKind = Field(..., description="Button kind")
    target_temp_stage: int | None = Field(
        default=None, description="Target temperature stage"
    )
    target_humi_stage: int | None = Field(
        default=None, description="Target humidity stage"
    )
    timeout_s: int = Field(..., description="Timeout in seconds")


class ControllerButton(ControllerButtonBase, table=True):
    __tablename__ = "controller_button"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    controller_id: uuid.UUID = Field(
        sa_column=Column(
            "controller_id",
            ForeignKey("controller.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 🚫 No Relationship() here - use explicit foreign keys and manual queries


class ControllerButtonCreate(ControllerButtonBase):
    controller_id: uuid.UUID


class ControllerButtonPublic(ControllerButtonBase):
    id: uuid.UUID
    controller_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ControllerButtonUpdate(SQLModel):
    button_kind: ButtonKind | None = None
    target_temp_stage: int | None = None
    target_humi_stage: int | None = None
    timeout_s: int | None = None


# -------------------------------------------------------
# EQUIPMENT MODELS (Legacy - for backward compatibility)
# -------------------------------------------------------
class EquipmentBase(SQLModel):
    name: str = Field(..., description="Equipment name")
    equipment_type: str = Field(..., description="Equipment type")


class Equipment(EquipmentBase, table=True):
    __tablename__ = "equipment"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    controller_id: uuid.UUID = Field(
        sa_column=Column(
            "controller_id",
            ForeignKey("controller.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 🚫 No Relationship() here - use explicit foreign keys and manual queries


class EquipmentCreate(EquipmentBase):
    controller_id: uuid.UUID


class EquipmentPublic(EquipmentBase):
    id: uuid.UUID
    controller_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class EquipmentUpdate(SQLModel):
    name: str | None = None
    equipment_type: str | None = None


# ===============================================
# PAGINATED TYPES
# ===============================================
ActuatorsPaginated = Paginated[ActuatorPublic]
ControllerButtonsPaginated = Paginated[ControllerButtonPublic]
FanGroupsPaginated = Paginated[FanGroupPublic]
