from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.api.deps import get_current_user, get_db
from app.crud.zone_crop import zone_crop as crud_zone_crop
from app.models import (
    User,
    ZoneCropCreate,
    ZoneCropPublic,
    ZoneCropsPaginated,
    ZoneCropUpdate,
)
from app.utils_errors import ErrorResponse

router = APIRouter()


@router.post(
    "/zone-crops",
    response_model=ZoneCropPublic,
    status_code=201,
    responses={
        201: {"description": "Zone crop created successfully"},
        400: {"description": "Invalid input", "model": ErrorResponse},
        403: {"description": "Not authorized", "model": ErrorResponse},
        409: {
            "description": "Conflict - active crop already exists in zone",
            "model": ErrorResponse,
        },
    },
    tags=["Zone Crops"],
)
def create_zone_crop(
    *,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    zone_crop_in: ZoneCropCreate,
) -> ZoneCropPublic:
    """Create a new zone crop planting"""
    zone_crop = crud_zone_crop.create(
        session=session, obj_in=zone_crop_in, user_id=current_user.id
    )
    return ZoneCropPublic.model_validate(zone_crop)


@router.get(
    "/zone-crops",
    response_model=ZoneCropsPaginated,
    responses={
        200: {"description": "Zone crops retrieved successfully"},
        400: {"description": "Invalid parameters", "model": ErrorResponse},
    },
    tags=["Zone Crops"],
)
def list_zone_crops(
    *,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    zone_id: Annotated[UUID | None, Query(description="Filter by zone ID")] = None,
    greenhouse_id: Annotated[
        UUID | None, Query(description="Filter by greenhouse ID")
    ] = None,
    is_active: Annotated[
        bool | None, Query(description="Filter by active status")
    ] = None,
    sort: Annotated[str, Query(description="Sort field and order")] = "-start_date",
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
) -> ZoneCropsPaginated:
    """List zone crops with filtering and pagination"""
    skip = (page - 1) * page_size

    zone_crops = crud_zone_crop.get_multi(
        session=session,
        user_id=current_user.id,
        zone_id=zone_id,
        greenhouse_id=greenhouse_id,
        is_active=is_active,
        sort=sort,
        skip=skip,
        limit=page_size,
    )

    total = crud_zone_crop.count(
        session=session,
        user_id=current_user.id,
        zone_id=zone_id,
        greenhouse_id=greenhouse_id,
        is_active=is_active,
    )

    return ZoneCropsPaginated(
        data=[ZoneCropPublic.model_validate(crop) for crop in zone_crops],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/zone-crops/{zone_crop_id}",
    response_model=ZoneCropPublic,
    responses={
        200: {"description": "Zone crop retrieved successfully"},
        403: {"description": "Not authorized", "model": ErrorResponse},
        404: {"description": "Zone crop not found", "model": ErrorResponse},
    },
    tags=["Zone Crops"],
)
def get_zone_crop(
    *,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    zone_crop_id: UUID,
) -> ZoneCropPublic:
    """Get zone crop by ID"""
    zone_crop = crud_zone_crop.get(session=session, id=zone_crop_id)
    if not zone_crop:
        raise HTTPException(status_code=404, detail="Zone crop not found")

    # Validate ownership
    if not crud_zone_crop.validate_zone_ownership(
        session, zone_id=zone_crop.zone_id, user_id=current_user.id
    ):
        raise HTTPException(
            status_code=403, detail="Not authorized to access this zone crop"
        )

    return ZoneCropPublic.model_validate(zone_crop)


@router.put(
    "/zone-crops/{zone_crop_id}",
    response_model=ZoneCropPublic,
    responses={
        200: {"description": "Zone crop updated successfully"},
        400: {"description": "Invalid input", "model": ErrorResponse},
        403: {"description": "Not authorized", "model": ErrorResponse},
        404: {"description": "Zone crop not found", "model": ErrorResponse},
    },
    tags=["Zone Crops"],
)
def update_zone_crop(
    *,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    zone_crop_id: UUID,
    zone_crop_in: ZoneCropUpdate,
) -> ZoneCropPublic:
    """Update zone crop"""
    zone_crop = crud_zone_crop.get(session=session, id=zone_crop_id)
    if not zone_crop:
        raise HTTPException(status_code=404, detail="Zone crop not found")

    updated_zone_crop = crud_zone_crop.update(
        session=session, db_obj=zone_crop, obj_in=zone_crop_in, user_id=current_user.id
    )
    return ZoneCropPublic.model_validate(updated_zone_crop)


@router.delete(
    "/zone-crops/{zone_crop_id}",
    status_code=204,
    responses={
        204: {"description": "Zone crop deleted successfully"},
        403: {"description": "Not authorized", "model": ErrorResponse},
        404: {"description": "Zone crop not found", "model": ErrorResponse},
    },
    tags=["Zone Crops"],
)
def delete_zone_crop(
    *,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    zone_crop_id: UUID,
) -> None:
    """Delete zone crop"""
    zone_crop = crud_zone_crop.remove(
        session=session, id=zone_crop_id, user_id=current_user.id
    )
    if not zone_crop:
        raise HTTPException(status_code=404, detail="Zone crop not found")
