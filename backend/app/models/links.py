"""
Association/link models for cross-domain relationships.
Simple approach - just the association tables without complex bidirectional relationships.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Column, ForeignKey
from sqlmodel import Field, SQLModel

from .enums import SensorKind

if TYPE_CHECKING:
    pass


# -------------------------------------------------------
# BASE MODELS FOR DTOs
# -------------------------------------------------------
class SensorZoneMapBase(SQLModel):
    """Base model for sensor zone mappings."""

    sensor_id: uuid.UUID
    zone_id: uuid.UUID
    kind: SensorKind


class FanGroupMemberBase(SQLModel):
    """Base model for fan group members."""

    fan_group_id: uuid.UUID
    actuator_id: uuid.UUID


# -------------------------------------------------------
# ASSOCIATION MODELS - simple association tables only
# -------------------------------------------------------
class SensorZoneMap(SensorZoneMapBase, table=True):
    """Association table mapping sensors to zones they monitor."""

    __tablename__ = "sensor_zone_map"

    sensor_id: uuid.UUID = Field(
        sa_column=Column(
            "sensor_id",
            ForeignKey("sensor.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    zone_id: uuid.UUID = Field(
        sa_column=Column(
            "zone_id",
            ForeignKey("zone.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    kind: SensorKind = Field(primary_key=True, description="Sensor kind")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 🚫 No Relationship() here - use explicit foreign keys and manual queries


class FanGroupMember(FanGroupMemberBase, table=True):
    """Association table for fan group membership."""

    __tablename__ = "fan_group_member"

    fan_group_id: uuid.UUID = Field(
        sa_column=Column(
            "fan_group_id",
            ForeignKey("fan_group.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    actuator_id: uuid.UUID = Field(
        sa_column=Column(
            "actuator_id",
            ForeignKey("actuator.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 🚫 No Relationship() here - use explicit foreign keys and manual queries


# -------------------------------------------------------
# DTO MODELS FOR API
# -------------------------------------------------------
class SensorZoneMapCreate(SensorZoneMapBase):
    """Create model for sensor zone mappings."""

    pass


class SensorZoneMapPublic(SensorZoneMapBase):
    """Public model for sensor zone mappings."""

    created_at: datetime
    updated_at: datetime


class SensorZoneMapUpdate(SQLModel):
    """Update model for sensor zone mappings."""

    kind: SensorKind | None = None


class FanGroupMemberCreate(FanGroupMemberBase):
    """Create model for fan group members."""

    pass


class FanGroupMemberPublic(FanGroupMemberBase):
    """Public model for fan group members."""

    created_at: datetime
    updated_at: datetime
