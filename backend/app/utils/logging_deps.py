"""
Enhanced dependencies for Project Verdify API with logging context.

Extends the base dependencies to set user/device context for structured logging.
"""

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlmodel import Session

from app.api.deps import SessionDep, TokenDep, get_db
from app.api.deps import get_current_device as _get_current_device
from app.api.deps import get_current_user as _get_current_user
from app.models import Controller, User
from app.utils.log import set_device_context, set_request_context, set_user_context


def get_current_user_with_logging(
    request: Request, session: SessionDep, token: TokenDep
) -> User:
    """
    Get current user and set logging context.

    Args:
        request: FastAPI request object
        session: Database session
        token: JWT token

    Returns:
        Authenticated user
    """
    # Set request context for logging
    set_request_context(request)

    # Get user using existing dependency
    user = _get_current_user(session, token)

    # Set user context for logging
    set_user_context(user)

    # Store user in request state for middleware access
    request.state.current_user = user

    return user


def get_current_device_with_logging(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    x_device_token: Annotated[str | None, Header(alias="X-Device-Token")] = None,
) -> Controller:
    """
    Get current device/controller and set logging context.

    Args:
        request: FastAPI request object
        session: Database session
        x_device_token: Device token from header

    Returns:
        Authenticated controller
    """
    # Set request context for logging
    set_request_context(request)

    # Get device using existing dependency
    device = _get_current_device(session, x_device_token)

    # Set device context for logging
    set_device_context(device)

    # Store device in request state for middleware access
    request.state.current_device = device

    return device


# Enhanced dependency annotations with logging
CurrentUserWithLogging = Annotated[User, Depends(get_current_user_with_logging)]
CurrentDeviceWithLogging = Annotated[
    Controller, Depends(get_current_device_with_logging)
]
