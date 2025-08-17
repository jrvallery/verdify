import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, SessionDep
from app.crud.actuator import (
    create_actuator as crud_create_actuator,
)
from app.crud.actuator import (
    delete_actuator as crud_delete_actuator,
)
from app.crud.actuator import (
    get_actuator as crud_get_actuator,
)
from app.crud.actuator import (
    list_actuators,
    validate_user_owns_actuator,
)
from app.crud.actuator import (
    update_actuator as crud_update_actuator,
)
from app.crud.controller import get_controller as crud_get_controller
from app.models import (
    ActuatorCreate,
    ActuatorKind,
    ActuatorPublic,
    ActuatorsPaginated,
    ActuatorUpdate,
)
from app.utils_paging import PaginationParams

router = APIRouter()


@router.get("/", response_model=ActuatorsPaginated)
def list_actuators_endpoint(
    session: SessionDep,
    current_user: CurrentUser,
    controller_id: uuid.UUID | None = Query(
        None, description="Filter by controller ID"
    ),
    kind: ActuatorKind | None = Query(None, description="Filter by actuator kind"),
    sort: str = Query("name", description="Sort field and direction"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
) -> ActuatorsPaginated:
    """List actuators with optional filtering."""
    pagination = PaginationParams(page=page, page_size=page_size)
    return list_actuators(
        session=session,
        user_id=current_user.id,
        pagination=pagination,
        controller_id=controller_id,
        kind=kind,
        sort=sort,
    )


@router.post("/", response_model=ActuatorPublic, status_code=status.HTTP_201_CREATED)
def create_actuator_endpoint(
    actuator_in: ActuatorCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ActuatorPublic:
    """Create a new actuator."""
    # Validate that user owns the controller
    controller = crud_get_controller(session, actuator_in.controller_id)
    if not controller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Controller not found"
        )

    # Check ownership through greenhouse
    from app.crud.greenhouses import validate_user_owns_greenhouse

    if not validate_user_owns_greenhouse(
        session, controller.greenhouse_id, current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )

    try:
        actuator = crud_create_actuator(session, actuator_in)
        return ActuatorPublic.model_validate(actuator)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{actuator_id}", response_model=ActuatorPublic)
def get_actuator_endpoint(
    actuator_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> ActuatorPublic:
    """Get an actuator by ID."""
    actuator = crud_get_actuator(session, actuator_id)
    if not actuator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Actuator not found"
        )

    # Validate ownership
    if not validate_user_owns_actuator(session, actuator_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )

    return ActuatorPublic.model_validate(actuator)


@router.patch("/{actuator_id}", response_model=ActuatorPublic)
def update_actuator_endpoint(
    actuator_id: uuid.UUID,
    actuator_in: ActuatorUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ActuatorPublic:
    """Update an actuator."""
    # Validate ownership first
    if not validate_user_owns_actuator(session, actuator_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )

    actuator = crud_update_actuator(session, actuator_id, actuator_in)
    if not actuator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Actuator not found"
        )

    return ActuatorPublic.model_validate(actuator)


@router.delete("/{actuator_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_actuator_endpoint(
    actuator_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> None:
    """Delete an actuator."""
    # Validate ownership first
    if not validate_user_owns_actuator(session, actuator_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )

    if not crud_delete_actuator(session, actuator_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Actuator not found"
        )
