from datetime import datetime, timedelta
from typing import List
from sqlalchemy import delete
from sqlmodel import Session, select
import uuid
from statistics import mean

from app.models import (
    Zone,
    Greenhouse,
    ZoneClimateHistory,
    GreenhouseClimateHistory,
)

def record_zone_climate(
    session: Session,
    zone_id: uuid.UUID,
    temperature: float,
    humidity: float,
) -> ZoneClimateHistory:
    """Record a new climate reading for a zone."""
    reading = ZoneClimateHistory(
        zone_id=zone_id,
        temperature=temperature,
        humidity=humidity,
    )
    session.add(reading)
    session.commit()
    session.refresh(reading)
    return reading

def record_greenhouse_climate(
    session: Session,
    greenhouse_id: uuid.UUID,
) -> GreenhouseClimateHistory:
    """Calculate and record mean climate for a greenhouse."""
    # Get all zones for this greenhouse
    zones = session.exec(
        select(Zone).where(Zone.greenhouse_id == greenhouse_id)
    ).all()
    
    # Get latest readings from each zone
    zone_readings = []
    for zone in zones:
        latest = session.exec(
            select(ZoneClimateHistory)
            .where(ZoneClimateHistory.zone_id == zone.id)
            .order_by(ZoneClimateHistory.timestamp.desc())
        ).first()
        if latest:
            zone_readings.append(latest)
    
    if not zone_readings:
        return None

    # Calculate means
    mean_temp = mean(r.temperature for r in zone_readings)
    mean_humidity = mean(r.humidity for r in zone_readings)
    
    # Get greenhouse for outside readings
    greenhouse = session.get(Greenhouse, greenhouse_id)
    
    # Create and store reading
    reading = GreenhouseClimateHistory(
        greenhouse_id=greenhouse_id,
        temperature=mean_temp,
        humidity=mean_humidity,
        outside_temperature=greenhouse.outside_temperature,
        outside_humidity=greenhouse.outside_humidity,
    )
    session.add(reading)
    session.commit()
    session.refresh(reading)
    return reading

def get_zone_climate_history(
    session: Session,
    zone_id: uuid.UUID,
    hours: int = 24,
) -> List[ZoneClimateHistory]:
    """Get climate history for a zone for the specified time period."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    return session.exec(
        select(ZoneClimateHistory)
        .where(ZoneClimateHistory.zone_id == zone_id)
        .where(ZoneClimateHistory.timestamp > cutoff)
        .order_by(ZoneClimateHistory.timestamp)
    ).all()

def get_greenhouse_climate_history(
    session: Session,
    greenhouse_id: uuid.UUID,
    hours: int = 24,
) -> List[GreenhouseClimateHistory]:
    """Get climate history for a greenhouse for the specified time period."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    return session.exec(
        select(GreenhouseClimateHistory)
        .where(GreenhouseClimateHistory.greenhouse_id == greenhouse_id)
        .where(GreenhouseClimateHistory.timestamp > cutoff)
        .order_by(GreenhouseClimateHistory.timestamp)
    ).all()

def cleanup_old_readings(
    session: Session,
    days: int = 30,
) -> None:
    """Remove readings older than specified days."""
    cutoff = datetime.now(datetime.timezone.utc) - timedelta(days=days)
    
    session.exec(
        delete(ZoneClimateHistory)
        .where(ZoneClimateHistory.timestamp < cutoff)
    )
    
    session.exec(
        delete(GreenhouseClimateHistory)
        .where(GreenhouseClimateHistory.timestamp < cutoff)
    )
    
    session.commit()
