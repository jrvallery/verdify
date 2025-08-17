import uuid

from sqlmodel import Session, and_, select

from app.models import (
    ButtonKind,
    Controller,
    ControllerButton,
    ControllerButtonCreate,
    ControllerButtonsPaginated,
    ControllerButtonUpdate,
    Greenhouse,
)
from app.utils_paging import PaginationParams, paginate_query


def create_controller_button(
    session: Session, button_in: ControllerButtonCreate
) -> ControllerButton:
    """Create a new controller button record."""
    data = button_in.model_dump()
    button = ControllerButton(**data)
    session.add(button)
    session.commit()
    session.refresh(button)
    return button


def get_controller_button(
    session: Session, button_id: uuid.UUID
) -> ControllerButton | None:
    """Retrieve a controller button by its ID."""
    return session.get(ControllerButton, button_id)


def validate_user_owns_controller_button(
    session: Session, button_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Validate that a user owns the controller button through greenhouse ownership."""
    result = session.exec(
        select(ControllerButton)
        .join(Controller)
        .join(Greenhouse)
        .where(and_(ControllerButton.id == button_id, Greenhouse.user_id == user_id))
    ).first()
    return result is not None


def list_controller_buttons(
    session: Session,
    user_id: uuid.UUID,
    pagination: PaginationParams,
    controller_id: uuid.UUID | None = None,
    button_kind: ButtonKind | None = None,
    sort: str = "button_kind",
) -> ControllerButtonsPaginated:
    """List controller buttons with filtering and pagination."""
    # Base query - join with controller and greenhouse for ownership validation
    query = (
        select(ControllerButton)
        .join(Controller)
        .join(Greenhouse)
        .where(Greenhouse.user_id == user_id)
    )

    # Apply filters
    if controller_id:
        query = query.where(ControllerButton.controller_id == controller_id)

    if button_kind:
        query = query.where(ControllerButton.button_kind == button_kind)

    # Apply sorting
    if sort == "button_kind":
        query = query.order_by(ControllerButton.button_kind)
    elif sort == "-button_kind":
        query = query.order_by(ControllerButton.button_kind.desc())
    elif sort == "created_at":
        query = query.order_by(ControllerButton.created_at)
    elif sort == "-created_at":
        query = query.order_by(ControllerButton.created_at.desc())
    else:
        # Default to button_kind ascending
        query = query.order_by(ControllerButton.button_kind)

    # Apply pagination and return
    return paginate_query(session, query, pagination)


def update_controller_button(
    session: Session, button_id: uuid.UUID, button_in: ControllerButtonUpdate
) -> ControllerButton | None:
    """Update a controller button record."""
    button = session.get(ControllerButton, button_id)
    if not button:
        return None

    update_data = button_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(button, key, value)

    session.add(button)
    session.commit()
    session.refresh(button)
    return button


def delete_controller_button(session: Session, button_id: uuid.UUID) -> bool:
    """Delete a controller button record."""
    button = session.get(ControllerButton, button_id)
    if not button:
        return False

    session.delete(button)
    session.commit()
    return True
