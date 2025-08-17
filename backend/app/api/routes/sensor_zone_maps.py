import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session, and_, select

from app.api.deps import CurrentUser, SessionDep
from app.crud.sensor_zone_map import (
    create_sensor_zone_map as crud_create_sensor_zone_map,
)
from app.crud.sensor_zone_map import (
    delete_sensor_zone_map as crud_delete_sensor_zone_map,
)
from app.models import (
    Controller,
    Greenhouse,
    Sensor,
    SensorKind,
    SensorZoneMapCreate,
    SensorZoneMapPublic,
    Zone,
)

router = APIRouter()


def validate_user_owns_sensor_and_zone(
    session: Session, sensor_id: uuid.UUID, zone_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Validate that user owns both the sensor and zone through greenhouse ownership."""
    # Check sensor ownership
    sensor_result = session.exec(
        select(Sensor)
        .join(Controller)
        .join(Greenhouse)
        .where(and_(Sensor.id == sensor_id, Greenhouse.user_id == user_id))
    ).first()

    # Check zone ownership
    zone_result = session.exec(
        select(Zone)
        .join(Greenhouse)
        .where(and_(Zone.id == zone_id, Greenhouse.user_id == user_id))
    ).first()

    return sensor_result is not None and zone_result is not None


@router.post("/", response_model=SensorZoneMapPublic, status_code=201)
def create_sensor_zone_map(
    map_in: SensorZoneMapCreate,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Map a sensor to a zone (multi-zone supported)."""
    # Validate user owns both sensor and zone
    if not validate_user_owns_sensor_and_zone(
        session, map_in.sensor_id, map_in.zone_id, current_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="Not enough permissions - you must own both the sensor and zone",
        )

    try:
        return crud_create_sensor_zone_map(session, map_in)
    except ValueError as e:
        if "already exists" in str(e).lower():
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/", status_code=204)
def delete_sensor_zone_map(
    sensor_id: uuid.UUID = Query(..., description="Sensor ID"),
    zone_id: uuid.UUID = Query(..., description="Zone ID"),
    kind: SensorKind = Query(..., description="Sensor kind"),
    session: SessionDep = ...,
    current_user: CurrentUser = ...,
):
    """Unmap a sensor from a zone."""
    # Validate user owns both sensor and zone
    if not validate_user_owns_sensor_and_zone(
        session, sensor_id, zone_id, current_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="Not enough permissions - you must own both the sensor and zone",
        )

    try:
        crud_delete_sensor_zone_map(session, sensor_id, zone_id, kind)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
