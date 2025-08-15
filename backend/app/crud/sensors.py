from typing import List, Optional, Union
from uuid import UUID
from sqlmodel import Session, select
import uuid
from enum import Enum

from app.models import Sensor, SensorCreate, SensorUpdate, Zone, SensorType, Controller

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

def list_sensors_by_zone(session: Session, zone_id: uuid.UUID) -> List[Sensor]:
    """List all sensors mapped to a specific zone."""
    zone = session.get(Zone, zone_id)
    if not zone:
        return []
    
    sensors = []
    for sensor_type in SensorType:
        sensor_id = getattr(zone, f"{sensor_type.value}_sensor_id")
        if sensor_id:
            sensor = session.get(Sensor, sensor_id)
            if sensor:
                sensors.append(sensor)
    return sensors

def list_sensors_by_controller(session: Session, controller_id: uuid.UUID) -> List[Sensor]:
    """List all sensors in a specific controller."""
    return session.exec(select(Sensor).where(Sensor.controller_id == controller_id)).all()

def list_sensors_by_greenhouse(session: Session, greenhouse_id: uuid.UUID) -> List[Sensor]:
    """List all sensors for a specific greenhouse through its controllers."""
    return session.exec(
        select(Sensor)
        .join(Controller)
        .where(Controller.greenhouse_id == greenhouse_id)
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
    # First, unmap the sensor from any zones it's mapped to
    for sensor_type in SensorType:
        sensor_field = f"{sensor_type.value}_sensor_id"
        # Query for zones that have this sensor mapped for this type
        zones_with_sensor = session.exec(
            select(Zone).where(getattr(Zone, sensor_field) == sensor.id)
        ).all()
        
        # Unmap the sensor from these zones
        for zone in zones_with_sensor:
            setattr(zone, sensor_field, None)
            session.add(zone)
    
    # Commit the unmapping changes first
    session.commit()
    
    # Now delete the sensor
    session.delete(sensor)
    session.commit()

def list_available_sensors(
    session: Session,
    greenhouse_id: uuid.UUID,
    sensor_type: SensorType
) -> List[Sensor]:
    """List all sensors of a specific type in a greenhouse."""
    # Now returns all sensors since they can be mapped to multiple zones
    all_sensors = session.exec(
        select(Sensor)
        .join(Controller)
        .where(
            Controller.greenhouse_id == greenhouse_id,
            Sensor.kind == sensor_type.value
        )
    ).all()
    
    return all_sensors

def map_sensor_to_zone(session: Session, zone_id: Union[UUID, str], sensor_id: Union[UUID, str], sensor_type):
    # Normalize enum -> string
    requested_type = sensor_type.value if isinstance(sensor_type, Enum) else str(sensor_type)

    zone = session.get(Zone, zone_id)
    if not zone:
        raise ValueError("Zone not found")

    sensor = session.get(Sensor, sensor_id)
    if not sensor:
        raise ValueError("Sensor not found")

    # Validate kind matches requested type
    if sensor.kind != requested_type:
        raise ValueError(f"Sensor kind mismatch: expected {requested_type}, got {sensor.kind}")

    # Map kind -> zone FK field
    field_map = {
        "temperature": "temperature_sensor_id",
        "humidity": "humidity_sensor_id",
        "co2": "co2_sensor_id",
        "light": "light_sensor_id",
        "soil_moisture": "soil_moisture_sensor_id",
    }
    fk_field = field_map.get(requested_type)
    if not fk_field:
        raise ValueError(f"Unsupported sensor type: {requested_type}")

    setattr(zone, fk_field, sensor.id)
    session.add(zone)
    session.commit()
    session.refresh(zone)
    return zone

def unmap_sensor_from_zone(
    session: Session,
    zone_id: uuid.UUID,
    sensor_type: SensorType
) -> Zone:
    """Remove sensor mapping from a zone for a specific type."""
    zone = session.get(Zone, zone_id)
    if not zone:
        raise ValueError("Zone not found")
    
    # Simply remove the sensor mapping from this zone
    setattr(zone, f"{sensor_type.value}_sensor_id", None)
    
    session.add(zone)
    session.commit()
    session.refresh(zone)
    return zone

def list_unmapped_sensors_by_greenhouse(session: Session, greenhouse_id: uuid.UUID) -> List[Sensor]:
    """List all sensors for a specific greenhouse."""
    # Since sensors can now be mapped to multiple zones, this returns all sensors
    return session.exec(
        select(Sensor)
        .join(Controller)
        .where(
            Controller.greenhouse_id == greenhouse_id,
        )
    ).all()
