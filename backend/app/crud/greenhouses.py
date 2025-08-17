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
    gh_data = data.model_dump(exclude_unset=True)
    for key, val in gh_data.items():
        setattr(gh, key, val)
    session.add(gh)
    session.commit()
    session.refresh(gh)
    return gh


def delete_greenhouse(*, session: Session, db_gh: Greenhouse) -> None:
    # cascade delete of links happens automatically (link table FKs)
    session.delete(db_gh)
    session.commit()
