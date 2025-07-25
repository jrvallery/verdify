import uuid
from typing import List

from fastapi import APIRouter, HTTPException, status
from sqlmodel import func, select
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    EquipmentCreate, 
    EquipmentPublic, 
    EquipmentUpdate
)
from app.crud.equipment import (
    create_equipment as crud_create_equipment,
    get_equipment as crud_get_equipment,
    list_equipment as crud_list_equipment,
    update_equipment as crud_update_equipment,
    delete_equipment as crud_delete_equipment,
)
from app.crud.greenhouses import get_greenhouse as crud_get_greenhouse

router = APIRouter(tags=["equipment"], prefix="/equipment")

@router.post("/", response_model=EquipmentPublic)
def create_equipment(
    e_in: EquipmentCreate,
    session: SessionDep
):
    # ensure parent greenhouse exists
    if not crud_get_greenhouse(session=session, id=e_in.greenhouse_id):
        raise HTTPException(status_code=404, detail="Parent greenhouse not found")
    return crud_create_equipment(session, e_in)

@router.get("/", response_model=List[EquipmentPublic])
def list_equipment(
    session: SessionDep
):
    return crud_list_equipment(session)

@router.get("/{equipment_id}", response_model=EquipmentPublic)
def get_equipment(
    equipment_id: uuid.UUID,
    session: SessionDep
):
    eq = crud_get_equipment(session, equipment_id)
    if not eq:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return eq

@router.patch("/{equipment_id}", response_model=EquipmentPublic)
def update_equipment(
    equipment_id: uuid.UUID,
    e_in: EquipmentUpdate,
    session: SessionDep
):
    eq = crud_get_equipment(session, equipment_id)
    if not eq:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return crud_update_equipment(session, eq, e_in)

@router.delete("/{equipment_id}")
def delete_equipment(
    equipment_id: uuid.UUID,
    session: SessionDep
):
    eq = crud_get_equipment(session, equipment_id)
    if not eq:
        raise HTTPException(status_code=404, detail="Equipment not found")
    crud_delete_equipment(session, eq)
    return {"ok": True}