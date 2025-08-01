from typing import List, Optional
from sqlmodel import Session, select
import uuid

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
    if sensor.is_mapped:
        # Find zones that reference this sensor
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
        
        # Update the sensor's mapped status
        sensor.is_mapped = False
        session.add(sensor)
        
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
    """List all sensors of a specific type in a greenhouse that aren't mapped to any zone."""
    # Get all sensors of the specified type in the greenhouse
    all_sensors = session.exec(
        select(Sensor)
        .join(Controller)
        .where(
            Controller.greenhouse_id == greenhouse_id,
            Sensor.type == sensor_type
        )
    ).all()
    
    # Filter out sensors that are mapped (using the is_mapped field)
    available_sensors = [sensor for sensor in all_sensors if not sensor.is_mapped]
    
    return available_sensors

def map_sensor_to_zone(
    session: Session,
    zone_id: uuid.UUID,
    sensor_id: uuid.UUID,
    sensor_type: SensorType
) -> Zone:
    """Map a sensor to a zone for a specific type."""
    zone = session.get(Zone, zone_id)
    if not zone:
        raise ValueError("Zone not found")
    
    sensor = session.get(Sensor, sensor_id)
    if not sensor or sensor.type != sensor_type:
        raise ValueError("Invalid sensor for this type")
    
    # Check if this sensor type slot is already occupied
    current_sensor_id = getattr(zone, f"{sensor_type.value}_sensor_id")
    if current_sensor_id is not None:
        raise ValueError(f"Zone already has a {sensor_type.value} sensor mapped. Please unmap the existing sensor first.")
    
    # Check if the sensor is already mapped to another zone
    if sensor.is_mapped:
        raise ValueError("Sensor is already mapped to another zone")
    
    setattr(zone, f"{sensor_type.value}_sensor_id", sensor_id)
    
    # Mark sensor as mapped
    sensor.is_mapped = True
    session.add(sensor)
    
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
    
    # Get the sensor that's being unmapped and mark it as unmapped
    sensor_id = getattr(zone, f"{sensor_type.value}_sensor_id")
    if sensor_id:
        sensor = session.get(Sensor, sensor_id)
        if sensor:
            sensor.is_mapped = False
            session.add(sensor)
    
    setattr(zone, f"{sensor_type.value}_sensor_id", None)
    
    session.add(zone)
    session.commit()
    session.refresh(zone)
    return zone

def list_unmapped_sensors_by_greenhouse(session: Session, greenhouse_id: uuid.UUID) -> List[Sensor]:
    """List all unmapped sensors for a specific greenhouse."""
    return session.exec(
        select(Sensor)
        .join(Controller)
        .where(
            Controller.greenhouse_id == greenhouse_id,
            Sensor.is_mapped == False
        )
    ).all()
