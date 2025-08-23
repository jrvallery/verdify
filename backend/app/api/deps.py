from collections.abc import Generator
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session
from sqlalchemy import text

from app.core import security
from app.core.config import settings
from app.core.db import engine
from app.models import Controller, TokenPayload, User
from app.utils_paging import PaginationParams, create_pagination_dependency

reusable_oauth2 = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    user = session.get(User, token_data.sub)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    # Set session variable for RLS policies
    try:
        session.exec(text("SET LOCAL app.current_user_id = :uid").bindparams(uid=str(user.id)))
    except Exception:
        # Non-fatal in environments without the helper function/policy yet
        pass
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user


# Pagination dependency
PaginationDep = Annotated[PaginationParams, Depends(create_pagination_dependency())]


def get_current_device(
    session: Annotated[Session, Depends(get_db)],
    x_device_token: Annotated[str | None, Header(alias="X-Device-Token")] = None,
) -> Controller:
    """Extract and validate device token, return associated controller.

    This dependency validates the X-Device-Token header and returns the
    associated controller for device-authenticated endpoints.

    Args:
        session: Database session
        x_device_token: Device token from X-Device-Token header

    Returns:
        Controller instance associated with the valid token

    Raises:
        HTTPException: 401 if token missing/invalid, 404 if controller not found
    """
    if not x_device_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Device-Token header required",
            headers={"WWW-Authenticate": "X-Device-Token"},
        )

    # Hash the provided token and look up controller
    from datetime import datetime, timezone

    from sqlmodel import select

    from app.core.security import create_device_token_hash

    token_hash = create_device_token_hash(x_device_token)

    # Find controller by device token hash
    controller = session.exec(
        select(Controller).where(Controller.device_token_hash == token_hash)
    ).first()

    if not controller:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid device token",
            headers={"WWW-Authenticate": "X-Device-Token"},
        )

    # Check token expiry
    current_time = datetime.now(timezone.utc)
    if controller.token_expires_at:
        # Ensure both datetimes are timezone-aware for comparison
        token_expires_at = controller.token_expires_at
        if token_expires_at.tzinfo is None:
            # If stored datetime is naive, assume it's UTC
            token_expires_at = token_expires_at.replace(tzinfo=timezone.utc)

        if token_expires_at < current_time:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Device token expired",
                headers={"WWW-Authenticate": "X-Device-Token"},
            )

    # Set session variable for RLS policies (controller scope)
    try:
        session.exec(
            text("SET LOCAL app.current_controller_id = :cid").bindparams(
                cid=str(controller.id)
            )
        )
    except Exception:
        # Non-fatal if DB helper not present yet
        pass

    # Update last_seen timestamp
    controller.last_seen = current_time
    session.add(controller)
    session.commit()

    return controller


CurrentDevice = Annotated[Controller, Depends(get_current_device)]


# RBAC Permission Dependencies
def require_owner(greenhouse_id: str):
    """Dependency factory that requires owner permission for a greenhouse."""

    def _require_owner(
        session: Annotated[Session, Depends(get_db)],
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> None:
        """Check if current user is owner of the greenhouse."""
        import uuid

        from app.api.permissions import require_owner_permission

        try:
            greenhouse_uuid = uuid.UUID(greenhouse_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid greenhouse ID format",
            )

        require_owner_permission(session, greenhouse_uuid, current_user.id)

    return _require_owner


def require_access(greenhouse_id: str):
    """Dependency factory that requires access permission (owner or operator) for a greenhouse."""

    def _require_access(
        session: Annotated[Session, Depends(get_db)],
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> None:
        """Check if current user has access to the greenhouse."""
        import uuid

        from app.api.permissions import require_access_permission

        try:
            greenhouse_uuid = uuid.UUID(greenhouse_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid greenhouse ID format",
            )

        require_access_permission(session, greenhouse_uuid, current_user.id)

    return _require_access
