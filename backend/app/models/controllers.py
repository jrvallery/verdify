"""
Controller and related models for Verdify API.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import field_validator
from sqlalchemy import Column, ForeignKey, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.utils_paging import Paginated

from .enums import ControllerStatus

# TYPE_CHECKING imports only - no runtime circular imports
if TYPE_CHECKING:
    pass


# -------------------------------------------------------
# CONTROLLER MODELS
# -------------------------------------------------------
class ControllerBase(SQLModel):
    device_name: str = Field(..., description="Controller device name (verdify-XXXXXX)")
    is_climate_controller: bool = Field(default=False)
    label: str | None = Field(default=None, description="Optional human-readable label")
    model: str | None = Field(default=None, description="Controller model/hardware")
    fw_version: str | None = None
    hw_version: str | None = None
    hardware_profile: str | None = Field(
        default=None, description="Hardware profile identifier"
    )
    last_seen: datetime | None = Field(
        default=None, description="Last communication timestamp"
    )

    @field_validator("device_name")
    @classmethod
    def validate_device_name(cls, v: str) -> str:
        if not re.match(r"^verdify-[0-9a-f]{6}$", v):
            raise ValueError(
                "device_name must match pattern 'verdify-XXXXXX' where X is a lowercase hex digit"
            )
        return v


class Controller(ControllerBase, table=True):
    __tablename__ = "controller"
    __table_args__ = (
        UniqueConstraint("device_name", name="uq_controller_device_name"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    greenhouse_id: uuid.UUID | None = (
        Field(  # Nullable to support unclaimed controllers
            default=None,
            sa_column=Column(
                "greenhouse_id",
                ForeignKey("greenhouse.id", ondelete="CASCADE"),
                nullable=True,  # Allow unclaimed controllers in DB
            ),
        )
    )

    # Onboarding and device authentication fields
    first_seen: datetime | None = Field(
        default=None, description="First announcement timestamp"
    )
    claim_code: str | None = Field(default=None, description="6-digit claim code")
    claim_code_expires_at: datetime | None = Field(
        default=None, description="Claim code expiry"
    )
    device_token_hash: str | None = Field(
        default=None, description="Hashed device token"
    )
    token_expires_at: datetime | None = Field(
        default=None, description="Device token expiry"
    )
    token_exchange_completed: bool = Field(
        default=False, description="Token exchange completed"
    )
    claimed_at: datetime | None = Field(default=None, description="Claim timestamp")
    claimed_by: uuid.UUID | None = Field(
        default=None, description="User who claimed this controller"
    )

    # 🚫 No Relationship() here - use explicit foreign keys and manual queries


class ControllerCreate(ControllerBase):
    greenhouse_id: uuid.UUID


class ControllerPublic(ControllerBase):
    id: uuid.UUID
    greenhouse_id: uuid.UUID  # Non-nullable per spec - only claimed controllers exposed
    last_seen: datetime | None = None


class ControllerUpdate(SQLModel):
    label: str | None = None
    model: str | None = None
    is_climate_controller: bool | None = None
    fw_version: str | None = None
    hw_version: str | None = None
    last_seen: datetime | None = None


# -------------------------------------------------------
# ONBOARDING DTOs
# -------------------------------------------------------
class HelloRequest(SQLModel):
    device_name: str = Field(...)
    claim_code: str = Field(...)
    hardware_profile: str
    firmware: str
    ts_utc: datetime

    @field_validator("device_name")
    @classmethod
    def validate_device_name(cls, v: str) -> str:
        if not re.match(r"^verdify-[0-9a-f]{6}$", v):
            raise ValueError(
                "device_name must match pattern 'verdify-XXXXXX' where X is a lowercase hex digit"
            )
        return v

    @field_validator("claim_code")
    @classmethod
    def validate_claim_code(cls, v: str) -> str:
        if not re.match(r"^\d{6}$", v):
            raise ValueError("claim_code must be exactly 6 digits")
        return v

    @field_validator("ts_utc")
    @classmethod
    def validate_ts_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("ts_utc must be timezone-aware (include timezone info)")
        return v


class HelloResponse(SQLModel):
    status: ControllerStatus = Field(..., description="Controller hello status")
    controller_uuid: uuid.UUID | None = None
    greenhouse_id: uuid.UUID | None = None
    retry_after_s: int | None = Field(default=None, ge=1)
    message: str | None = None


class ControllerClaimRequest(SQLModel):
    device_name: str = Field(...)
    claim_code: str = Field(...)
    greenhouse_id: uuid.UUID

    @field_validator("device_name")
    @classmethod
    def validate_device_name(cls, v: str) -> str:
        if not re.match(r"^verdify-[0-9a-f]{6}$", v):
            raise ValueError(
                "device_name must match pattern 'verdify-XXXXXX' where X is a lowercase hex digit"
            )
        return v

    @field_validator("claim_code")
    @classmethod
    def validate_claim_code(cls, v: str) -> str:
        if not re.match(r"^\d{6}$", v):
            raise ValueError("claim_code must be exactly 6 digits")
        return v


class ControllerClaimResponse(SQLModel):
    controller: ControllerPublic
    device_token: str
    expires_at: datetime


# TokenExchange models moved to auth.py to avoid duplication


# ===============================================
# PAGINATED TYPES
# ===============================================
ControllersPaginated = Paginated[ControllerPublic]
