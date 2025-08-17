"""
CRUD operations for idempotency key management.

Handles idempotency key creation, lookup, and expiration for telemetry endpoints.
Ensures exactly-once processing of telemetry data with proper deduplication.
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, delete, select

from app.models import IdempotencyKey


def create_idempotency_key(
    session: Session,
    *,
    key: str,
    controller_id: uuid.UUID,
    body_hash: str,
    response_status: int,
    response_body: str | None = None,
    expires_in_hours: int = 24,
) -> IdempotencyKey:
    """
    Create a new idempotency key record.

    Args:
        session: Database session
        key: Idempotency key string
        controller_id: Controller that submitted the request
        body_hash: Hash of the request body
        response_status: HTTP status code of the response
        response_body: Optional response body (for replay)
        expires_in_hours: Expiration time in hours

    Returns:
        Created IdempotencyKey instance

    Raises:
        IntegrityError: If key already exists for this controller
    """
    expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)

    idempotency_obj = IdempotencyKey(
        key=key,
        controller_id=controller_id,
        body_hash=body_hash,
        response_status=response_status,
        response_body=response_body,
        expires_at=expires_at,
    )

    session.add(idempotency_obj)
    session.commit()
    session.refresh(idempotency_obj)

    return idempotency_obj


def get_idempotency_key(
    session: Session, *, key: str, controller_id: uuid.UUID
) -> IdempotencyKey | None:
    """
    Get idempotency key by key and controller ID.

    Args:
        session: Database session
        key: Idempotency key string
        controller_id: Controller ID

    Returns:
        IdempotencyKey instance if found and not expired, None otherwise
    """
    statement = select(IdempotencyKey).where(
        IdempotencyKey.key == key,
        IdempotencyKey.controller_id == controller_id,
        IdempotencyKey.expires_at > datetime.now(timezone.utc),
    )

    return session.exec(statement).first()


def check_idempotency(
    session: Session, *, key: str, controller_id: uuid.UUID, body_hash: str
) -> dict[str, Any] | None:
    """
    Check if request is idempotent (already processed).

    Args:
        session: Database session
        key: Idempotency key string
        controller_id: Controller ID
        body_hash: Hash of current request body

    Returns:
        Dict with response info if request already processed, None if new request
        Dict contains: {"status": int, "body": str|None}
    """
    existing = get_idempotency_key(session, key=key, controller_id=controller_id)

    if not existing:
        return None

    # Verify body hash matches (detect replay attacks or body tampering)
    if existing.body_hash != body_hash:
        # This is suspicious - same key with different body
        # For now, treat as new request but log the incident
        print(
            f"WARNING: Idempotency key reused with different body hash. "
            f"Key: {key}, Controller: {controller_id}"
        )
        return None

    # Return the stored response for replay
    return {"status": existing.response_status, "body": existing.response_body}


def cleanup_expired_keys(session: Session) -> int:
    """
    Remove expired idempotency keys.

    Args:
        session: Database session

    Returns:
        Number of keys removed
    """
    cutoff = datetime.now(timezone.utc)

    statement = delete(IdempotencyKey).where(IdempotencyKey.expires_at <= cutoff)

    result = session.exec(statement)
    session.commit()

    return result.rowcount  # type: ignore


def hash_request_body(body: bytes) -> str:
    """
    Create a hash of the request body for idempotency checking.

    Args:
        body: Raw request body bytes

    Returns:
        SHA-256 hash of the body as hex string
    """
    return hashlib.sha256(body).hexdigest()


def store_idempotent_response(
    session: Session,
    *,
    key: str,
    controller_id: uuid.UUID,
    body_hash: str,
    response_status: int,
    response_body: str | None = None,
) -> IdempotencyKey:
    """
    Store response for idempotent replay.

    Args:
        session: Database session
        key: Idempotency key string
        controller_id: Controller ID
        body_hash: Hash of request body
        response_status: HTTP status code
        response_body: Response body for replay

    Returns:
        Created IdempotencyKey instance
    """
    # First check if key already exists (in case unique constraint isn't in DB yet)
    existing = get_idempotency_key(session, key=key, controller_id=controller_id)
    if existing:
        return existing

    try:
        return create_idempotency_key(
            session,
            key=key,
            controller_id=controller_id,
            body_hash=body_hash,
            response_status=response_status,
            response_body=response_body,
        )
    except IntegrityError:
        # Key already exists, this is a race condition
        # Roll back and return the existing key
        session.rollback()
        existing = get_idempotency_key(session, key=key, controller_id=controller_id)
        if existing:
            return existing
        raise
