import uuid

from sqlmodel import Session, and_, select

from app.models import (
    Actuator,
    ActuatorCreate,
    ActuatorKind,
    ActuatorsPaginated,
    ActuatorUpdate,
    Controller,
    Greenhouse,
)
from app.utils_paging import PaginationParams, paginate_query


def create_actuator(session: Session, actuator_in: ActuatorCreate) -> Actuator:
    """Create a new actuator record."""
    data = actuator_in.model_dump()
    actuator = Actuator(**data)
    session.add(actuator)
    session.commit()
    session.refresh(actuator)
    return actuator


def get_actuator(session: Session, actuator_id: uuid.UUID) -> Actuator | None:
    """Retrieve an actuator by its ID."""
    return session.get(Actuator, actuator_id)


def validate_user_owns_actuator(
    session: Session, actuator_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Validate that a user owns the actuator through greenhouse ownership."""
    result = session.exec(
        select(Actuator)
        .join(Controller)
        .join(Greenhouse)
        .where(and_(Actuator.id == actuator_id, Greenhouse.user_id == user_id))
    ).first()
    return result is not None


def list_actuators(
    session: Session,
    user_id: uuid.UUID,
    pagination: PaginationParams,
    controller_id: uuid.UUID | None = None,
    kind: ActuatorKind | None = None,
    sort: str = "name",
) -> ActuatorsPaginated:
    """List actuators with filtering and pagination."""
    # Base query - join with controller and greenhouse for ownership validation
    query = (
        select(Actuator)
        .join(Controller)
        .join(Greenhouse)
        .where(Greenhouse.user_id == user_id)
    )

    # Apply filters
    if controller_id:
        query = query.where(Actuator.controller_id == controller_id)

    if kind:
        query = query.where(Actuator.kind == kind)

    # Apply sorting
    if sort == "name":
        query = query.order_by(Actuator.name)
    elif sort == "-name":
        query = query.order_by(Actuator.name.desc())
    elif sort == "kind":
        query = query.order_by(Actuator.kind)
    elif sort == "-kind":
        query = query.order_by(Actuator.kind.desc())
    else:
        # Default to name ascending
        query = query.order_by(Actuator.name)

    # Apply pagination and return
    return paginate_query(session, query, pagination)


def update_actuator(
    session: Session, actuator_id: uuid.UUID, actuator_in: ActuatorUpdate
) -> Actuator | None:
    """Update an actuator record."""
    actuator = session.get(Actuator, actuator_id)
    if not actuator:
        return None

    update_data = actuator_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(actuator, key, value)

    session.add(actuator)
    session.commit()
    session.refresh(actuator)
    return actuator


def delete_actuator(session: Session, actuator_id: uuid.UUID) -> bool:
    """Delete an actuator record."""
    actuator = session.get(Actuator, actuator_id)
    if not actuator:
        return False

    session.delete(actuator)
    session.commit()
    return True
