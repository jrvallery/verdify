import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, SessionDep
from app.crud.controller import get_controller as crud_get_controller
from app.crud.sensors import (
    create_sensor as crud_create_sensor,
)
from app.crud.sensors import (
    delete_sensor as crud_delete_sensor,
)
from app.crud.sensors import (
    get_sensor as crud_get_sensor,
)
from app.crud.sensors import (
    list_sensors,
    validate_user_owns_sensor,
)
from app.crud.sensors import (
    update_sensor as crud_update_sensor,
)
from app.models import (
    SensorCreate,
    SensorKind,
    SensorPublic,
    SensorsPaginated,
    SensorUpdate,
)
from app.utils_paging import PaginationParams

router = APIRouter()


@router.get("/", response_model=SensorsPaginated)
def list_sensors_endpoint(
    session: SessionDep,
    current_user: CurrentUser,
    kind: SensorKind | None = Query(None, description="Filter by sensor kind"),
    controller_id: uuid.UUID | None = Query(
        None, description="Filter by controller ID"
    ),
    greenhouse_id: uuid.UUID | None = Query(
        None, description="Filter by greenhouse ID"
    ),
    sort: str = Query("name", description="Sort field and direction"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
) -> SensorsPaginated:
    """List sensors with optional filtering."""
    pagination = PaginationParams(page=page, page_size=page_size)
    return list_sensors(
        session=session,
        user_id=current_user.id,
        pagination=pagination,
        kind=kind,
        controller_id=controller_id,
        greenhouse_id=greenhouse_id,
        sort=sort,
    )


@router.post("/", response_model=SensorPublic, status_code=status.HTTP_201_CREATED)
def create_sensor(
    s_in: SensorCreate,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Create a new sensor."""
    # Validate controller exists and user owns it
    controller = crud_get_controller(session, s_in.controller_id)
    if not controller:
        raise HTTPException(status_code=404, detail="Controller not found")
    if not (
        current_user.is_superuser or controller.greenhouse.user_id == current_user.id
    ):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    return crud_create_sensor(session, s_in)


@router.get("/{sensor_id}", response_model=SensorPublic)
def get_sensor(
    sensor_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Get sensor by ID."""
    sensor = crud_get_sensor(session, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")

    # Validate user owns this sensor
    if not validate_user_owns_sensor(session, sensor_id, current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    return sensor


@router.patch("/{sensor_id}", response_model=SensorPublic)
def update_sensor(
    sensor_id: uuid.UUID,
    s_in: SensorUpdate,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Update sensor."""
    sensor = crud_get_sensor(session, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")

    # Validate user owns this sensor
    if not validate_user_owns_sensor(session, sensor_id, current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    return crud_update_sensor(session, sensor, s_in)


@router.delete("/{sensor_id}")
def delete_sensor(
    sensor_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Delete sensor."""
    sensor = crud_get_sensor(session, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")

    # Validate user owns this sensor
    if not validate_user_owns_sensor(session, sensor_id, current_user.id):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    crud_delete_sensor(session, sensor)
    return {"ok": True}
