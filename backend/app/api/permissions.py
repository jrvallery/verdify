"""
RBAC permission utilities for greenhouse access control.

This module provides centralized permission checking functions to ensure
consistent access control across the API.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import and_, exists, or_, select
from sqlmodel import Session

if TYPE_CHECKING:
    pass

from app.models.enums import GreenhouseRole


def user_is_owner(
    session: Session, greenhouse_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Check if user is the owner of the greenhouse."""
    from app.models import Greenhouse

    stmt = select(Greenhouse.id).where(
        and_(Greenhouse.id == greenhouse_id, Greenhouse.user_id == user_id)
    )
    result = session.exec(stmt).first()
    return result is not None


def user_is_member(
    session: Session,
    greenhouse_id: uuid.UUID,
    user_id: uuid.UUID,
    allowed_roles: tuple[GreenhouseRole, ...] = (
        GreenhouseRole.OWNER,
        GreenhouseRole.OPERATOR,
    ),
) -> bool:
    """Check if user has membership in the greenhouse with allowed roles."""
    from app.models import GreenhouseMember

    stmt = select(GreenhouseMember.id).where(
        and_(
            GreenhouseMember.greenhouse_id == greenhouse_id,
            GreenhouseMember.user_id == user_id,
            GreenhouseMember.role.in_(allowed_roles),
        )
    )
    result = session.exec(stmt).first()
    return result is not None


def user_can_access_greenhouse(
    session: Session, greenhouse_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Check if user can access greenhouse (owner OR operator)."""
    return user_is_owner(session, greenhouse_id, user_id) or user_is_member(
        session, greenhouse_id, user_id, (GreenhouseRole.OPERATOR,)
    )


def accessible_greenhouse_ids(session: Session, user_id: uuid.UUID) -> list[uuid.UUID]:
    """Get list of greenhouse IDs that user can access (owned + shared)."""
    from app.models import Greenhouse, GreenhouseMember

    # Get owned greenhouses
    owned_stmt = select(Greenhouse.id).where(Greenhouse.user_id == user_id)
    owned_ids = session.exec(owned_stmt).all()

    # Get shared greenhouses
    shared_stmt = select(GreenhouseMember.greenhouse_id).where(
        GreenhouseMember.user_id == user_id
    )
    shared_ids = session.exec(shared_stmt).all()

    # Combine and deduplicate
    all_ids = list(set(owned_ids + shared_ids))
    return all_ids


def ownership_or_membership_condition(user_id: uuid.UUID):
    """
    SQLAlchemy condition for filtering greenhouses by ownership OR membership.

    Use this in queries to replace simple ownership checks:

    Replace:
        .where(Greenhouse.user_id == user_id)

    With:
        .where(ownership_or_membership_condition(user_id))
    """
    from app.models import Greenhouse, GreenhouseMember

    return or_(
        Greenhouse.user_id == user_id,
        exists(
            select(GreenhouseMember.id).where(
                and_(
                    GreenhouseMember.greenhouse_id == Greenhouse.id,
                    GreenhouseMember.user_id == user_id,
                )
            )
        ),
    )


# Convenience functions for common permission patterns
def require_owner_permission(
    session: Session, greenhouse_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """Raise 403 if user is not the owner of the greenhouse."""
    from fastapi import HTTPException, status

    if not user_is_owner(session, greenhouse_id, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only greenhouse owners can perform this action",
        )


def require_access_permission(
    session: Session, greenhouse_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """Raise 403 if user cannot access the greenhouse (owner or operator)."""
    from fastapi import HTTPException, status

    if not user_can_access_greenhouse(session, greenhouse_id, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this greenhouse",
        )
