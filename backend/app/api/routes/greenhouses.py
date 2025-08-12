import uuid
from typing import List

from fastapi import APIRouter, HTTPException, Response, status, Depends
from sqlmodel import func, select, Session
from pydantic import BaseModel

from app.debug_verify import verify_cleanup

from app.api.deps import CurrentUser, SessionDep, User, get_current_user
from app.models import (
    Greenhouse,
    GreenhouseCreate,
    GreenhousePublic,
    GreenhousesPublic,
    GreenhouseUpdate,
    Message,
    SensorPublic,
)
from app.crud.sensors import list_sensors_by_greenhouse, list_unmapped_sensors_by_greenhouse
from app.crud.greenhouses import get_greenhouse as crud_get_greenhouse

router = APIRouter()
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


@router.delete("/{greenhouse_id}", status_code=204)
def delete_greenhouse(
    greenhouse_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser
):
    gh = session.get(Greenhouse, greenhouse_id)
    if not gh:
        raise HTTPException(status_code=404, detail="Greenhouse not found")
    if not (current_user.is_superuser or gh.owner_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    session.delete(gh)
    session.commit()

    # Verify cleanup
    print(verify_cleanup(session, gh.id))

    return Response(status_code=204)


@router.get("/{greenhouse_id}/listsensors", response_model=List[SensorPublic])
def list_greenhouse_sensors(
    greenhouse_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser
):
    """List all sensors for a specific greenhouse."""
    greenhouse = crud_get_greenhouse(session=session, id=greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Greenhouse not found")
    
    if not (current_user.is_superuser or greenhouse.owner_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    return list_sensors_by_greenhouse(session, greenhouse_id)


@router.get("/{greenhouse_id}/unmapped-sensors", response_model=List[SensorPublic])
def list_unmapped_greenhouse_sensors(
    greenhouse_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser
):
    """List all unmapped sensors for a specific greenhouse."""
    greenhouse = crud_get_greenhouse(session=session, id=greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Greenhouse not found")
    
    if not (current_user.is_superuser or greenhouse.owner_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    return list_unmapped_sensors_by_greenhouse(session, greenhouse_id)
