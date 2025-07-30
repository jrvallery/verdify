from typing import List
from sqlmodel import Session, select
import uuid

from app.models import Sensor, SensorCreate, SensorUpdate

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
    """List all sensors in a specific zone."""
    return session.exec(select(Sensor).where(Sensor.zone_id == zone_id)).all()

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
    session.delete(sensor)
    session.commit()
