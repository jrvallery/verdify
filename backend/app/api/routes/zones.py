import uuid
from typing import List
from statistics import mean

from fastapi import APIRouter, HTTPException, status
from sqlmodel import func, select
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    Zone,
    ZoneReading,
    ZoneCreate,
    ZonePublic,
    ZoneUpdate,
    Message,
)
from app.crud.zone import (
    create_zone as crud_create_zone,
    list_zones as crud_list_zones,
    get_zone as crud_get_zone,
    update_zone as crud_update_zone,
)
from app.crud.greenhouses import get_greenhouse as crud_get_greenhouse
from app.crud.sensors import list_sensors_by_zone

router = APIRouter()

@router.post("/", response_model=ZonePublic)
def create_zone(
    z_in: ZoneCreate,
    session: SessionDep
) -> ZonePublic:
    # ensure parent greenhouse exists
    if not crud_get_greenhouse(session=session, id=z_in.greenhouse_id):
        raise HTTPException(status_code=404, detail="Parent greenhouse not found")
    return crud_create_zone(session, z_in)


@router.get("/", response_model=List[ZonePublic])
def list_zones(
    session: SessionDep
) -> List[ZonePublic]:
    return crud_list_zones(session)


@router.get("/{zone_id}", response_model=ZonePublic)
def get_zone(
    zone_id: uuid.UUID,
    session: SessionDep
):
    zone = crud_get_zone(session, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    return zone

@router.patch("/{zone_id}", response_model=ZonePublic)
def update_zone(
    zone_id: uuid.UUID,
    z_in: ZoneUpdate,
    session: SessionDep
) -> ZonePublic:
    zone = crud_get_zone(session, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    return crud_update_zone(session, zone, z_in)


@router.delete("/{zone_id}", response_model=Message)
def delete_zone(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    zone_id: uuid.UUID,
) -> Message:
    zone = session.get(Zone, zone_id)
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    if not (current_user.is_superuser or zone.owner_id == current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    session.delete(zone)
    session.commit()
    return Message(message="Zone deleted successfully")

@router.put("/{zone_id}/updateReadings", response_model=ZoneReading)
def update_zone_readings(
    zone_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> ZoneReading:
    zone = session.get(Zone, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    if not (current_user.is_superuser or zone.greenhouse.owner_id == current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    
    # Get all sensors for this zone
    sensors = list_sensors_by_zone(session, zone_id)
    
    # Filter sensors by type and get their readings
    temp_readings = [s.value for s in sensors if s.type == "temperature" and s.value is not None]
    humidity_readings = [s.value for s in sensors if s.type == "humidity" and s.value is not None]
    
    # Calculate averages if readings exist
    if not temp_readings and not humidity_readings:
        raise HTTPException(status_code=404, detail="No sensor readings available")
    
    # Update zone with new readings
    if temp_readings:
        zone.temperature = mean(temp_readings)
    if humidity_readings:
        zone.humidity = mean(humidity_readings)
    
    # Save changes
    session.add(zone)
    session.commit()
    session.refresh(zone)
    
    # Create and store reading history
    reading = ZoneReading(
        zone_id=zone_id,
        temperature=zone.temperature,
        humidity=zone.humidity
    )
    session.add(reading)
    session.commit()
    
    return reading

@router.get("/{zone_id}/reading", response_model=ZoneReading)
def get_zone_reading(
    zone_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> ZoneReading:
    zone = session.get(Zone, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    if not (current_user.is_superuser or zone.greenhouse.owner_id == current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    temp = zone.temperature
    humidity = zone.humidity
    if temp is None or humidity is None:
        raise HTTPException(status_code=404, detail="Zone readings not available")
    return ZoneReading(temperature=temp ,humidity=humidity)

@router.get("/{zone_id}/readings", response_model=List[ZoneReading])
def get_zone_readings(zone_id: uuid.UUID, session: SessionDep) -> List[ZoneReading]:
    """Get all readings for a specific zone."""
    return session.exec(select(ZoneReading).where(ZoneReading.zone_id == zone_id)).all()