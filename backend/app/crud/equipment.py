from typing import List
from sqlmodel import Session, select
import uuid

from app.models import Equipment, EquipmentCreate, EquipmentUpdate

def create_equipment(session: Session, e_in: EquipmentCreate) -> Equipment:
    """
    Create a new Equipment record.
    """
    data = e_in.model_dump()
    eq = Equipment(**data)
    session.add(eq)
    session.commit()
    session.refresh(eq)
    return eq

def get_equipment(session: Session, eq_id: uuid.UUID) -> Equipment | None:
    """
    Retrieve an Equipment by its ID.
    """
    return session.get(Equipment, eq_id)

def list_equipment(session: Session) -> List[Equipment]:
    """
    List all equipment.
    """
    return session.exec(select(Equipment)).all()

def update_equipment(session: Session, eq: Equipment, e_in: EquipmentUpdate) -> Equipment:
    """
    Update fields on an existing Equipment.
    """
    update_data = e_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(eq, key, value)
    session.add(eq)
    session.commit()
    session.refresh(eq)
    return eq

def delete_equipment(session: Session, eq: Equipment) -> None:
    """
    Delete an Equipment record.
    """
    session.delete(eq)
    session.commit()