import uuid

from sqlmodel import Session, and_, select

from app.models import (
    Actuator,
    Controller,
    FanGroup,
    FanGroupCreate,
    FanGroupMember,
    FanGroupsPaginated,
    FanGroupUpdate,
    Greenhouse,
)
from app.utils_paging import PaginationParams, paginate_query


def create_fan_group(session: Session, fan_group_in: FanGroupCreate) -> FanGroup:
    """Create a new fan group record."""
    data = fan_group_in.model_dump()
    fan_group = FanGroup(**data)
    session.add(fan_group)
    session.commit()
    session.refresh(fan_group)
    return fan_group


def get_fan_group(session: Session, fan_group_id: uuid.UUID) -> FanGroup | None:
    """Retrieve a fan group by its ID."""
    return session.get(FanGroup, fan_group_id)


def validate_user_owns_fan_group(
    session: Session, fan_group_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Validate that a user owns the fan group through greenhouse ownership."""
    result = session.exec(
        select(FanGroup)
        .join(Controller)
        .join(Greenhouse)
        .where(and_(FanGroup.id == fan_group_id, Greenhouse.user_id == user_id))
    ).first()
    return result is not None


def list_fan_groups(
    session: Session,
    user_id: uuid.UUID,
    pagination: PaginationParams,
    controller_id: uuid.UUID | None = None,
    sort: str = "name",
) -> FanGroupsPaginated:
    """List fan groups with filtering and pagination."""
    # Base query - join with controller and greenhouse for ownership validation
    query = (
        select(FanGroup)
        .join(Controller)
        .join(Greenhouse)
        .where(Greenhouse.user_id == user_id)
    )

    # Apply filters
    if controller_id:
        query = query.where(FanGroup.controller_id == controller_id)

    # Apply sorting
    if sort == "name":
        query = query.order_by(FanGroup.name)
    elif sort == "-name":
        query = query.order_by(FanGroup.name.desc())
    elif sort == "created_at":
        query = query.order_by(FanGroup.created_at)
    elif sort == "-created_at":
        query = query.order_by(FanGroup.created_at.desc())
    else:
        # Default to name ascending
        query = query.order_by(FanGroup.name)

    # Apply pagination and return
    return paginate_query(session, query, pagination)


def update_fan_group(
    session: Session, fan_group_id: uuid.UUID, fan_group_in: FanGroupUpdate
) -> FanGroup | None:
    """Update a fan group record."""
    fan_group = session.get(FanGroup, fan_group_id)
    if not fan_group:
        return None

    update_data = fan_group_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(fan_group, key, value)

    session.add(fan_group)
    session.commit()
    session.refresh(fan_group)
    return fan_group


def delete_fan_group(session: Session, fan_group_id: uuid.UUID) -> bool:
    """Delete a fan group record."""
    fan_group = session.get(FanGroup, fan_group_id)
    if not fan_group:
        return False

    session.delete(fan_group)
    session.commit()
    return True


def add_fan_group_member(
    session: Session, fan_group_id: uuid.UUID, actuator_id: uuid.UUID
) -> FanGroupMember | None:
    """Add an actuator to a fan group."""
    # Check if the member already exists
    existing = session.exec(
        select(FanGroupMember).where(
            and_(
                FanGroupMember.fan_group_id == fan_group_id,
                FanGroupMember.actuator_id == actuator_id,
            )
        )
    ).first()

    if existing:
        raise ValueError("Actuator is already a member of this fan group")

    # Verify both fan group and actuator exist
    fan_group = session.get(FanGroup, fan_group_id)
    actuator = session.get(Actuator, actuator_id)

    if not fan_group:
        raise ValueError("Fan group not found")
    if not actuator:
        raise ValueError("Actuator not found")

    # Create the membership
    member = FanGroupMember(fan_group_id=fan_group_id, actuator_id=actuator_id)
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


def remove_fan_group_member(
    session: Session, fan_group_id: uuid.UUID, actuator_id: uuid.UUID
) -> bool:
    """Remove an actuator from a fan group."""
    member = session.exec(
        select(FanGroupMember).where(
            and_(
                FanGroupMember.fan_group_id == fan_group_id,
                FanGroupMember.actuator_id == actuator_id,
            )
        )
    ).first()

    if not member:
        return False

    session.delete(member)
    session.commit()
    return True
