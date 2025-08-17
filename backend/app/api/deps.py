from collections.abc import Generator
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session

from app.core import security
from app.core.config import settings
from app.core.db import engine
from app.models import Controller, TokenPayload, User
from app.utils_paging import PaginationParams, create_pagination_dependency

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)


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

    # For now, implement basic token verification
    # In a full implementation, this would:
    # 1. Hash the provided token using security.create_device_token_hash()
    # 2. Query controller_token table for matching hash
    # 3. Check expiry and revocation status
    # 4. Return associated controller

    # Simplified implementation: treat token as controller ID for now
    # This allows testing the endpoint structure before full token table implementation
    try:
        # Parse token as UUID (temporary implementation)
        import uuid

        controller_id = uuid.UUID(x_device_token)

        # Look up controller by ID
        controller = session.get(Controller, controller_id)
        if not controller:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Controller not found",
            )

        return controller

    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid device token format",
            headers={"WWW-Authenticate": "X-Device-Token"},
        )


CurrentDevice = Annotated[Controller, Depends(get_current_device)]
