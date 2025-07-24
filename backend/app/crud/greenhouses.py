import uuid
from typing import Any, List, Optional

from sqlmodel import Session, select
from app.models import (
    Greenhouse,
    GreenhouseCreate,
    GreenhouseUpdate,
    User,
)


def get_greenhouse(*, session: Session, id: uuid.UUID) -> Optional[Greenhouse]:
    return session.get(Greenhouse, id)


def get_user_greenhouses(*, session: Session, user: User, skip: int = 0, limit: int = 100) -> List[Greenhouse]:
    q = select(Greenhouse).where(Greenhouse.owner_id == user.id).offset(skip).limit(limit)
    return session.exec(q).all()


def create_greenhouse(*, session: Session, greenhouse_create: GreenhouseCreate, owner_id: uuid.UUID) -> Greenhouse:
    gh = Greenhouse.model_validate(greenhouse_create, update={"owner_id": owner_id})
    session.add(gh)
    session.commit()
    session.refresh(gh)
    return gh



def delete_greenhouse(*, session: Session, db_gh: Greenhouse) -> None:
    # cascade delete of links happens automatically (link table FKs)
    session.delete(db_gh)
    session.commit()