import uuid

from sqlmodel import Session, and_, select

from app.models import SensorKind, SensorZoneMap, SensorZoneMapCreate


def create_sensor_zone_map(
    session: Session, map_in: SensorZoneMapCreate
) -> SensorZoneMap:
    """Create a new sensor zone mapping."""
    # Check if mapping already exists
    existing = session.exec(
        select(SensorZoneMap).where(
            and_(
                SensorZoneMap.sensor_id == map_in.sensor_id,
                SensorZoneMap.zone_id == map_in.zone_id,
                SensorZoneMap.kind == map_in.kind,
            )
        )
    ).first()

    if existing:
        raise ValueError(
            f"Sensor zone mapping already exists for sensor {map_in.sensor_id}, zone {map_in.zone_id}, kind {map_in.kind}"
        )

    # Create new mapping
    data = map_in.model_dump()
    mapping = SensorZoneMap(**data)
    session.add(mapping)
    session.commit()
    session.refresh(mapping)
    return mapping


def delete_sensor_zone_map(
    session: Session, sensor_id: uuid.UUID, zone_id: uuid.UUID, kind: SensorKind
) -> None:
    """Delete a sensor zone mapping."""
    mapping = session.exec(
        select(SensorZoneMap).where(
            and_(
                SensorZoneMap.sensor_id == sensor_id,
                SensorZoneMap.zone_id == zone_id,
                SensorZoneMap.kind == kind,
            )
        )
    ).first()

    if not mapping:
        raise ValueError(
            f"Sensor zone mapping not found for sensor {sensor_id}, zone {zone_id}, kind {kind}"
        )

    session.delete(mapping)
    session.commit()


def get_sensor_zone_mappings_by_sensor(
    session: Session, sensor_id: uuid.UUID
) -> list[SensorZoneMap]:
    """Get all zone mappings for a sensor."""
    return session.exec(
        select(SensorZoneMap).where(SensorZoneMap.sensor_id == sensor_id)
    ).all()


def get_sensor_zone_mappings_by_zone(
    session: Session, zone_id: uuid.UUID
) -> list[SensorZoneMap]:
    """Get all sensor mappings for a zone."""
    return session.exec(
        select(SensorZoneMap).where(SensorZoneMap.zone_id == zone_id)
    ).all()
