"""Greenhouse and Zone models for Verdify API."""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from pydantic import EmailStr, field_validator
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel

from app.utils_paging import Paginated

from .enums import GreenhouseRole, InviteStatus, LocationEnum

# Direct imports for forward reference resolution - these are available since
# greenhouses module is imported after users and crops in __init__.py dependency order

if TYPE_CHECKING:
    pass


# -------------------------------------------------------
# GREENHOUSE MODELS
# -------------------------------------------------------
class GreenhouseBase(SQLModel):
    title: str = Field(
        min_length=1,
        max_length=255,
    )  # API field 'title' maps to DB column 'title'
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


class ZonePublic(SQLModel):
    """Zone public response - matches database schema."""

    id: uuid.UUID
    greenhouse_id: uuid.UUID
    zone_number: int = Field(..., description="Numeric identifier within greenhouse")
    location: LocationEnum = Field(..., description="N, E, S, W, NE, SE, SW, NW")
    context_text: str | None = Field(
        default=None, max_length=2000, description="Zone context or notes"
    )


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


# -------------------------------------------------------
# GREENHOUSE RBAC MODELS
# -------------------------------------------------------
class GreenhouseMember(SQLModel, table=True):
    """Table for greenhouse role-based access control."""

    __tablename__ = "greenhouse_member"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    greenhouse_id: uuid.UUID = Field(
        sa_column=Column(
            "greenhouse_id",
            ForeignKey("greenhouse.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    user_id: uuid.UUID = Field(
        sa_column=Column(
            "user_id",
            ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    role: GreenhouseRole = Field(
        sa_column=Column(SAEnum(GreenhouseRole, name="greenhouserole"), nullable=False),
        description="User role in the greenhouse",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("greenhouse_id", "user_id", name="uq_greenhouse_member"),
    )


class GreenhouseInvite(SQLModel, table=True):
    """Table for greenhouse access invitations."""

    __tablename__ = "greenhouse_invite"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    greenhouse_id: uuid.UUID = Field(
        sa_column=Column(
            "greenhouse_id",
            ForeignKey("greenhouse.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    email: EmailStr = Field(max_length=255, description="Email address of invited user")
    role: GreenhouseRole = Field(
        sa_column=Column(SAEnum(GreenhouseRole, name="greenhouserole"), nullable=False),
        description="Role being offered to the invited user",
    )
    token: str = Field(
        max_length=255, unique=True, description="Unique invitation token"
    )
    expires_at: datetime = Field(description="When the invitation expires")
    invited_by_user_id: uuid.UUID | None = Field(
        sa_column=Column(
            "invited_by_user_id",
            ForeignKey("app_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        description="User who sent the invitation",
    )
    status: InviteStatus = Field(
        sa_column=Column(SAEnum(InviteStatus, name="invitestatus"), nullable=False),
        default=InviteStatus.PENDING,
        description="Current status of the invitation",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Note: Uniqueness is enforced by partial unique index for pending invites only
    # See Alembic migration 28bf57b69a7f for the index definition


# DTO Models for RBAC
class GreenhouseMemberUser(SQLModel):
    """User info for greenhouse member - avoids forward reference issues."""

    id: uuid.UUID
    email: str
    full_name: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class GreenhouseMemberPublic(SQLModel):
    """Public representation of greenhouse member."""

    user: GreenhouseMemberUser
    role: GreenhouseRole
    added_at: datetime = Field(alias="created_at")

    class Config:
        from_attributes = True


class GreenhouseInvitePublic(SQLModel):
    """Public representation of greenhouse invite."""

    id: uuid.UUID
    greenhouse_id: uuid.UUID
    email: EmailStr
    role: GreenhouseRole
    status: InviteStatus
    expires_at: datetime
    created_at: datetime


class GreenhouseMemberCreate(SQLModel):
    """Request to add a member to greenhouse."""

    email: EmailStr = Field(max_length=255)
    role: GreenhouseRole = Field(
        description="Role to assign (owner role not allowed via API)"
    )

    @field_validator("role")
    @classmethod
    def validate_role_not_owner(cls, v):
        if v == GreenhouseRole.OWNER:
            raise ValueError("Cannot assign owner role via API")
        return v


class GreenhouseInviteAccept(SQLModel):
    """Request to accept a greenhouse invitation."""

    pass  # No additional fields needed


# ===============================================
# PAGINATED TYPES
# ===============================================
GreenhousesPaginated = Paginated[GreenhousePublicAPI]  # Use API-compliant DTO
ZonesPaginated = Paginated[ZonePublic]
