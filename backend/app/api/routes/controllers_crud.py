"""
Top-level Controllers CRUD API endpoints.

These endpoints provide direct access to controller management operations
following the OpenAPI specification. They differ from the nested routes
under /greenhouses/{greenhouse_id}/controllers in that they provide
cross-greenhouse filtering and management.
"""

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import and_, select

from app.api.deps import CurrentUser, PaginationDep, SessionDep
from app.crud.controller import (
    create_controller as crud_create_controller,
)
from app.crud.controller import (
    delete_controller as crud_delete_controller,
)
from app.crud.controller import (
    get_controller as crud_get_controller,
)
from app.crud.controller import (
    update_controller as crud_update_controller,
)
from app.crud.greenhouses import get_greenhouse as crud_get_greenhouse
from app.models import (
    Controller,
    ControllerCreate,
    ControllerPublic,
    ControllerUpdate,
    Greenhouse,
)
from app.utils_paging import Paginated, paginate_query

router = APIRouter()


@router.get("/", response_model=Paginated[ControllerPublic])
def list_controllers(
    session: SessionDep,
    current_user: CurrentUser,
    pagination: PaginationDep,
    greenhouse_id: uuid.UUID | None = Query(
        None, description="Filter by greenhouse ID"
    ),
    is_climate_controller: bool | None = Query(
        None, description="Filter by climate controller status"
    ),
    sort: str = Query(
        "device_name",
        enum=["device_name", "created_at", "-device_name", "-created_at"],
        description="Sort field and direction",
    ),
) -> Paginated[ControllerPublic]:
    """
    List controllers with optional filtering and sorting.

    - **greenhouse_id**: Filter to specific greenhouse (optional)
    - **is_climate_controller**: Filter by climate controller status (optional)
    - **sort**: Sort by device_name or created_at, prefix with '-' for descending
    - **page/page_size**: Standard pagination parameters

    Returns paginated list of controllers the user has access to.
    """
    # Base query - only include claimed controllers (greenhouse_id IS NOT NULL)
    # from greenhouses user owns (unless superuser, then show all claimed controllers)
    base_query = select(Controller).where(Controller.greenhouse_id.is_not(None))

    if not current_user.is_superuser:
        # Join with greenhouse to filter by ownership
        base_query = base_query.join(Greenhouse).where(
            Greenhouse.user_id == current_user.id
        )

    # Apply greenhouse filter if provided
    if greenhouse_id:
        # Verify user has access to this greenhouse
        greenhouse = crud_get_greenhouse(session=session, id=greenhouse_id)
        if not greenhouse:
            raise HTTPException(status_code=404, detail="Greenhouse not found")
        if not (current_user.is_superuser or greenhouse.user_id == current_user.id):
            raise HTTPException(status_code=403, detail="Not enough permissions")

        base_query = base_query.where(Controller.greenhouse_id == greenhouse_id)

    # Apply climate controller filter if provided
    if is_climate_controller is not None:
        base_query = base_query.where(
            Controller.is_climate_controller == is_climate_controller
        )

    # Apply sorting
    if sort.startswith("-"):
        # Descending
        field = sort[1:]
        if field == "device_name":
            base_query = base_query.order_by(Controller.device_name.desc())
        elif field == "created_at":
            base_query = base_query.order_by(Controller.created_at.desc())
    else:
        # Ascending
        if sort == "device_name":
            base_query = base_query.order_by(Controller.device_name)
        elif sort == "created_at":
            base_query = base_query.order_by(Controller.created_at)

    # Execute paginated query
    return paginate_query(session, base_query, pagination)


@router.post("/", response_model=ControllerPublic, status_code=status.HTTP_201_CREATED)
def create_controller(
    controller_in: ControllerCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ControllerPublic:
    """
    Create a new controller.

    - **device_name**: Must follow 'verdify-XXXXXX' pattern
    - **greenhouse_id**: Must be a greenhouse the user owns
    - **is_climate_controller**: Whether this controls climate (default: false)

    Validates device_name uniqueness and greenhouse ownership.
    """
    # Verify user owns the greenhouse
    greenhouse = crud_get_greenhouse(session=session, id=controller_in.greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Greenhouse not found")
    if not (current_user.is_superuser or greenhouse.user_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Check device_name uniqueness
    existing = session.exec(
        select(Controller).where(Controller.device_name == controller_in.device_name)
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Controller with device_name '{controller_in.device_name}' already exists",
        )

    # If setting is_climate_controller=True, ensure no other climate controller in this greenhouse
    if controller_in.is_climate_controller:
        existing_climate = session.exec(
            select(Controller).where(
                and_(
                    Controller.greenhouse_id == controller_in.greenhouse_id,
                    Controller.is_climate_controller is True,
                )
            )
        ).first()
        if existing_climate:
            raise HTTPException(
                status_code=409,
                detail=f"Greenhouse already has a climate controller: {existing_climate.device_name}",
            )

    return crud_create_controller(session, controller_in)


@router.get("/{controller_id}", response_model=ControllerPublic)
def get_controller(
    controller_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> ControllerPublic:
    """
    Get a specific controller by ID.

    User must own the greenhouse containing this controller.
    Only returns claimed controllers (with greenhouse_id).
    """
    controller = crud_get_controller(session, controller_id)
    if not controller or controller.greenhouse_id is None:
        raise HTTPException(status_code=404, detail="Controller not found")

    # Check ownership by querying the greenhouse
    greenhouse = crud_get_greenhouse(session=session, id=controller.greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Controller not found")
    if not (current_user.is_superuser or greenhouse.user_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    return controller


@router.patch("/{controller_id}", response_model=ControllerPublic)
def update_controller(
    controller_id: uuid.UUID,
    controller_update: ControllerUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ControllerPublic:
    """
    Update a controller.

    - **is_climate_controller**: Can be changed (subject to uniqueness constraint)
    - **label**: Can be updated
    - **versions**: fw_version, hw_version can be updated

    Enforces business rules around climate controller uniqueness.
    """
    controller = crud_get_controller(session, controller_id)
    if not controller or controller.greenhouse_id is None:
        raise HTTPException(status_code=404, detail="Controller not found")

    # Check ownership by querying the greenhouse
    greenhouse = crud_get_greenhouse(session=session, id=controller.greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Controller not found")
    if not (current_user.is_superuser or greenhouse.user_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # If changing is_climate_controller to True, check uniqueness
    if (
        controller_update.is_climate_controller is True
        and not controller.is_climate_controller
    ):
        existing_climate = session.exec(
            select(Controller).where(
                and_(
                    Controller.greenhouse_id == controller.greenhouse_id,
                    Controller.is_climate_controller is True,
                    Controller.id != controller_id,
                )
            )
        ).first()
        if existing_climate:
            raise HTTPException(
                status_code=409,
                detail=f"Greenhouse already has a climate controller: {existing_climate.device_name}",
            )

    return crud_update_controller(session, controller, controller_update)


@router.delete("/{controller_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_controller(
    controller_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    """
    Delete a controller.

    This will also revoke any associated device tokens and cascade delete
    related sensors, actuators, etc.
    Only allows deletion of claimed controllers.
    """
    controller = crud_get_controller(session, controller_id)
    if not controller or controller.greenhouse_id is None:
        raise HTTPException(status_code=404, detail="Controller not found")

    # Check ownership by querying the greenhouse
    greenhouse = crud_get_greenhouse(session=session, id=controller.greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Controller not found")
    if not (current_user.is_superuser or greenhouse.user_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    crud_delete_controller(session, controller)
