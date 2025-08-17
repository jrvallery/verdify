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

    # 🚫 No Relationship() here - use explicit foreign keys and manual queries


class ControllerCreate(ControllerBase):
    greenhouse_id: uuid.UUID


class ControllerPublic(ControllerBase):
    id: uuid.UUID
    greenhouse_id: uuid.UUID  # Non-nullable per spec - only claimed controllers exposed
    last_seen: datetime | None = None


class ControllerUpdate(SQLModel):
    device_name: str | None = Field(default=None)
    label: str | None = None
    model: str | None = None
    is_climate_controller: bool | None = None
    fw_version: str | None = None
    hw_version: str | None = None
    last_seen: datetime | None = None

    @field_validator("device_name")
    @classmethod
    def validate_device_name(cls, v: str | None) -> str | None:
        if v is not None and not re.match(r"^verdify-[0-9a-f]{6}$", v):
            raise ValueError(
                "device_name must match pattern 'verdify-XXXXXX' where X is a lowercase hex digit"
            )
        return v


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


class HelloResponse(SQLModel):
    status: str = Field(..., description="pending or claimed")
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


class TokenExchangeRequest(SQLModel):
    device_name: str = Field(...)
    claim_code: str = Field(...)

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


class TokenExchangeResponse(SQLModel):
    device_token: str
    config_etag: str = Field(...)
    plan_etag: str = Field(...)
    expires_at: datetime

    @field_validator("config_etag")
    @classmethod
    def validate_config_etag(cls, v: str) -> str:
        if not re.match(r"^config:v[0-9]+:[0-9a-f]{8}$", v):
            raise ValueError("config_etag must match pattern 'config:vN:XXXXXXXX'")
        return v

    @field_validator("plan_etag")
    @classmethod
    def validate_plan_etag(cls, v: str) -> str:
        if not re.match(r"^plan:v[0-9]+:[0-9a-f]{8}$", v):
            raise ValueError("plan_etag must match pattern 'plan:vN:XXXXXXXX'")
        return v


class TokenRotateResponse(SQLModel):
    device_token: str
    expires_at: datetime


# Combined model for simpler imports
class TokenExchange(SQLModel):
    device_name: str
    claim_code: str
    device_token: str | None = None


# ===============================================
# PAGINATED TYPES
# ===============================================
ControllersPaginated = Paginated[ControllerPublic]
