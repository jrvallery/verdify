import uuid
from typing import List
from statistics import mean

from fastapi import APIRouter, HTTPException, status
from sqlmodel import func, select
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    Zone,
    ZoneCreate,
    ZonePublic,
    ZoneUpdate,
    Message,
    SensorPublic,
    ZoneSensorMap,
    SensorType,
)
from app.crud.zone import (
    create_zone as crud_create_zone,
    list_zones as crud_list_zones,
    get_zone as crud_get_zone,
    update_zone as crud_update_zone,
)
from app.crud.greenhouses import get_greenhouse as crud_get_greenhouse
from app.crud.sensors import (
    list_sensors_by_zone as crud_list_sensors_by_zone,
    map_sensor_to_zone,
    unmap_sensor_from_zone,
)

router = APIRouter()

@router.post("/", response_model=ZonePublic)
def create_zone(
    greenhouse_id: uuid.UUID,  # From URL path
    z_in: ZoneCreate,
    session: SessionDep,
    current_user: CurrentUser
) -> ZonePublic:
    # Verify user owns this greenhouse
    greenhouse = crud_get_greenhouse(session=session, id=greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Greenhouse not found")
    if not (current_user.is_superuser or greenhouse.owner_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    # Override greenhouse_id from URL path (ensures consistency)
    z_in.greenhouse_id = greenhouse_id
    return crud_create_zone(session, z_in)


@router.get("/", response_model=List[ZonePublic])
def list_zones(
    greenhouse_id: uuid.UUID,  # From URL path
    session: SessionDep,
    current_user: CurrentUser
) -> List[ZonePublic]:
    # Verify user owns this greenhouse
    greenhouse = crud_get_greenhouse(session=session, id=greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Greenhouse not found")
    if not (current_user.is_superuser or greenhouse.owner_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    # Return zones ONLY for this specific greenhouse
    return crud_list_zones(session, greenhouse_id)

@router.get("/{zone_id}", response_model=ZonePublic)
def get_zone(
    greenhouse_id: uuid.UUID,  # From URL path
    zone_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser
):
    zone = crud_get_zone(session, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    
    # Verify zone belongs to the greenhouse in the URL
    if zone.greenhouse_id != greenhouse_id:
        raise HTTPException(status_code=404, detail="Zone not found in this greenhouse")
    
    if not (current_user.is_superuser or zone.greenhouse.owner_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return zone

@router.patch("/{zone_id}", response_model=ZonePublic)
def update_zone(
    greenhouse_id: uuid.UUID,  # From URL path
    zone_id: uuid.UUID,
    z_in: ZoneUpdate,
    session: SessionDep,
    current_user: CurrentUser
) -> ZonePublic:
    zone = crud_get_zone(session, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    
    # Verify zone belongs to the greenhouse in the URL
    if zone.greenhouse_id != greenhouse_id:
        raise HTTPException(status_code=404, detail="Zone not found in this greenhouse")
    
    if not (current_user.is_superuser or zone.greenhouse.owner_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return crud_update_zone(session, zone, z_in)

@router.delete("/{zone_id}", response_model=Message)
def delete_zone(
    *,
    greenhouse_id: uuid.UUID,  # From URL path
    session: SessionDep,
    current_user: CurrentUser,
    zone_id: uuid.UUID,
) -> Message:
    zone = session.get(Zone, zone_id)
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    
    # Verify zone belongs to the greenhouse in the URL
    if zone.greenhouse_id != greenhouse_id:
        raise HTTPException(status_code=404, detail="Zone not found in this greenhouse")
    
    if not (current_user.is_superuser or zone.greenhouse.owner_id == current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    session.delete(zone)
    session.commit()
    return Message(message="Zone deleted successfully")


@router.get("/{zone_id}/sensors", response_model=List[SensorPublic])
def list_zone_sensors(
    zone_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser
):
    """List all sensors mapped to a specific zone."""
    zone = crud_get_zone(session, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    
    if not (current_user.is_superuser or zone.greenhouse.owner_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    return crud_list_sensors_by_zone(session, zone_id)


@router.post("/{zone_id}/map-sensor", response_model=ZonePublic)
def map_sensor_to_zone_endpoint(
    zone_id: uuid.UUID,
    sensor_map: ZoneSensorMap,
    session: SessionDep,
    current_user: CurrentUser
):
    """Map a sensor to a zone for a specific type."""
    zone = crud_get_zone(session, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    
    if not (current_user.is_superuser or zone.greenhouse.owner_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    try:
        return map_sensor_to_zone(session, zone_id, sensor_map.sensor_id, sensor_map.type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{zone_id}/unmap-sensor/{sensor_type}", response_model=ZonePublic)
def unmap_sensor_from_zone_endpoint(
    zone_id: uuid.UUID,
    sensor_type: SensorType,
    session: SessionDep,
    current_user: CurrentUser
):
    """Remove sensor mapping from a zone for a specific type."""
    zone = crud_get_zone(session, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    
    if not (current_user.is_superuser or zone.greenhouse.owner_id == current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    try:
        return unmap_sensor_from_zone(session, zone_id, sensor_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))