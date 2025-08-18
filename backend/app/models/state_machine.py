"""
State machine models for greenhouse climate control.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Column, ForeignKey, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.utils_paging import Paginated

# TYPE_CHECKING imports only - no runtime circular imports
if TYPE_CHECKING:
    pass


# -------------------------------------------------------
# STATE MACHINE TYPED MODELS
# -------------------------------------------------------
class FanGroupOn(SQLModel):
    """Typed model for fan group on configuration."""

    fan_group_id: uuid.UUID = Field(..., description="Fan group UUID")
    on_count: int = Field(..., ge=0, description="Number of fans to turn on")


# -------------------------------------------------------
# STATE MACHINE ROW MODELS
# -------------------------------------------------------
class StateMachineRowBase(SQLModel):
    """Base model for state machine configuration rows."""

    temp_stage: int | None = Field(
        default=None, ge=-3, le=3, description="Temperature stage (-3 to 3)"
    )
    humi_stage: int | None = Field(
        default=None, ge=-3, le=3, description="Humidity stage (-3 to 3)"
    )
    is_fallback: bool = Field(
        default=False, description="Whether this is a fallback row"
    )
    must_on_actuators: list[str] = Field(
        default_factory=list, description="Actuator IDs that must be on"
    )
    must_off_actuators: list[str] = Field(
        default_factory=list, description="Actuator IDs that must be off"
    )
    must_on_fan_groups: list[FanGroupOn] = Field(
        default_factory=list, description="Fan group configurations"
    )
    must_off_fan_groups: list[uuid.UUID] = Field(
        default_factory=list, description="Fan group IDs that must be off"
    )


class StateMachineRow(StateMachineRowBase, table=True):
    """State machine row database model - greenhouse scoped."""

    __tablename__ = "state_machine_row"
    __table_args__ = (
        UniqueConstraint(
            "greenhouse_id", "temp_stage", "humi_stage", name="uq_smrow_gh_temp_humi"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    greenhouse_id: uuid.UUID = Field(
        sa_column=Column(
            "greenhouse_id",
            ForeignKey("greenhouse.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    must_on_actuators: list[str] = Field(default_factory=list, sa_type=JSON)
    must_off_actuators: list[str] = Field(default_factory=list, sa_type=JSON)
    must_on_fan_groups: list[FanGroupOn] = Field(
        default_factory=list, sa_type=JSON
    )  # Typed as FanGroupOn objects
    must_off_fan_groups: list[uuid.UUID] = Field(default_factory=list, sa_type=JSON)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 🚫 No Relationship() here - use explicit foreign keys and manual queries


class StateMachineRowCreate(StateMachineRowBase):
    """Create model for state machine rows."""

    greenhouse_id: uuid.UUID


class StateMachineRowUpdate(SQLModel):
    """Update model for state machine rows."""

    temp_stage: int | None = Field(default=None, ge=-3, le=3)
    humi_stage: int | None = Field(default=None, ge=-3, le=3)
    is_fallback: bool | None = None
    must_on_actuators: list[str] | None = None
    must_off_actuators: list[str] | None = None
    must_on_fan_groups: list[FanGroupOn] | None = None
    must_off_fan_groups: list[uuid.UUID] | None = None


class StateMachineRowPublic(StateMachineRowBase):
    """Public model for state machine rows."""

    id: uuid.UUID
    greenhouse_id: uuid.UUID
    # Removed: created_at, updated_at per OpenAPI spec


# -------------------------------------------------------
# STATE MACHINE FALLBACK MODELS
# -------------------------------------------------------
class StateMachineFallbackBase(SQLModel):
    """Base model for state machine fallback configuration."""

    must_on_actuators: list[str] = Field(
        default_factory=list, description="Actuator IDs that must be on in fallback"
    )
    must_off_actuators: list[str] = Field(
        default_factory=list, description="Actuator IDs that must be off in fallback"
    )
    must_on_fan_groups: list[FanGroupOn] = Field(
        default_factory=list, description="Fan group configurations for fallback"
    )
    must_off_fan_groups: list[uuid.UUID] = Field(
        default_factory=list, description="Fan group IDs that must be off in fallback"
    )


class StateMachineFallback(StateMachineFallbackBase, table=True):
    """State machine fallback database model - one per greenhouse."""

    __tablename__ = "state_machine_fallback"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    greenhouse_id: uuid.UUID = Field(
        sa_column=Column(
            "greenhouse_id",
            ForeignKey("greenhouse.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        )
    )
    must_on_actuators: list[str] = Field(default_factory=list, sa_type=JSON)
    must_off_actuators: list[str] = Field(default_factory=list, sa_type=JSON)
    must_on_fan_groups: list[FanGroupOn] = Field(
        default_factory=list, sa_type=JSON
    )  # Typed as FanGroupOn objects
    must_off_fan_groups: list[uuid.UUID] = Field(default_factory=list, sa_type=JSON)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 🚫 No Relationship() here - use explicit foreign keys and manual queries


class StateMachineFallbackCreate(StateMachineFallbackBase):
    """Create model for state machine fallback."""

    greenhouse_id: uuid.UUID


class StateMachineFallbackUpdate(SQLModel):
    """Update model for state machine fallback."""

    must_on_actuators: list[str] | None = None
    must_off_actuators: list[str] | None = None
    must_on_fan_groups: list[FanGroupOn] | None = None
    must_off_fan_groups: list[uuid.UUID] | None = None


class StateMachineFallbackPublic(StateMachineFallbackBase):
    """Public model for state machine fallback."""

    id: uuid.UUID
    greenhouse_id: uuid.UUID
    # Removed: created_at, updated_at per OpenAPI spec


# ===============================================
# PAGINATED TYPES
# ===============================================
StateMachineRowsPaginated = Paginated[StateMachineRowPublic]
