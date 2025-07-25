import uuid
from typing import List

from fastapi import APIRouter, HTTPException, status
from sqlmodel import func, select
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    Greenhouse,
    GreenhouseCreate,
    GreenhousePublic,
    GreenhousesPublic,
    GreenhouseUpdate,
    GreenhouseClimateUpdate,
    Message,
)

router = APIRouter(prefix="/greenhouses", tags=["greenhouses"])


class SensorPayload(BaseModel):
    sensor_type: str
    value: float
    timestamp: str


@router.get("/", response_model=GreenhousesPublic)
def read_greenhouses(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> GreenhousesPublic:
    stmt = select(Greenhouse)
    count_stmt = select(func.count()).select_from(Greenhouse)

    if not current_user.is_superuser:
        stmt = stmt.where(Greenhouse.owner_id == current_user.id)
        count_stmt = count_stmt.where(Greenhouse.owner_id == current_user.id)

    total = session.exec(count_stmt).one()
    gh_list: List[Greenhouse] = session.exec(
        stmt.offset(skip).limit(limit)
    ).all()
    return GreenhousesPublic(data=gh_list, count=total)


@router.get("/{greenhouse_id}", response_model=GreenhousePublic)
def read_greenhouse(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    greenhouse_id: uuid.UUID,
) -> Greenhouse:
    gh = session.get(Greenhouse, greenhouse_id)
    if not gh:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Greenhouse not found")
    if not (current_user.is_superuser or gh.owner_id == current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return gh


@router.post("/", response_model=GreenhousePublic, status_code=status.HTTP_201_CREATED)
def create_greenhouse(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    greenhouse_in: GreenhouseCreate,
) -> Greenhouse:
    gh = Greenhouse(**greenhouse_in.model_dump(), owner_id=current_user.id)
    session.add(gh)
    session.commit()
    session.refresh(gh)
    return gh


@router.put("/{greenhouse_id}", response_model=GreenhousePublic)
def update_greenhouse(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    greenhouse_id: uuid.UUID,
    greenhouse_in: GreenhouseUpdate,
) -> Greenhouse:
    gh = session.get(Greenhouse, greenhouse_id)
    if not gh:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Greenhouse not found")
    if not (current_user.is_superuser or gh.owner_id == current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    updates = greenhouse_in.model_dump(exclude_unset=True)
    gh.sqlmodel_update(updates)
    session.add(gh)
    session.commit()
    session.refresh(gh)
    return gh


@router.delete("/{greenhouse_id}", response_model=Message)
def delete_greenhouse(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    greenhouse_id: uuid.UUID,
) -> Message:
    gh = session.get(Greenhouse, greenhouse_id)
    if not gh:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Greenhouse not found")
    if not (current_user.is_superuser or gh.owner_id == current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    session.delete(gh)
    session.commit()
    return Message(message="Greenhouse deleted successfully")


@router.post("/{greenhouse_id}/sensors", response_model=GreenhousePublic)
def add_sensor_data(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    greenhouse_id: uuid.UUID,
    payload: SensorPayload,
) -> Greenhouse:
    gh = session.get(Greenhouse, greenhouse_id)
    if not gh:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Greenhouse not found")
    if not (current_user.is_superuser or gh.owner_id == current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    greenhouse_in = GreenhouseUpdate(**payload.dict())
    updates = greenhouse_in.model_dump(exclude_unset=True)
    gh.sqlmodel_update(updates)
    session.add(gh)
    session.commit()
    session.refresh(gh)
    return gh

@router.put("/{greenhouse_id}/climate", response_model=GreenhousePublic)
def update_climate(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    greenhouse_id: uuid.UUID,
    climate_in: GreenhouseClimateUpdate,               # ← bind JSON body here
) -> Greenhouse:
    gh = session.get(Greenhouse, greenhouse_id)
    if not gh:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Greenhouse not found")
    if not (current_user.is_superuser or gh.owner_id == current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    # apply only the provided fields
    updates = climate_in.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(gh, field, value)

    session.add(gh)
    session.commit()
    session.refresh(gh)
    return gh