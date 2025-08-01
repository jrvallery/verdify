from typing import List
from sqlmodel import Session, select
import uuid

from app.models import Zone, ZoneCreate, ZoneUpdate

def create_zone(session: Session, z_in: ZoneCreate) -> Zone:
    """
    Create a new Zone record.
    """
    # Use model_dump() (Pydantic v2) instead of dict()
    zone_data = z_in.model_dump()
    zone = Zone(**zone_data)
    session.add(zone)
    session.commit()
    session.refresh(zone)
    return zone

def get_zone(session: Session, zone_id: uuid.UUID) -> Zone | None:
    """
    Retrieve a Zone by its ID.
    """
    return session.get(Zone, zone_id)

def list_zones(session: Session, greenhouse_id: uuid.UUID | None = None) -> List[Zone]:
    """
    List zones, optionally filtered by greenhouse.
    """
    if greenhouse_id:
        return session.exec(select(Zone).where(Zone.greenhouse_id == greenhouse_id)).all()
    return session.exec(select(Zone)).all()

def update_zone(session: Session, zone: Zone, z_in: ZoneUpdate) -> Zone:
    """
    Update fields on an existing Zone.
    """
    # Only include fields that were actually set
    update_data = z_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(zone, key, value)
    session.add(zone)
    session.commit()
    session.refresh(zone)
    return zone

def delete_zone(session: Session, zone: Zone) -> None:
    """
    Delete a Zone record.
    """
    session.delete(zone)
    session.commit()