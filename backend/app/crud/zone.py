import uuid

from sqlmodel import Session, desc, select

from app.models import Greenhouse, Zone, ZoneCreate, ZoneUpdate


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


def list_zones(
    session: Session,
    greenhouse_id: uuid.UUID | None = None,
    is_active: bool | None = None,
    sort: str = "zone_number",
    skip: int = 0,
    limit: int = 100,
) -> list[Zone]:
    """
    List zones with filtering and sorting.

    Args:
        session: Database session
        greenhouse_id: Filter by greenhouse ID
        is_active: Filter by active status (ignored for now - not in model)
        sort: Sort field and direction (e.g., "zone_number", "-zone_number")
        skip: Number of records to skip (for pagination)
        limit: Maximum number of records to return
    """
    stmt = select(Zone)

    # Apply filters
    if greenhouse_id:
        stmt = stmt.where(Zone.greenhouse_id == greenhouse_id)

    # Note: is_active filter is ignored as this field is not currently modeled
    # in Zone table. This is documented as per task constraint.

    # Apply sorting
    sort_field = sort.lstrip("-")
    is_desc = sort.startswith("-")

    if sort_field == "zone_number":
        stmt = stmt.order_by(desc(Zone.zone_number) if is_desc else Zone.zone_number)
    elif sort_field == "title":
        # Note: Zone doesn't have a title field, fallback to zone_number
        stmt = stmt.order_by(desc(Zone.zone_number) if is_desc else Zone.zone_number)
    elif sort_field == "created_at":
        # Zone model doesn't have created_at, fallback to zone_number
        stmt = stmt.order_by(desc(Zone.zone_number) if is_desc else Zone.zone_number)
    else:
        # Default to zone_number
        stmt = stmt.order_by(Zone.zone_number)

    # Apply pagination
    stmt = stmt.offset(skip).limit(limit)

    return session.exec(stmt).all()


def count_zones(
    session: Session,
    greenhouse_id: uuid.UUID | None = None,
    is_active: bool | None = None,
) -> int:
    """
    Count zones with the same filters as list_zones.
    """
    from sqlmodel import func

    stmt = select(func.count(Zone.id))

    if greenhouse_id:
        stmt = stmt.where(Zone.greenhouse_id == greenhouse_id)

    # is_active filter ignored (not modeled)

    return session.exec(stmt).one()


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


def validate_greenhouse_ownership(
    session: Session, greenhouse_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """
    Validate that a user owns a specific greenhouse.
    """
    greenhouse = session.get(Greenhouse, greenhouse_id)
    return greenhouse is not None and greenhouse.user_id == user_id
