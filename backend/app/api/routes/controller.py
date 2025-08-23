import uuid

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, SessionDep
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
    list_controllers as crud_list_controllers,
)
from app.crud.controller import (
    update_controller as crud_update_controller,
)
from app.crud.greenhouses import get_greenhouse as crud_get_greenhouse
from app.models import (
    ControllerCreate,
    ControllerPublic,
    ControllerUpdate,
)

router = APIRouter()


@router.post("/", response_model=ControllerPublic)
def create_controller(
    greenhouse_id: uuid.UUID,  # From URL path
    c_in: ControllerCreate,
    session: SessionDep,
    current_user: CurrentUser,
):
    # Verify user owns this greenhouse
    greenhouse = crud_get_greenhouse(session=session, id=greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Greenhouse not found")
    if not (current_user.is_superuser or greenhouse.user_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Override greenhouse_id from URL path
    c_in.greenhouse_id = greenhouse_id
    return crud_create_controller(session, c_in)


@router.get("/", response_model=list[ControllerPublic])
def list_controllers(
    greenhouse_id: uuid.UUID,  # From URL path
    session: SessionDep,
    current_user: CurrentUser,
):
    # Verify user owns this greenhouse
    greenhouse = crud_get_greenhouse(session=session, id=greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Greenhouse not found")
    if not (current_user.is_superuser or greenhouse.user_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # Return controllers ONLY for this specific greenhouse
    return crud_list_controllers(session, greenhouse_id)


@router.get("/{controller_id}", response_model=ControllerPublic)
def get_controller(
    greenhouse_id: uuid.UUID,  # From URL path
    controller_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    controller = crud_get_controller(session, controller_id)
    if not controller:
        raise HTTPException(status_code=404, detail="Controller not found")

    # Verify controller belongs to the greenhouse in the URL
    if controller.greenhouse_id != greenhouse_id:
        raise HTTPException(
            status_code=404, detail="Controller not found in this greenhouse"
        )

    # Check ownership by querying the greenhouse
    greenhouse = crud_get_greenhouse(session=session, id=greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Greenhouse not found")
    if not (current_user.is_superuser or greenhouse.user_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return controller


@router.patch("/{controller_id}", response_model=ControllerPublic)
def update_controller(
    greenhouse_id: uuid.UUID,  # From URL path
    controller_id: uuid.UUID,
    c_in: ControllerUpdate,
    session: SessionDep,
    current_user: CurrentUser,
):
    controller = crud_get_controller(session, controller_id)
    if not controller:
        raise HTTPException(status_code=404, detail="Controller not found")

    # Verify controller belongs to the greenhouse in the URL
    if controller.greenhouse_id != greenhouse_id:
        raise HTTPException(
            status_code=404, detail="Controller not found in this greenhouse"
        )

    # Check ownership by querying the greenhouse
    greenhouse = crud_get_greenhouse(session=session, id=greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Greenhouse not found")
    if not (current_user.is_superuser or greenhouse.user_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return crud_update_controller(session, controller, c_in)


@router.delete("/{controller_id}")
def delete_controller(
    greenhouse_id: uuid.UUID,  # From URL path
    controller_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    controller = crud_get_controller(session, controller_id)
    if not controller:
        raise HTTPException(status_code=404, detail="Controller not found")

    # Verify controller belongs to the greenhouse in the URL
    if controller.greenhouse_id != greenhouse_id:
        raise HTTPException(
            status_code=404, detail="Controller not found in this greenhouse"
        )

    # Check ownership by querying the greenhouse
    greenhouse = crud_get_greenhouse(session=session, id=greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Greenhouse not found")
    if not (current_user.is_superuser or greenhouse.user_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    crud_delete_controller(session, controller)
    return {"ok": True}
