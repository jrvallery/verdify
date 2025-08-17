from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.api.deps import get_current_user, get_db
from app.core.upload import presigned_upload_service
from app.crud.observation import observation as crud_observation
from app.models import (
    User,
    ZoneCropObservationCreate,
    ZoneCropObservationPublic,
    ZoneCropObservationsPaginated,
    ZoneCropObservationUpdate,
)
from app.models.enums import ObservationType
from app.utils_errors import ErrorResponse

router = APIRouter()


@router.post(
    "/observations",
    response_model=ZoneCropObservationPublic,
    status_code=201,
    responses={
        201: {"description": "Observation created successfully"},
        400: {"description": "Invalid input", "model": ErrorResponse},
        403: {"description": "Not authorized", "model": ErrorResponse},
    },
    tags=["Observations"],
)
def create_observation(
    *,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    observation_in: ZoneCropObservationCreate,
) -> ZoneCropObservationPublic:
    """Create a new zone crop observation"""
    observation = crud_observation.create(
        session=session, obj_in=observation_in, user_id=current_user.id
    )
    return ZoneCropObservationPublic.model_validate(observation)


@router.get(
    "/observations",
    response_model=ZoneCropObservationsPaginated,
    responses={
        200: {"description": "Observations retrieved successfully"},
        400: {"description": "Invalid parameters", "model": ErrorResponse},
    },
    tags=["Observations"],
)
def list_observations(
    *,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    zone_crop_id: Annotated[
        UUID | None, Query(description="Filter by zone crop ID")
    ] = None,
    zone_id: Annotated[UUID | None, Query(description="Filter by zone ID")] = None,
    greenhouse_id: Annotated[
        UUID | None, Query(description="Filter by greenhouse ID")
    ] = None,
    observation_type: Annotated[
        ObservationType | None, Query(description="Filter by observation type")
    ] = None,
    sort: Annotated[
        str, Query(description="Sort field and order")
    ] = "-observation_date",
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
) -> ZoneCropObservationsPaginated:
    """List observations with filtering and pagination"""
    skip = (page - 1) * page_size

    observations = crud_observation.get_multi(
        session=session,
        user_id=current_user.id,
        zone_crop_id=zone_crop_id,
        zone_id=zone_id,
        greenhouse_id=greenhouse_id,
        observation_type=observation_type,
        sort=sort,
        skip=skip,
        limit=page_size,
    )

    total = crud_observation.count(
        session=session,
        user_id=current_user.id,
        zone_crop_id=zone_crop_id,
        zone_id=zone_id,
        greenhouse_id=greenhouse_id,
        observation_type=observation_type,
    )

    return ZoneCropObservationsPaginated(
        data=[ZoneCropObservationPublic.model_validate(obs) for obs in observations],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/observations/{observation_id}",
    response_model=ZoneCropObservationPublic,
    responses={
        200: {"description": "Observation retrieved successfully"},
        403: {"description": "Not authorized", "model": ErrorResponse},
        404: {"description": "Observation not found", "model": ErrorResponse},
    },
    tags=["Observations"],
)
def get_observation(
    *,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    observation_id: UUID,
) -> ZoneCropObservationPublic:
    """Get observation by ID"""
    observation = crud_observation.get(session=session, id=observation_id)
    if not observation:
        raise HTTPException(status_code=404, detail="Observation not found")

    # Validate ownership through zone crop
    if not crud_observation.validate_zone_crop_ownership(
        session, zone_crop_id=observation.zone_crop_id, user_id=current_user.id
    ):
        raise HTTPException(
            status_code=403, detail="Not authorized to access this observation"
        )

    return ZoneCropObservationPublic.model_validate(observation)


@router.put(
    "/observations/{observation_id}",
    response_model=ZoneCropObservationPublic,
    responses={
        200: {"description": "Observation updated successfully"},
        400: {"description": "Invalid input", "model": ErrorResponse},
        403: {"description": "Not authorized", "model": ErrorResponse},
        404: {"description": "Observation not found", "model": ErrorResponse},
    },
    tags=["Observations"],
)
def update_observation(
    *,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    observation_id: UUID,
    observation_in: ZoneCropObservationUpdate,
) -> ZoneCropObservationPublic:
    """Update observation"""
    observation = crud_observation.get(session=session, id=observation_id)
    if not observation:
        raise HTTPException(status_code=404, detail="Observation not found")

    updated_observation = crud_observation.update(
        session=session,
        db_obj=observation,
        obj_in=observation_in,
        user_id=current_user.id,
    )
    return ZoneCropObservationPublic.model_validate(updated_observation)


@router.delete(
    "/observations/{observation_id}",
    status_code=204,
    responses={
        204: {"description": "Observation deleted successfully"},
        403: {"description": "Not authorized", "model": ErrorResponse},
        404: {"description": "Observation not found", "model": ErrorResponse},
    },
    tags=["Observations"],
)
def delete_observation(
    *,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    observation_id: UUID,
) -> None:
    """Delete observation"""
    observation = crud_observation.remove(
        session=session, id=observation_id, user_id=current_user.id
    )
    if not observation:
        raise HTTPException(status_code=404, detail="Observation not found")


@router.post(
    "/observations/{observation_id}/upload-url",
    response_model=dict,
    responses={
        200: {"description": "Upload URL generated successfully"},
        403: {"description": "Not authorized", "model": ErrorResponse},
        404: {"description": "Observation not found", "model": ErrorResponse},
    },
    tags=["Observations"],
)
def get_observation_upload_url(
    *,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    observation_id: UUID,
    filename: Annotated[
        str | None, Query(description="Original filename for extension detection")
    ] = None,
) -> dict:
    """
    Generate presigned upload URL for observation image

    Returns:
        dict: {
            "upload_url": str,
            "expires_in_s": int
        }
    """
    return presigned_upload_service.generate_upload_url(
        session=session,
        observation_id=observation_id,
        user_id=current_user.id,
        filename=filename,
    )
