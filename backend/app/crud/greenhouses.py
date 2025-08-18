import uuid

from sqlmodel import Session, and_, select

from app.models import (
    Greenhouse,
    GreenhouseCreate,
    GreenhouseUpdate,
    User,
)


def get_greenhouse(*, session: Session, id: uuid.UUID) -> Greenhouse | None:
    return session.get(Greenhouse, id)


def validate_user_owns_greenhouse(
    session: Session, greenhouse_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Validate that a user owns the greenhouse."""
    result = session.exec(
        select(Greenhouse).where(
            and_(Greenhouse.id == greenhouse_id, Greenhouse.user_id == user_id)
        )
    ).first()
    return result is not None


def assert_user_owns_greenhouse(
    session: Session, greenhouse_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    """Assert that a user owns the greenhouse, raise ValueError if not."""
    if not validate_user_owns_greenhouse(session, greenhouse_id, user_id):
        raise ValueError(f"User {user_id} does not own greenhouse {greenhouse_id}")


def validate_user_can_access_greenhouse(
    session: Session, greenhouse_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Validate that a user can access the greenhouse (owner or operator)."""
    from app.api.permissions import user_can_access_greenhouse

    return user_can_access_greenhouse(session, greenhouse_id, user_id)


def get_user_greenhouses(
    *, session: Session, user: User, skip: int = 0, limit: int = 100
) -> list[Greenhouse]:
    q = (
        select(Greenhouse)
        .where(Greenhouse.user_id == user.id)
        .offset(skip)
        .limit(limit)
    )
    return session.exec(q).all()


def create_greenhouse(
    *, session: Session, greenhouse_create: GreenhouseCreate, owner_id: uuid.UUID
) -> Greenhouse:
    gh = Greenhouse.model_validate(greenhouse_create, update={"user_id": owner_id})
    session.add(gh)
    session.commit()
    session.refresh(gh)
    return gh


def update_greenhouse(
    session: Session, gh: Greenhouse, data: GreenhouseUpdate
) -> Greenhouse:
    """Update greenhouse data."""
    greenhouse_data = data.model_dump(exclude_unset=True)
    for field, value in greenhouse_data.items():
        setattr(gh, field, value)
    session.add(gh)
    session.commit()
    session.refresh(gh)
    return gh


def delete_greenhouse(*, session: Session, db_gh: Greenhouse) -> None:
    """Delete a greenhouse."""
    session.delete(db_gh)
    session.commit()


def get_greenhouse_members(session: Session, greenhouse_id: uuid.UUID) -> list:
    """Get greenhouse members - placeholder."""
    return []


def create_greenhouse_member(session: Session, **kwargs) -> None:
    """Create greenhouse member - placeholder."""
    pass


def remove_greenhouse_member(session: Session, **kwargs) -> None:
    """Remove greenhouse member - placeholder."""
    pass


# Alias for backward compatibility
crud_remove_greenhouse_member = remove_greenhouse_member


def create_greenhouse_invite(session: Session, **kwargs) -> None:
    """Create greenhouse invite - placeholder."""
    pass


def get_user_pending_invites(session: Session, user_id: uuid.UUID) -> list:
    """Get user pending invites - placeholder."""
    return []


def get_invite_by_token(session: Session, token: str) -> None:
    """Get invite by token - placeholder."""
    return None


def accept_greenhouse_invite(session: Session, **kwargs) -> None:
    """Accept greenhouse invite - placeholder."""
    pass


def revoke_greenhouse_invite(session: Session, **kwargs) -> None:
    """Revoke greenhouse invite - placeholder."""
    pass


# Note: update_greenhouse and delete_greenhouse functions are already defined above
