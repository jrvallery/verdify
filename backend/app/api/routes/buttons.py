import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, SessionDep
from app.crud.buttons import (
    create_controller_button as crud_create_controller_button,
)
from app.crud.buttons import (
    delete_controller_button as crud_delete_controller_button,
)
from app.crud.buttons import (
    get_controller_button as crud_get_controller_button,
)
from app.crud.buttons import (
    list_controller_buttons,
    validate_user_owns_controller_button,
)
from app.crud.buttons import (
    update_controller_button as crud_update_controller_button,
)
from app.crud.controller import get_controller as crud_get_controller
from app.models import (
    ButtonKind,
    ControllerButtonCreate,
    ControllerButtonPublic,
    ControllerButtonsPaginated,
    ControllerButtonUpdate,
)
from app.utils_paging import PaginationParams

router = APIRouter()


@router.get("/", response_model=ControllerButtonsPaginated)
def list_controller_buttons_endpoint(
    session: SessionDep,
    current_user: CurrentUser,
    controller_id: uuid.UUID | None = Query(
        None, description="Filter by controller ID"
    ),
    button_kind: ButtonKind | None = Query(None, description="Filter by button kind"),
    sort: str = Query("button_kind", description="Sort field and direction"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
) -> ControllerButtonsPaginated:
    """List controller buttons with optional filtering."""
    pagination = PaginationParams(page=page, page_size=page_size)
    return list_controller_buttons(
        session=session,
        user_id=current_user.id,
        pagination=pagination,
        controller_id=controller_id,
        button_kind=button_kind,
        sort=sort,
    )


@router.post(
    "/", response_model=ControllerButtonPublic, status_code=status.HTTP_201_CREATED
)
def create_controller_button_endpoint(
    button_in: ControllerButtonCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ControllerButtonPublic:
    """Create a new controller button configuration."""
    # Validate that user owns the controller
    controller = crud_get_controller(session, button_in.controller_id)
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
        button = crud_create_controller_button(session, button_in)
        return ControllerButtonPublic.model_validate(button)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{button_id}", response_model=ControllerButtonPublic)
def get_controller_button_endpoint(
    button_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> ControllerButtonPublic:
    """Get a controller button by ID."""
    button = crud_get_controller_button(session, button_id)
    if not button:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Controller button not found"
        )

    # Validate ownership
    if not validate_user_owns_controller_button(session, button_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )

    return ControllerButtonPublic.model_validate(button)


@router.patch("/{button_id}", response_model=ControllerButtonPublic)
def update_controller_button_endpoint(
    button_id: uuid.UUID,
    button_in: ControllerButtonUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ControllerButtonPublic:
    """Update a controller button."""
    # Validate ownership first
    if not validate_user_owns_controller_button(session, button_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )

    button = crud_update_controller_button(session, button_id, button_in)
    if not button:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Controller button not found"
        )

    return ControllerButtonPublic.model_validate(button)


@router.delete("/{button_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_controller_button_endpoint(
    button_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> None:
    """Delete a controller button."""
    # Validate ownership first
    if not validate_user_owns_controller_button(session, button_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
        )

    if not crud_delete_controller_button(session, button_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Controller button not found"
        )
