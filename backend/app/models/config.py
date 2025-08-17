"""Configuration and planning models for greenhouse configuration snapshots and plans."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Column, ForeignKey, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.utils_paging import Paginated

if TYPE_CHECKING:
    pass


# -------------------------------------------------------
# CONFIG SNAPSHOT MODELS
# -------------------------------------------------------
class ConfigSnapshotBase(SQLModel):
    version: int = Field(..., description="Config version number")
    payload: dict[str, Any] = Field(
        ..., sa_type=JSON, description="Configuration payload"
    )
    etag: str = Field(..., description="ETag for caching")


class ConfigSnapshot(ConfigSnapshotBase, table=True):
    __tablename__ = "config_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "greenhouse_id", "version", name="uq_config_snapshot_greenhouse_version"
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
    created_by: uuid.UUID | None = Field(
        sa_column=Column(
            "created_by",
            ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        )
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 🚫 No Relationship() here - use explicit foreign keys and manual queries


class ConfigSnapshotCreate(ConfigSnapshotBase):
    greenhouse_id: uuid.UUID
    created_by: uuid.UUID | None = None


class ConfigSnapshotPublic(ConfigSnapshotBase):
    id: uuid.UUID
    greenhouse_id: uuid.UUID
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


# -------------------------------------------------------
# PLAN MODELS
# -------------------------------------------------------
class PlanBase(SQLModel):
    version: int = Field(..., description="Plan version number")
    payload: dict[str, Any] = Field(..., sa_type=JSON, description="Plan payload")
    is_active: bool = Field(
        default=False, description="Whether this plan is currently active"
    )
    effective_from: datetime = Field(
        ..., description="When this plan becomes effective"
    )
    effective_to: datetime = Field(..., description="When this plan expires")


class Plan(PlanBase, table=True):
    __tablename__ = "plan"
    __table_args__ = (
        UniqueConstraint("greenhouse_id", "version", name="uq_plan_greenhouse_version"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    etag: str = Field(..., description="ETag for caching")
    greenhouse_id: uuid.UUID = Field(
        sa_column=Column(
            "greenhouse_id",
            ForeignKey("greenhouse.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    created_by: uuid.UUID | None = Field(
        sa_column=Column(
            "created_by",
            ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        )
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 🚫 No Relationship() here - use explicit foreign keys and manual queries


class PlanCreate(PlanBase):
    greenhouse_id: uuid.UUID
    created_by: uuid.UUID | None = None


class PlanPublic(PlanBase):
    id: uuid.UUID
    greenhouse_id: uuid.UUID
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class PlanUpdate(SQLModel):
    is_active: bool | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    payload: dict[str, Any] | None = None


# -------------------------------------------------------
# CONFIG PUBLISH/DIFF DTOs
# -------------------------------------------------------
class ConfigPublishRequest(SQLModel):
    """Request DTO for publishing greenhouse configuration."""

    dry_run: bool = Field(
        default=False, description="If true, return preview without persisting"
    )


class ConfigPublishResult(SQLModel):
    """Result of config publish operation."""

    published: bool = Field(..., description="Whether snapshot was actually persisted")
    version: int = Field(..., description="Configuration version number")
    errors: list[str] = Field(default_factory=list, description="Validation errors")
    warnings: list[str] = Field(default_factory=list, description="Validation warnings")
    payload: dict[str, Any] = Field(..., description="Complete configuration payload")


class ConfigDiff(SQLModel):
    """JSON patch-like diff between current DB state and last published snapshot."""

    added: list[str] = Field(
        default_factory=list, description="Added configuration paths"
    )
    removed: list[str] = Field(
        default_factory=list, description="Removed configuration paths"
    )
    changed: list[str] = Field(
        default_factory=list, description="Modified configuration paths"
    )


# ===============================================
# PAGINATED TYPES
# ===============================================
ConfigSnapshotsPaginated = Paginated[ConfigSnapshotPublic]
PlansPaginated = Paginated[PlanPublic]
