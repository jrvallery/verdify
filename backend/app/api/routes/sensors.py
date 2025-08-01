import uuid
from typing import List

from fastapi import APIRouter, HTTPException
from app.api.deps import SessionDep, CurrentUser
from app.models import SensorCreate, SensorPublic, SensorUpdate, ZoneSensorMap, SensorType, Zone
from app.crud.sensors import (
    create_sensor as crud_create_sensor,
    get_sensor as crud_get_sensor,
    list_sensors_by_zone as crud_list_sensors_by_zone,
    update_sensor as crud_update_sensor,
    delete_sensor as crud_delete_sensor,
    list_available_sensors,
)
from app.crud.zone import get_zone as crud_get_zone
from app.crud.greenhouses import get_greenhouse as crud_get_greenhouse
from app.crud.sensors import map_sensor_to_zone, unmap_sensor_from_zone
from app.crud.controller import get_controller as crud_get_controller
from app.crud.sensors import list_sensors_by_controller

router = APIRouter()


@router.post("/", response_model=SensorPublic)
def create_sensor(
    controller_id: uuid.UUID,  # Now comes from path
    s_in: SensorCreate,
    session: SessionDep,
    current_user: CurrentUser
):
    """Create a new sensor under a controller."""
    controller = crud_get_controller(session, controller_id)
    if not controller:
        raise HTTPException(status_code=404, detail="Controller not found")
    if not (current_user.is_superuser or controller.greenhouse.owner_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    sensor_data = s_in.model_dump()
    sensor_data["controller_id"] = controller_id
    return crud_create_sensor(session, SensorCreate(**sensor_data))


@router.get("/", response_model=List[SensorPublic])
def list_sensors(
    controller_id: uuid.UUID,
    session: SessionDep
):
    if not crud_get_controller(session=session, controller_id=controller_id):
        raise HTTPException(status_code=404, detail="Controller not found")
    return list_sensors_by_controller(session, controller_id)  # Fixed function call


@router.get("/{sensor_id}", response_model=SensorPublic)
def get_sensor(
    sensor_id: uuid.UUID,
    session: SessionDep
):
    sensor = crud_get_sensor(session, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return sensor


@router.patch("/{sensor_id}", response_model=SensorPublic)
def update_sensor(
    sensor_id: uuid.UUID,
    s_in: SensorUpdate,
    session: SessionDep
):
    sensor = crud_get_sensor(session, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return crud_update_sensor(session, sensor, s_in)


@router.delete("/{sensor_id}")
def delete_sensor(
    sensor_id: uuid.UUID,
    session: SessionDep
):
    sensor = crud_get_sensor(session, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    crud_delete_sensor(session, sensor)
    return {"ok": True}
