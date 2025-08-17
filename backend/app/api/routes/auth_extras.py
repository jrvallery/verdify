from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.api.deps import SessionDep
from app.core import security
from app.crud.auth import authenticate, create_user_crud, get_user_by_email
from app.models import Token, UserPublic, UserRegister

router = APIRouter()


class CSRFTokenResponse(BaseModel):
    """Response model for CSRF token endpoint."""

    csrf_token: str
    expires_at: datetime


@router.get(
    "/csrf",
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
    response_model=Token,
    summary="Login and obtain JWT",
    description="Authenticate with email/password and receive JWT token",
)
def login_user(
    session: SessionDep, form_data: OAuth2PasswordRequestForm = Depends()
) -> Token:
    """Login with email and password to get JWT token.

    Args:
        session: Database session
        form_data: OAuth2 form containing username/password

    Returns:
        Token: JWT access token and metadata

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

    access_token_expires = timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        user.id, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")
