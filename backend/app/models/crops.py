"""
Crop and ZoneCrop models for Verdify API.
"""
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Column, DateTime, Enum, ForeignKey
from sqlalchemy.sql import func
from sqlmodel import Field, SQLModel

from app.utils_paging import Paginated

if TYPE_CHECKING:
    pass


# Import the new enum
from .enums import ObservationType


# -------------------------------------------------------
# CROP MODELS (Global crop templates)
# -------------------------------------------------------
class CropBase(SQLModel):
    name: str = Field(
        ..., max_length=255, description="Name of the crop (e.g., 'Tomato')"
    )
    description: str | None = Field(default=None, max_length=500)
    expected_yield_per_sqm: float | None = Field(
        default=None, description="Expected yield per square meter"
    )
    growing_days: int | None = Field(
        default=None, description="Expected days from seed to harvest"
    )


class Crop(CropBase, table=True):
    __tablename__ = "crop"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    recipe: dict[str, Any] | None = Field(
        default=None, sa_type=JSON, description="JSON recipe for the crop"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 🚫 No Relationship() here - use explicit foreign keys and manual queries


class CropCreate(CropBase):
    recipe: dict[str, Any] | None = None


class CropPublic(CropBase):
    id: uuid.UUID
    recipe: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class CropUpdate(SQLModel):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    recipe: dict[str, Any] | None = None
    expected_yield_per_sqm: float | None = None
    growing_days: int | None = None


# -------------------------------------------------------
# ZONE CROP MODELS (Zone-specific crop instance)
# -------------------------------------------------------
class ZoneCropBase(SQLModel):
    start_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_date: datetime | None = Field(default=None)
    is_active: bool = Field(default=True)
    final_yield: float | None = Field(default=None, description="Total yield produced")
    area_sqm: float | None = Field(
        default=None, description="Area used in square meters"
    )


class ZoneCrop(ZoneCropBase, table=True):
    __tablename__ = "zone_crop"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    crop_id: uuid.UUID | None = Field(  # Change to SET NULL for global crop templates
        sa_column=Column(
            "crop_id", ForeignKey("crop.id", ondelete="SET NULL"), nullable=True
        )
    )
    zone_id: uuid.UUID = Field(
        sa_column=Column(
            "zone_id", ForeignKey("zone.id", ondelete="CASCADE"), nullable=False
        )
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 🚫 No Relationship() here - use explicit foreign keys and manual queries


class ZoneCropCreate(ZoneCropBase):
    crop_id: uuid.UUID
    zone_id: uuid.UUID
    start_date: datetime  # Make required in create, remove default


class ZoneCropPublic(ZoneCropBase):
    id: uuid.UUID
    crop_id: uuid.UUID | None
    zone_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ZoneCropUpdate(SQLModel):
    end_date: datetime | None = None
    is_active: bool | None = None
    final_yield: float | None = None
    area_sqm: float | None = None


# -------------------------------------------------------
# ZONE CROP OBSERVATION MODELS
# -------------------------------------------------------
class ZoneCropObservationBase(SQLModel):
    observed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When observation was made",
    )
    observation_type: ObservationType | None = Field(
        default=None,
        description="Type of observation: growth, pest, disease, harvest, general",
    )
    notes: str | None = Field(default=None, max_length=2000)
    image_url: str | None = Field(
        default=None, max_length=500, description="URL to uploaded image"
    )
    height_cm: float | None = Field(default=None, description="Plant height in cm")
    health_score: int | None = Field(
        default=None, ge=1, le=10, description="Health score 1-10"
    )


class ZoneCropObservation(ZoneCropObservationBase, table=True):
    __tablename__ = "zone_crop_observation"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    zone_crop_id: uuid.UUID = Field(
        sa_column=Column(
            "zone_crop_id",
            ForeignKey("zone_crop.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    # Override observation_type to ensure proper enum serialization
    observation_type: ObservationType | None = Field(
        default=None,
        sa_column=Column(
            "observation_type",
            Enum(ObservationType, values_callable=lambda obj: [e.value for e in obj]),
            nullable=True,
        ),
        description="Type of observation: growth, pest, disease, harvest, general",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            "created_at",
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
    )
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 🚫 No Relationship() here - use explicit foreign keys and manual queries


class ZoneCropObservationCreate(ZoneCropObservationBase):
    zone_crop_id: uuid.UUID


class ZoneCropObservationPublic(ZoneCropObservationBase):
    id: uuid.UUID
    zone_crop_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ZoneCropObservationUpdate(SQLModel):
    observation_type: ObservationType | None = None
    notes: str | None = Field(default=None, max_length=2000)
    image_url: str | None = Field(default=None, max_length=500)
    height_cm: float | None = None
    health_score: int | None = Field(default=None, ge=1, le=10)


# ===============================================
# PAGINATED TYPES
# ===============================================
CropsPaginated = Paginated[CropPublic]
ZoneCropsPaginated = Paginated[ZoneCropPublic]
ZoneCropObservationsPaginated = Paginated[ZoneCropObservationPublic]
