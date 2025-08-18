import uuid

from sqlmodel import Session, and_, select

from app.models import Controller, ControllerCreate, ControllerUpdate


def create_controller(session: Session, c_in: ControllerCreate) -> Controller:
    """
    Create a new Controller record.

    Note: Validation of device_name uniqueness and climate controller
    constraints should be handled at the API layer.
    """
    data = c_in.model_dump()
    controller = Controller(**data)
    session.add(controller)
    session.commit()
    session.refresh(controller)
    return controller


def get_controller(session: Session, controller_id: uuid.UUID) -> Controller | None:
    """
    Retrieve a Controller by its ID.
    """
    return session.get(Controller, controller_id)


def get_controller_by_device_name(
    session: Session, device_name: str
) -> Controller | None:
    """
    Retrieve a Controller by its device_name.
    """
    return session.exec(
        select(Controller).where(Controller.device_name == device_name)
    ).first()


def list_controllers(
    session: Session,
    greenhouse_id: uuid.UUID | None = None,
    is_climate_controller: bool | None = None,
    owner_id: uuid.UUID | None = None,
) -> list[Controller]:
    """
    List controllers with optional filtering.

    Args:
        session: Database session
        greenhouse_id: Filter by greenhouse (optional)
        is_climate_controller: Filter by climate controller status (optional)
        owner_id: Filter by greenhouse owner (for access control, optional)

    Returns:
        List of matching controllers
    """
    query = select(Controller)

    # Apply filters
    conditions = []

    if greenhouse_id:
        conditions.append(Controller.greenhouse_id == greenhouse_id)

    if is_climate_controller is not None:
        conditions.append(Controller.is_climate_controller == is_climate_controller)

    if owner_id:
        # Join with greenhouse to filter by owner using explicit FK join
        from app.models import Greenhouse

        query = query.join(Greenhouse, Controller.greenhouse_id == Greenhouse.id)
        conditions.append(Greenhouse.user_id == owner_id)

    if conditions:
        query = query.where(and_(*conditions))

    return session.exec(query).all()


def update_controller(
    session: Session, controller: Controller, c_in: ControllerUpdate
) -> Controller:
    """
    Update fields on an existing Controller.

    Note: Business rule validation (e.g., climate controller uniqueness)
    should be handled at the API layer.
    """
    update_data = c_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(controller, key, value)
    session.add(controller)
    session.commit()
    session.refresh(controller)
    return controller


def delete_controller(session: Session, controller: Controller) -> None:
    """
    Delete a Controller record.

    This will cascade delete related sensors, actuators, etc. due to
    foreign key constraints with CASCADE delete.
    """
    session.delete(controller)
    session.commit()


def validate_climate_controller_uniqueness(
    session: Session,
    greenhouse_id: uuid.UUID,
    exclude_controller_id: uuid.UUID | None = None,
) -> Controller | None:
    """
    Check if there's already a climate controller in this greenhouse.

    Args:
        session: Database session
        greenhouse_id: Greenhouse to check
        exclude_controller_id: Controller ID to exclude from check (for updates)

    Returns:
        Existing climate controller if found, None otherwise
    """
    query = select(Controller).where(
        and_(
            Controller.greenhouse_id == greenhouse_id,
            Controller.is_climate_controller is True,
        )
    )

    if exclude_controller_id:
        query = query.where(Controller.id != exclude_controller_id)

    return session.exec(query).first()
