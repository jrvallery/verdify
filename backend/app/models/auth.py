"""Authentication and messaging models for token handling."""

import re
import uuid
from datetime import datetime

from pydantic import field_validator
from sqlmodel import Field, SQLModel


# -------------------------------------------------------
# AUTHENTICATION MODELS
# -------------------------------------------------------
class Token(SQLModel):
    """JSON payload containing access token."""

    access_token: str
    token_type: str = "bearer"


class TokenPayload(SQLModel):
    """Contents of JWT token."""

    sub: str | None = None


class NewPassword(SQLModel):
    """Password reset model."""

    token: str
    new_password: str


class UserRegisterResponseUser(SQLModel):
    """Minimal user info for registration response."""

    id: uuid.UUID
    email: str
    full_name: str | None
    created_at: datetime


class UserRegisterResponse(SQLModel):
    """Response after successful user registration."""

    user: UserRegisterResponseUser
    access_token: str


# -------------------------------------------------------
# DEVICE TOKEN EXCHANGE MODELS
# -------------------------------------------------------
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


# -------------------------------------------------------
# MISC MODELS
# -------------------------------------------------------
class Message(SQLModel):
    """Generic message response."""

    message: str
