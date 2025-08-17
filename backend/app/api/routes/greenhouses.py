import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.crud.greenhouses import get_greenhouse as crud_get_greenhouse
from app.crud.sensors import (
    list_sensors_by_greenhouse,
    list_unmapped_sensors_by_greenhouse,
)
from app.debug_verify import verify_cleanup
from app.models import (
    Greenhouse,
    GreenhouseCreate,
    GreenhousePublic,
    GreenhousesPaginated,
    GreenhouseUpdate,
    SensorPublic,
)
from app.utils_paging import PaginationParams, paginate_query

router = APIRouter()


# Create pagination dependency
def get_pagination_params(page: int = 1, page_size: int = 50) -> PaginationParams:
    return PaginationParams(page=page, page_size=page_size)


PaginationDep = Annotated[PaginationParams, Depends(get_pagination_params)]


@router.get("/", response_model=GreenhousesPaginated)
def read_greenhouses(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    pagination: PaginationDep,
) -> GreenhousesPaginated:
    """List greenhouses with pagination."""
    # Build base query with user scoping
    stmt = select(Greenhouse)
    if not current_user.is_superuser:
        stmt = stmt.where(Greenhouse.user_id == current_user.id)

    # Use the pagination utility
    result = paginate_query(session, stmt, pagination)
    return result


@router.get("/{greenhouse_id}", response_model=GreenhousePublic)
def read_greenhouse(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    greenhouse_id: uuid.UUID,
) -> Greenhouse:
    """Get a specific greenhouse by ID."""
    gh = session.get(Greenhouse, greenhouse_id)
    if not gh:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Greenhouse not found"
        )
    if not (current_user.is_superuser or gh.user_id == current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )
    return gh


@router.post("/", response_model=GreenhousePublic, status_code=status.HTTP_201_CREATED)
def create_greenhouse(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    greenhouse_in: GreenhouseCreate,
) -> Greenhouse:
    """Create a new greenhouse."""
    gh = Greenhouse(**greenhouse_in.model_dump(), user_id=current_user.id)
    session.add(gh)
    session.commit()
    session.refresh(gh)
    return gh


@router.patch("/{greenhouse_id}", response_model=GreenhousePublic)
def update_greenhouse(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    greenhouse_id: uuid.UUID,
    greenhouse_in: GreenhouseUpdate,
) -> Greenhouse:
    """Update a greenhouse."""
    gh = session.get(Greenhouse, greenhouse_id)
    if not gh:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Greenhouse not found"
        )
    if not (current_user.is_superuser or gh.user_id == current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )

    updates = greenhouse_in.model_dump(exclude_unset=True)
    gh.sqlmodel_update(updates)
    session.add(gh)
    session.commit()
    session.refresh(gh)
    return gh


@router.delete("/{greenhouse_id}", status_code=204)
def delete_greenhouse(
    *, greenhouse_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
):
    """Delete a greenhouse."""
    gh = session.get(Greenhouse, greenhouse_id)
    if not gh:
        raise HTTPException(status_code=404, detail="Greenhouse not found")
    if not (current_user.is_superuser or gh.user_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    session.delete(gh)
    session.commit()

    # Verify cleanup
    print(verify_cleanup(session, gh.id))


@router.get("/{greenhouse_id}/listsensors", response_model=list[SensorPublic])
def list_greenhouse_sensors(
    greenhouse_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
):
    """List all sensors for a specific greenhouse."""
    greenhouse = crud_get_greenhouse(session=session, id=greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Greenhouse not found")

    if not (current_user.is_superuser or greenhouse.user_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    return list_sensors_by_greenhouse(session, greenhouse_id)


@router.get("/{greenhouse_id}/unmapped-sensors", response_model=list[SensorPublic])
def list_unmapped_greenhouse_sensors(
    greenhouse_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
):
    """List all unmapped sensors for a specific greenhouse."""
    greenhouse = crud_get_greenhouse(session=session, id=greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Greenhouse not found")

    if not (current_user.is_superuser or greenhouse.user_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    return list_unmapped_sensors_by_greenhouse(session, greenhouse_id)
