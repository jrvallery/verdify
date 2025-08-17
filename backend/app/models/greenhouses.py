"""import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Column, DateTime, ForeignKey, func
from sqlmodel import Field, SQLModelhouse and Zone models for Verdify API.
"""
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import Column, DateTime, ForeignKey, func
from sqlmodel import JSON, Field, SQLModel

from app.utils_paging import Paginated

from .enums import LocationEnum

# Direct imports for forward reference resolution - these are available since
# greenhouses module is imported after users and crops in __init__.py dependency order

if TYPE_CHECKING:
    pass


# -------------------------------------------------------
# GREENHOUSE MODELS
# -------------------------------------------------------
class GreenhouseBase(SQLModel):
    title: str = Field(
        min_length=1, max_length=255
    )  # Updated field name to match OpenAPI spec
    description: str | None = Field(default=None, max_length=255)
    is_active: bool = Field(
        default=True, description="Whether this greenhouse is active"
    )

    latitude: float | None = Field(
        default=None, description="Latitude of greenhouse location"
    )
    longitude: float | None = Field(
        default=None, description="Longitude of greenhouse location"
    )

    # Control parameters with defaults matching OpenAPI schema
    min_temp_c: float = Field(default=7.0, description="Minimum temperature in Celsius")
    max_temp_c: float = Field(
        default=35.0, description="Maximum temperature in Celsius"
    )
    min_vpd_kpa: float = Field(default=0.3, description="Minimum VPD in kPa")
    max_vpd_kpa: float = Field(default=2.5, description="Maximum VPD in kPa")
    enthalpy_open_kjkg: float = Field(
        default=-2.0, description="Enthalpy threshold for opening in kJ/kg"
    )
    enthalpy_close_kjkg: float = Field(
        default=1.0, description="Enthalpy threshold for closing in kJ/kg"
    )
    site_pressure_hpa: float = Field(default=840.0, description="Site pressure in hPa")
    context_text: str | None = Field(
        default=None, max_length=4000, description="Additional context information"
    )

    # New OpenAPI v2 fields
    rails_max_temp_c: float = Field(
        default=50.0, description="Maximum rail/track temperature in Celsius"
    )
    rails_min_temp_c: float = Field(
        default=-10.0, description="Minimum rail/track temperature in Celsius"
    )
    params: dict[str, Any] | None = Field(
        default=None, sa_type=JSON, description="Additional greenhouse parameters"
    )


class Greenhouse(GreenhouseBase, table=True):
    __tablename__ = "greenhouse"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        sa_column=Column(
            "user_id", ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
        )
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 🚫 No Relationship() here - use explicit foreign keys and manual queries


class GreenhouseCreate(GreenhouseBase):
    pass


class GreenhouseUpdate(SQLModel):
    title: str | None = Field(
        default=None, min_length=1, max_length=255
    )  # Updated field name to match OpenAPI spec
    description: str | None = None
    is_active: bool | None = None
    latitude: float | None = None
    longitude: float | None = None
    min_temp_c: float | None = None
    max_temp_c: float | None = None
    min_vpd_kpa: float | None = None
    max_vpd_kpa: float | None = None
    enthalpy_open_kjkg: float | None = None
    enthalpy_close_kjkg: float | None = None
    site_pressure_hpa: float | None = None
    context_text: str | None = Field(default=None, max_length=4000)
    rails_max_temp_c: float | None = None
    rails_min_temp_c: float | None = None
    params: dict[str, Any] | None = None


class GreenhousePublic(GreenhouseBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class GreenhousePublicAPI(SQLModel):
    """
    Public greenhouse schema matching OpenAPI spec exactly.
    Excludes internal fields: user_id, rails_*, params, created_at, updated_at.
    """

    id: uuid.UUID = Field(description="Greenhouse unique identifier")
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)
    is_active: bool = Field(
        default=True, description="Whether this greenhouse is active"
    )
    latitude: float | None = Field(
        default=None, description="Latitude of greenhouse location"
    )
    longitude: float | None = Field(
        default=None, description="Longitude of greenhouse location"
    )
    min_temp_c: float = Field(default=7.0, description="Minimum temperature in Celsius")
    max_temp_c: float = Field(
        default=35.0, description="Maximum temperature in Celsius"
    )
    min_vpd_kpa: float = Field(default=0.3, description="Minimum VPD in kPa")
    max_vpd_kpa: float = Field(default=2.5, description="Maximum VPD in kPa")
    enthalpy_open_kjkg: float = Field(
        default=-2.0, description="Enthalpy threshold for opening in kJ/kg"
    )
    enthalpy_close_kjkg: float = Field(
        default=1.0, description="Enthalpy threshold for closing in kJ/kg"
    )
    site_pressure_hpa: float = Field(default=840.0, description="Site pressure in hPa")
    context_text: str | None = Field(
        default=None, max_length=4000, description="Additional context information"
    )


# -------------------------------------------------------
# ZONE MODELS
# -------------------------------------------------------
class ZoneBase(SQLModel):
    zone_number: int = Field(..., description="Numeric identifier within greenhouse")
    location: LocationEnum = Field(..., description="N, E, S, W, NE, SE, SW, NW")
    is_active: bool = Field(
        default=True, description="Whether the zone is currently active"
    )
    context_text: str | None = Field(
        default=None, max_length=2000, description="Zone context or notes"
    )


class Zone(ZoneBase, table=True):
    __tablename__ = "zone"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    greenhouse_id: uuid.UUID = Field(
        sa_column=Column(
            "greenhouse_id",
            ForeignKey("greenhouse.id", ondelete="CASCADE"),
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


class ZoneCreate(ZoneBase):
    greenhouse_id: uuid.UUID


class ZonePublic(ZoneBase):
    id: uuid.UUID
    greenhouse_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ZoneUpdate(SQLModel):
    zone_number: int | None = None
    location: LocationEnum | None = None
    context_text: str | None = Field(default=None, max_length=2000)


class ZoneRead(ZoneBase):
    id: uuid.UUID
    greenhouse_id: uuid.UUID
    # Remove created_at since it doesn't exist in DB yet
    # created_at: datetime


class ZoneReading(SQLModel, table=True):
    """Placeholder for zone sensor readings."""

    __tablename__ = "zone_reading"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    zone_id: uuid.UUID = Field(
        sa_column=Column(
            "zone_id",
            ForeignKey("zone.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    reading_data: dict[str, Any] = Field(sa_type=JSON)


class ZoneSensorMap(SQLModel):
    """Mapping between zones and sensors for readings."""

    zone_id: uuid.UUID
    sensor_ids: list[uuid.UUID]


# ===============================================
# PAGINATED TYPES
# ===============================================
GreenhousesPaginated = Paginated[GreenhousePublicAPI]  # Use API-compliant DTO
ZonesPaginated = Paginated[ZonePublic]
