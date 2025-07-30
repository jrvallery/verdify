from typing import List
from sqlmodel import Session, select
import uuid

from app.models import Controller, ControllerCreate, ControllerUpdate

def create_controller(session: Session, c_in: ControllerCreate) -> Controller:
    """
    Create a new Controller record.
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

def list_controllers(session: Session) -> List[Controller]:
    """
    List all controllers.
    """
    return session.exec(select(Controller)).all()

def update_controller(session: Session, controller: Controller, c_in: ControllerUpdate) -> Controller:
    """
    Update fields on an existing Controller.
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
    """
    session.delete(controller)
    session.commit()