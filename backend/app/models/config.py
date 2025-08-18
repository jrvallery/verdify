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
# TYPED PAYLOAD MODELS (per OpenAPI spec)
# -------------------------------------------------------
class TempThresholds(SQLModel):
    """Temperature thresholds for staging levels (-3 to +3)."""

    minus3: float = Field(
        ..., description="Stage -3 temperature threshold (maximum heat demand)"
    )
    minus2: float = Field(
        ..., description="Stage -2 temperature threshold (high heat demand)"
    )
    minus1: float = Field(
        ..., description="Stage -1 temperature threshold (moderate heat demand)"
    )
    zero: float = Field(
        ..., description="Stage 0 temperature threshold (target/neutral temperature)"
    )
    plus1: float = Field(
        ..., description="Stage +1 temperature threshold (moderate cooling demand)"
    )
    plus2: float = Field(
        ..., description="Stage +2 temperature threshold (high cooling demand)"
    )
    plus3: float = Field(
        ..., description="Stage +3 temperature threshold (maximum cooling demand)"
    )


class VpdThresholds(SQLModel):
    """VPD thresholds for humidity staging levels (-3 to +3)."""

    minus3: float = Field(
        ..., description="Stage -3 VPD threshold (maximum humidification need)"
    )
    minus2: float = Field(
        ..., description="Stage -2 VPD threshold (high humidification need)"
    )
    minus1: float = Field(
        ..., description="Stage -1 VPD threshold (moderate humidification need)"
    )
    zero: float = Field(
        ..., description="Stage 0 VPD threshold (target/neutral humidity)"
    )
    plus1: float = Field(
        ..., description="Stage +1 VPD threshold (moderate dehumidification need)"
    )
    plus2: float = Field(
        ..., description="Stage +2 VPD threshold (high dehumidification need)"
    )
    plus3: float = Field(
        ..., description="Stage +3 VPD threshold (maximum dehumidification need)"
    )


class HysteresisSettings(SQLModel):
    """Hysteresis values for control stability."""

    temp_c: float = Field(..., description="Temperature hysteresis in Celsius")
    vpd_kpa: float = Field(..., description="VPD hysteresis in kPa")


class ControlBaselines(SQLModel):
    """Control thresholds and hysteresis for staging decisions."""

    temp_thresholds: TempThresholds
    vpd_thresholds: VpdThresholds
    hysteresis: HysteresisSettings


class GreenhouseConfigInfo(SQLModel):
    """Greenhouse parameters for configuration."""

    id: uuid.UUID = Field(..., description="Unique greenhouse identifier")
    title: str = Field(..., description="Human-readable greenhouse name")
    min_temp_c: float = Field(
        ..., description="Minimum allowable temperature in Celsius"
    )
    max_temp_c: float = Field(
        ..., description="Maximum allowable temperature in Celsius"
    )
    min_vpd_kpa: float = Field(..., description="Minimum vapor pressure deficit in kPa")
    max_vpd_kpa: float = Field(..., description="Maximum vapor pressure deficit in kPa")
    enthalpy_open_kjkg: float = Field(
        ..., description="Enthalpy threshold for opening in kJ/kg"
    )
    enthalpy_close_kjkg: float = Field(
        ..., description="Enthalpy threshold for closing in kJ/kg"
    )
    site_pressure_hpa: float = Field(
        ..., description="Local atmospheric pressure in hPa"
    )


class ConfigPayload(SQLModel):
    """Complete configuration package for controllers per OpenAPI spec."""

    version: int = Field(..., ge=1, description="Configuration version number")
    generated_at: datetime | None = Field(
        default=None, description="UTC timestamp when generated"
    )
    greenhouse: GreenhouseConfigInfo
    controllers: list[dict[str, Any]] = Field(
        default_factory=list, description="Controller configurations"
    )
    sensors: list[dict[str, Any]] = Field(
        default_factory=list, description="Sensor mappings"
    )
    actuators: list[dict[str, Any]] = Field(
        default_factory=list, description="Actuator mappings"
    )
    state_rules: list[dict[str, Any]] = Field(
        default_factory=list, description="Control state rules"
    )
    baselines: ControlBaselines
    rails: dict[str, Any] = Field(
        default_factory=dict, description="Safety rails and constraints"
    )


class HysteresisOverrides(SQLModel):
    """Optional hysteresis overrides for specific time periods."""

    temp_c: float | None = None
    vpd_kpa: float | None = None


