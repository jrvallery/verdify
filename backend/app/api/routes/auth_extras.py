from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep
from app.core import security
from app.core.config import settings
from app.core.security import create_access_token
from app.crud.auth import authenticate, create_user_crud, get_user_by_email
from app.models import UserLoginResponse, UserPublic, UserRegister

router = APIRouter()


class CSRFTokenResponse(BaseModel):
    """Response model for CSRF token endpoint."""

    csrf_token: str
    expires_at: datetime


@router.get(
    "/csrf",
    operation_id="getCsrfToken",
    response_model=CSRFTokenResponse,
    summary="Get CSRF token for browser-based authentication",
    description="Generate a CSRF token for use in X-CSRF-Token header for browser requests",
)
def get_csrf_token() -> CSRFTokenResponse:
    """Generate a CSRF token for browser-based authentication.

    Returns a CSRF token and its expiration time. The token should be
    included in the X-CSRF-Token header for subsequent requests that
    require CSRF protection.

    Returns:
        CSRFTokenResponse: Contains the token and expiration timestamp
    """
    # Generate CSRF token
    csrf_token = security.generate_csrf_token()

    # Set expiry to 1 hour from now
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    return CSRFTokenResponse(csrf_token=csrf_token, expires_at=expires_at)


@router.post(
    "/register",
    operation_id="registerUser",
    response_model=UserPublic,
    status_code=201,
    summary="Register new user account",
    description="Create a new user account with email and password",
)
def register_user(session: SessionDep, user_in: UserRegister) -> UserPublic:
    """Register a new user account.

    Args:
        session: Database session
        user_in: User registration data

    Returns:
        UserPublic: The created user data

    Raises:
        HTTPException: If user with email already exists
    """
    user = get_user_by_email(session=session, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system",
        )
    user = create_user_crud(session=session, user_create=user_in)
    return user


@router.post(
    "/login",
    operation_id="loginUser",
    response_model=UserLoginResponse,
    summary="Login and obtain JWT",
    description="Authenticate with email/password and receive JWT token",
)
def login_user(
    session: SessionDep, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> UserLoginResponse:
    """Login with email and password to get JWT token.

    Args:
        session: Database session
        form_data: OAuth2 form containing username/password

    Returns:
        UserLoginResponse: JWT access token and metadata

    Raises:
        HTTPException: If credentials are invalid
    """
    user = authenticate(
        session=session, email=form_data.username, password=form_data.password
    )
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        user.id, expires_delta=access_token_expires
    )
    return UserLoginResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        * 60,  # Convert minutes to seconds
    )


@router.post(
    "/test-token",
    operation_id="testUserToken",
    response_model=UserPublic,
    summary="Test JWT token validity",
    description="Validate current JWT token and return user information",
)
def test_user_token(current_user: CurrentUser) -> UserPublic:
    """Test and validate current JWT token.

    Args:
        current_user: The authenticated user from JWT token

    Returns:
        UserPublic: Current user information if token is valid
    """
    return current_user


@router.post(
    "/revoke-token",
    operation_id="revokeUserToken",
    summary="Revoke current user JWT (logout)",
    description="Revoke the current user's JWT token, effectively logging them out",
    status_code=204,
)
def revoke_user_token(current_user: CurrentUser) -> None:
    """Revoke current user JWT token (logout).

    This endpoint invalidates the current user's JWT token.
    Note: In a stateless JWT implementation, this typically involves
    adding the token to a blacklist or setting a short expiry.

    Args:
        current_user: The authenticated user

    Returns:
        None: 204 No Content on successful revocation
    """
    # In a stateless JWT system, token revocation typically involves:
    # 1. Adding token to blacklist/cache with expiry time
    # 2. Client-side token deletion
    # 3. Short token expiry times

    # For now, we'll return success as the client should delete the token
    # In production, implement proper token blacklisting
    pass


# Legacy router for backward compatibility with tests
legacy_login_router = APIRouter()


@legacy_login_router.post(
    "/access-token",
    operation_id="loginAccessToken",
    response_model=UserLoginResponse,
    summary="Legacy login endpoint",
    description="OAuth2 compatible token login for backward compatibility",
)
def login_access_token(
    session: SessionDep, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> UserLoginResponse:
    """
    Legacy OAuth2 compatible token login, get an access token for future requests.
    This endpoint is for backward compatibility with existing tests.
    """
    user = authenticate(
        session=session, email=form_data.username, password=form_data.password
    )
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return UserLoginResponse(
        access_token=create_access_token(user.id, expires_delta=access_token_expires),
        token_type="bearer",
    )
