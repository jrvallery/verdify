import uuid
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, SessionDep
from app.crud.zone import (
    count_zones as crud_count_zones,
)
from app.crud.zone import (
    create_zone as crud_create_zone,
)
from app.crud.zone import (
    delete_zone as crud_delete_zone,
)
from app.crud.zone import (
    get_zone as crud_get_zone,
)
from app.crud.zone import (
    list_zones as crud_list_zones,
)
from app.crud.zone import (
    update_zone as crud_update_zone,
)
from app.crud.zone import (
    validate_greenhouse_ownership,
)
from app.models import (
    Greenhouse,
    Zone,
    ZoneCreate,
    ZonePublic,
    ZoneUpdate,
)
from app.utils_paging import Paginated, PaginationParams, page_to_offset

# Create ZonesPaginated using the correct ZonePublic from models
ZonesPaginated = Paginated[ZonePublic]

router = APIRouter()


class ZoneSortEnum(str, Enum):
    """Allowed sort fields for zones."""

    zone_number = "zone_number"
    title = "title"  # Note: fallback to zone_number since Zone doesn't have title
    created_at = (
        "created_at"  # Note: fallback to zone_number since Zone doesn't have created_at
    )
    zone_number_desc = "-zone_number"
    title_desc = "-title"
    created_at_desc = "-created_at"


# Create pagination dependency
def get_pagination_params(page: int = 1, page_size: int = 50) -> PaginationParams:
    return PaginationParams(page=page, page_size=page_size)


PaginationDep = Annotated[PaginationParams, Depends(get_pagination_params)]


@router.get("/", response_model=ZonesPaginated)
def list_zones(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    pagination: PaginationDep,
    greenhouse_id: uuid.UUID | None = Query(
        None, description="Filter by greenhouse ID"
    ),
    is_active: bool | None = Query(
        None, description="Filter by active status (not implemented)"
    ),
    sort: ZoneSortEnum = Query(
        ZoneSortEnum.zone_number, description="Sort field and direction"
    ),
) -> ZonesPaginated:
    """
    List zones with optional filtering and sorting.

    Supports filtering by greenhouse_id and sorting by various fields.
    The is_active filter is ignored as this field is not currently modeled in the Zone table.
    """
    # Validate greenhouse ownership if greenhouse_id is provided
    if greenhouse_id and not current_user.is_superuser:
        if not validate_greenhouse_ownership(session, greenhouse_id, current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions to access this greenhouse",
            )

    # Calculate offset and limit from pagination
    offset, limit = page_to_offset(pagination.page, pagination.page_size)

    # Get total count for pagination
    total = crud_count_zones(
        session=session,
        greenhouse_id=greenhouse_id,
        is_active=is_active,  # Ignored in implementation
    )

    # Get zones with filtering and sorting
    zones = crud_list_zones(
        session=session,
        greenhouse_id=greenhouse_id,
        is_active=is_active,  # Ignored in implementation
        sort=sort.value,
        skip=offset,
        limit=limit,
    )

    # For superusers, return all zones; for regular users, filter by greenhouse ownership
    if not current_user.is_superuser and greenhouse_id is None:
        # For non-superusers without greenhouse filter, we need to filter by owned greenhouses
        # This requires loading the greenhouse relationship or doing a join query
        # For now, let's require greenhouse_id parameter for non-superusers
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="greenhouse_id parameter is required for non-superuser access",
        )

    return ZonesPaginated(
        data=zones,
        page=pagination.page,
        page_size=pagination.page_size,
        total=total,
    )


@router.post("/", response_model=ZonePublic, status_code=status.HTTP_201_CREATED)
def create_zone(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    zone_in: ZoneCreate,
) -> Zone:
    """Create a new zone."""
    # Validate user owns the greenhouse
    if not current_user.is_superuser:
        if not validate_greenhouse_ownership(
            session, zone_in.greenhouse_id, current_user.id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions to create zone in this greenhouse",
            )

    try:
        return crud_create_zone(session, zone_in)
    except IntegrityError as e:
        session.rollback()
        if "uq_zone_number_per_greenhouse" in str(e.orig):
            raise HTTPException(
                status_code=400,
                detail="Zone with this zone number already exists in this greenhouse",
            )
        # Handle other potential integrity errors
        raise HTTPException(
            status_code=400, detail="Failed to create zone due to constraint violation"
        )


@router.get("/{zone_id}", response_model=ZonePublic)
def get_zone(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    zone_id: uuid.UUID,
) -> Zone:
    """Get a specific zone by ID."""
    zone = crud_get_zone(session, zone_id)
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found"
        )

    # Validate ownership through greenhouse
    if not current_user.is_superuser:
        # Get greenhouse manually since we use foreign-key-only mapping
        greenhouse = session.get(Greenhouse, zone.greenhouse_id)
        if not greenhouse or greenhouse.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
            )

    return zone


@router.patch("/{zone_id}", response_model=ZonePublic)
def update_zone(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    zone_id: uuid.UUID,
    zone_in: ZoneUpdate,
) -> Zone:
    """Update a zone."""
    zone = crud_get_zone(session, zone_id)
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found"
        )

    # Validate ownership through greenhouse
    if not current_user.is_superuser:
        # Get greenhouse manually since we use foreign-key-only mapping
        greenhouse = session.get(Greenhouse, zone.greenhouse_id)
        if not greenhouse or greenhouse.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
            )

    return crud_update_zone(session, zone, zone_in)


@router.delete("/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_zone(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    zone_id: uuid.UUID,
):
    """Delete a zone."""
    zone = crud_get_zone(session, zone_id)
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found"
        )

    # Validate ownership through greenhouse
    if not current_user.is_superuser:
        # Get greenhouse manually since we use foreign-key-only mapping
        greenhouse = session.get(Greenhouse, zone.greenhouse_id)
        if not greenhouse or greenhouse.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
            )

    crud_delete_zone(session, zone)
