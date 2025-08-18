import uuid

from sqlmodel import Session, and_, select

from app.api.permissions import ownership_or_membership_condition
from app.models import (
    Controller,
    Greenhouse,
    Sensor,
    SensorCreate,
    SensorKind,
    SensorUpdate,
    SensorZoneMap,
    Zone,
)
from app.utils_paging import PaginationParams, paginate_query


def create_sensor(session: Session, s_in: SensorCreate) -> Sensor:
    """Create a new sensor record."""
    data = s_in.model_dump()
    sensor = Sensor(**data)
    session.add(sensor)
    session.commit()
    session.refresh(sensor)
    return sensor


def get_sensor(session: Session, sensor_id: uuid.UUID) -> Sensor | None:
    """Retrieve a sensor by its ID."""
    return session.get(Sensor, sensor_id)


def validate_user_owns_sensor(
    session: Session, sensor_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Validate that a user owns the sensor through greenhouse ownership."""
    result = session.exec(
        select(Sensor)
        .join(Controller)
        .join(Greenhouse)
        .where(and_(Sensor.id == sensor_id, Greenhouse.user_id == user_id))
    ).first()
    return result is not None


def list_sensors(
    session: Session,
    user_id: uuid.UUID,
    pagination: PaginationParams,
    kind: SensorKind | None = None,
    controller_id: uuid.UUID | None = None,
    greenhouse_id: uuid.UUID | None = None,
    sort: str = "name",
):
    """List sensors with filtering and pagination using RBAC."""
    # Base query - join with controller and greenhouse for access validation
    query = select(Sensor).join(Controller).join(Greenhouse)

    # User access filter - users can see sensors in owned or shared greenhouses
    query = query.where(ownership_or_membership_condition(user_id))

    # Apply optional filters
    if kind:
        query = query.where(Sensor.kind == kind)
    if controller_id:
        query = query.where(Sensor.controller_id == controller_id)
    if greenhouse_id:
        query = query.where(Controller.greenhouse_id == greenhouse_id)

    # Apply sorting
    sort_desc = sort.startswith("-")
    sort_field = sort.lstrip("-")

    if sort_field == "name":
        order_col = Sensor.name
    elif sort_field == "kind":
        order_col = Sensor.kind
    elif sort_field == "created_at":
        # Assuming we have created_at field, if not we'll use id
        order_col = getattr(Sensor, "created_at", Sensor.id)
    else:
        order_col = Sensor.name  # Default

    if sort_desc:
        query = query.order_by(order_col.desc())
    else:
        query = query.order_by(order_col)

    return paginate_query(session, query, pagination)


def list_sensors_by_zone(session: Session, zone_id: uuid.UUID) -> list[Sensor]:
    """List all sensors mapped to a specific zone."""
    # Use a single joined query to avoid N+1 problem
    return session.exec(
        select(Sensor)
        .join(SensorZoneMap, SensorZoneMap.sensor_id == Sensor.id)
        .where(SensorZoneMap.zone_id == zone_id)
    ).all()


def list_sensors_by_controller(
    session: Session, controller_id: uuid.UUID
) -> list[Sensor]:
    """List all sensors in a specific controller."""
    return session.exec(
        select(Sensor).where(Sensor.controller_id == controller_id)
    ).all()


def list_sensors_by_greenhouse(
    session: Session, greenhouse_id: uuid.UUID
) -> list[Sensor]:
    """List all sensors for a specific greenhouse through its controllers."""
    return session.exec(
        select(Sensor).join(Controller).where(Controller.greenhouse_id == greenhouse_id)
    ).all()


def update_sensor(session: Session, sensor: Sensor, s_in: SensorUpdate) -> Sensor:
    """Update fields on an existing sensor."""
    update_data = s_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(sensor, key, value)
    session.add(sensor)
    session.commit()
    session.refresh(sensor)
    return sensor


def delete_sensor(session: Session, sensor: Sensor) -> None:
    """Delete a sensor record."""
    # First, remove all zone mappings for this sensor
    sensor_mappings = session.exec(
        select(SensorZoneMap).where(SensorZoneMap.sensor_id == sensor.id)
    ).all()

    # Delete all mappings
    for mapping in sensor_mappings:
        session.delete(mapping)

    # Commit the unmapping changes first
    session.commit()

    # Now delete the sensor
    session.delete(sensor)
    session.commit()


def list_available_sensors(
    session: Session, greenhouse_id: uuid.UUID, sensor_type: SensorKind
) -> list[Sensor]:
    """List all sensors of a specific type in a greenhouse."""
    # Now returns all sensors since they can be mapped to multiple zones
    all_sensors = session.exec(
        select(Sensor)
        .join(Controller)
        .where(Controller.greenhouse_id == greenhouse_id, Sensor.kind == sensor_type)
    ).all()

    return all_sensors


def map_sensor_to_zone(
    session: Session, zone_id: uuid.UUID, sensor_id: uuid.UUID, sensor_type: SensorKind
) -> SensorZoneMap:
    """Map a sensor to a zone for a specific type using SensorZoneMap."""
    zone = session.get(Zone, zone_id)
    if not zone:
        raise ValueError("Zone not found")

    sensor = session.get(Sensor, sensor_id)
    if not sensor or sensor.kind != sensor_type:
        raise ValueError("Invalid sensor for this type")

    # Check if this exact mapping already exists
    existing_mapping = session.exec(
        select(SensorZoneMap).where(
            and_(
                SensorZoneMap.zone_id == zone_id,
                SensorZoneMap.sensor_id == sensor_id,
                SensorZoneMap.kind == sensor_type,
            )
        )
    ).first()

    if existing_mapping:
        raise ValueError(
            f"Sensor is already mapped to this zone for {sensor_type.value}"
        )

    # Check if zone already has a sensor of this type mapped
    existing_type_mapping = session.exec(
        select(SensorZoneMap).where(
            and_(SensorZoneMap.zone_id == zone_id, SensorZoneMap.kind == sensor_type)
        )
    ).first()

    if existing_type_mapping:
        raise ValueError(
            f"Zone already has a {sensor_type.value} sensor mapped. Please unmap the existing sensor first."
        )

    # Create the mapping
    mapping = SensorZoneMap(sensor_id=sensor_id, zone_id=zone_id, kind=sensor_type)

    session.add(mapping)
    session.commit()
    session.refresh(mapping)
    return mapping


def unmap_sensor_from_zone(
    session: Session, zone_id: uuid.UUID, sensor_type: SensorKind
) -> bool:
    """Remove sensor mapping from a zone for a specific type using SensorZoneMap."""
    zone = session.get(Zone, zone_id)
    if not zone:
        raise ValueError("Zone not found")

    # Find the mapping to remove
    mapping = session.exec(
        select(SensorZoneMap).where(
            and_(SensorZoneMap.zone_id == zone_id, SensorZoneMap.kind == sensor_type)
        )
    ).first()

    if not mapping:
        return False  # No mapping found to remove

    session.delete(mapping)
    session.commit()
    return True


def list_unmapped_sensors_by_greenhouse(
    session: Session, greenhouse_id: uuid.UUID
) -> list[Sensor]:
    """List sensors that are not mapped to any zones in a specific greenhouse."""
    return session.exec(
        select(Sensor)
        .join(Controller, Controller.id == Sensor.controller_id)
        .outerjoin(SensorZoneMap, SensorZoneMap.sensor_id == Sensor.id)
        .where(
            Controller.greenhouse_id == greenhouse_id, SensorZoneMap.sensor_id.is_(None)
        )
    ).all()
