import uuid
from typing import List

from fastapi import APIRouter, HTTPException, status
from sqlmodel import func, select
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    ControllerCreate, 
    ControllerPublic, 
    ControllerUpdate
)
from app.crud.controller import (
    create_controller as crud_create_controller,
    get_controller as crud_get_controller,
    list_controllers as crud_list_controllers,
    update_controller as crud_update_controller,
    delete_controller as crud_delete_controller,
)
from app.crud.greenhouses import get_greenhouse as crud_get_greenhouse

router = APIRouter()

@router.post("/", response_model=ControllerPublic)
def create_controller(
    c_in: ControllerCreate,
    session: SessionDep
):
    # ensure parent greenhouse exists
    if not crud_get_greenhouse(session=session, id=c_in.greenhouse_id):
        raise HTTPException(status_code=404, detail="Parent greenhouse not found")
    return crud_create_controller(session, c_in)

@router.get("/", response_model=List[ControllerPublic])
def list_controllers(
    session: SessionDep
):
    return crud_list_controllers(session)

@router.get("/{controller_id}", response_model=ControllerPublic)
def get_controller(
    controller_id: uuid.UUID,
    session: SessionDep
):
    controller = crud_get_controller(session, controller_id)
    if not controller:
        raise HTTPException(status_code=404, detail="Controller not found")
    return controller

@router.patch("/{controller_id}", response_model=ControllerPublic)
def update_controller(
    controller_id: uuid.UUID,
    c_in: ControllerUpdate,
    session: SessionDep
):
    controller = crud_get_controller(session, controller_id)
    if not controller:
        raise HTTPException(status_code=404, detail="Controller not found")
    return crud_update_controller(session, controller, c_in)

@router.delete("/{controller_id}")
def delete_controller(
    controller_id: uuid.UUID,
    session: SessionDep
):
    controller = crud_get_controller(session, controller_id)
    if not controller:
        raise HTTPException(status_code=404, detail="Controller not found")
    crud_delete_controller(session, controller)
    return {"ok": True}