class PlanSetpoint(SQLModel):
    """Individual setpoint for plan execution."""

    ts_utc: datetime = Field(..., description="UTC timestamp for this setpoint")
    min_temp_c: float = Field(..., description="Minimum temperature in Celsius")
    max_temp_c: float = Field(..., description="Maximum temperature in Celsius")
    min_vpd_kpa: float = Field(..., description="Minimum VPD in kPa")
    max_vpd_kpa: float = Field(..., description="Maximum VPD in kPa")
    temp_stage_delta: int = Field(
        default=0, ge=-1, le=1, description="Temperature stage adjustment"
    )
    humi_stage_delta: int = Field(
        default=0, ge=-1, le=1, description="Humidity stage adjustment"
    )
    hysteresis_overrides: HysteresisOverrides | None = None


class PlanIrrigation(SQLModel):
    """Irrigation event in plan."""

    ts_utc: datetime = Field(..., description="UTC timestamp for irrigation")
    actuator_id: uuid.UUID = Field(..., description="Actuator to activate")
    zone_id: uuid.UUID | None = None
    duration_s: int = Field(..., ge=1, description="Duration in seconds")
    min_soil_vwc: float | None = None


class PlanFertilization(SQLModel):
    """Fertilization event in plan."""

    ts_utc: datetime = Field(..., description="UTC timestamp for fertilization")
    actuator_id: uuid.UUID = Field(..., description="Actuator to activate")
    zone_id: uuid.UUID | None = None
    duration_s: int = Field(..., ge=1, description="Duration in seconds")


class PlanLighting(SQLModel):
    """Lighting event in plan."""

    ts_utc: datetime = Field(..., description="UTC timestamp for lighting")
    actuator_id: uuid.UUID = Field(..., description="Actuator to activate")
    duration_s: int = Field(..., ge=1, description="Duration in seconds")


class PlanPayload(SQLModel):
    """Plan payload with setpoints and scheduled events per OpenAPI spec."""

    version: int = Field(..., description="Plan version number")
    greenhouse_id: uuid.UUID = Field(..., description="Target greenhouse")
    effective_from: datetime = Field(..., description="Plan start time")
    effective_to: datetime = Field(..., description="Plan end time")
    setpoints: list[PlanSetpoint] = Field(..., description="30-min steps recommended")
    irrigation: list[PlanIrrigation] = Field(
        default_factory=list, description="Irrigation events"
    )
    fertilization: list[PlanFertilization] = Field(
        default_factory=list, description="Fertilization events"
    )
    lighting: list[PlanLighting] = Field(
        default_factory=list, description="Lighting events"
    )


# -------------------------------------------------------
# CONFIG SNAPSHOT MODELS
# -------------------------------------------------------
class ConfigSnapshotBase(SQLModel):
    version: int = Field(..., description="Config version number")
    payload: ConfigPayload = Field(
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
    payload: PlanPayload = Field(..., sa_type=JSON, description="Plan payload")
    is_active: bool = Field(
        default=False, description="Whether this plan is currently active"
    )
    effective_from: datetime = Field(
        ..., description="When this plan becomes effective"
    )
    effective_to: datetime = Field(..., description="When this plan expires")


class Plan(PlanBase, table=True):
    """Plan model with database constraints.

    Database constraints:
    - uq_plan_greenhouse_version: Unique version per greenhouse
    - uq_plan_active_per_greenhouse: Only one active plan per greenhouse (partial index WHERE is_active=true)
    """

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


class PlanCreate(SQLModel):
    """Create model for plans - version assigned by server."""

    greenhouse_id: uuid.UUID
    is_active: bool = Field(
        default=False, description="Whether this plan is currently active"
    )
    effective_from: datetime = Field(
        ..., description="When this plan becomes effective"
    )
    effective_to: datetime = Field(..., description="When this plan expires")
    payload: PlanPayload = Field(..., sa_type=JSON, description="Plan payload")
    created_by: uuid.UUID | None = None


class PlanPublic(SQLModel):
    """Public model for plans - spec compliant fields only."""

    id: uuid.UUID
    version: int = Field(..., description="Plan version number")
    greenhouse_id: uuid.UUID
    is_active: bool = Field(
        default=False, description="Whether this plan is currently active"
    )
    effective_from: datetime = Field(
        ..., description="When this plan becomes effective"
    )
    effective_to: datetime = Field(..., description="When this plan expires")
    created_at: datetime = Field(..., description="Plan creation timestamp")
    payload: PlanPayload = Field(..., description="Plan payload")
    etag: str = Field(..., description="ETag for caching")
    # Removed: created_by, updated_at per OpenAPI spec


class PlanUpdate(SQLModel):
    is_active: bool | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    payload: PlanPayload | None = None


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
    payload: ConfigPayload = Field(..., description="Complete configuration payload")


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
