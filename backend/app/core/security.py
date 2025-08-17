import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


ALGORITHM = "HS256"


def create_access_token(subject: str | Any, expires_delta: timedelta) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_device_token_hash(token: str) -> str:
    """Create HMAC-SHA256 hash of device token for secure storage.

    Args:
        token: Raw device token string

    Returns:
        Base64-encoded HMAC-SHA256 hash of the token
    """
    # Use HMAC with server secret key for secure token hashing
    token_bytes = token.encode("utf-8")
    secret_bytes = settings.SECRET_KEY.encode("utf-8")
    hash_obj = hmac.new(secret_bytes, token_bytes, hashlib.sha256)
    return hash_obj.hexdigest()


def verify_device_token(token: str, token_hash: str) -> bool:
    """Verify a device token against its stored hash.

    Args:
        token: Raw device token to verify
        token_hash: Stored hash to compare against

    Returns:
        True if token matches the hash, False otherwise
    """
    computed_hash = create_device_token_hash(token)
    return hmac.compare_digest(computed_hash, token_hash)


def generate_csrf_token() -> str:
    """Generate a secure random CSRF token.

    Returns:
        URL-safe random string suitable for CSRF protection
    """
    return secrets.token_urlsafe(32)


def generate_device_token() -> str:
    """Generate a secure device token.

    Returns:
        URL-safe random string for device authentication
    """
    return secrets.token_urlsafe(64)


def generate_claim_code() -> str:
    """Generate a 6-digit claim code.

    Returns:
        6-digit numeric string
    """
    return f"{secrets.randbelow(1000000):06d}"
