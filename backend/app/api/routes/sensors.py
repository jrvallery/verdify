import uuid
from typing import List

from fastapi import APIRouter, HTTPException
from app.api.deps import SessionDep
from app.models import SensorCreate, SensorPublic, SensorUpdate
from app.crud.sensors import (
    create_sensor as crud_create_sensor,
    get_sensor as crud_get_sensor,
    list_sensors_by_zone as crud_list_sensors_by_zone,
    update_sensor as crud_update_sensor,
    delete_sensor as crud_delete_sensor,
)
from app.crud.zone import get_zone as crud_get_zone

router = APIRouter()

@router.post("/", response_model=SensorPublic)
def create_sensor(
    s_in: SensorCreate,
    session: SessionDep
):
    if not crud_get_zone(session=session, zone_id=s_in.zone_id):
        raise HTTPException(status_code=404, detail="Zone not found")
    return crud_create_sensor(session, s_in)

@router.get("/", response_model=List[SensorPublic])
def list_sensors(
    zone_id: uuid.UUID,
    session: SessionDep
):
    if not crud_get_zone(session=session, zone_id=zone_id):
        raise HTTPException(status_code=404, detail="Zone not found")
    return crud_list_sensors_by_zone(session, zone_id)

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
