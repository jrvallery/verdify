from typing import List, Optional
from uuid import UUID

from sqlmodel import Session, select

from app.models import CropObservation, CropObservationCreate, CropObservationUpdate


class CRUDObservation:
    def get(self, session: Session, *, id: UUID) -> Optional[CropObservation]:
        return session.get(CropObservation, id)

    def get_multi(self, session: Session, *, skip: int = 0, limit: int = 100) -> List[CropObservation]:
        statement = select(CropObservation).offset(skip).limit(limit)
        return session.exec(statement).all()

    def create(self, session: Session, *, obj_in: CropObservationCreate) -> CropObservation:
        db_obj = CropObservation.model_validate(obj_in)
        session.add(db_obj)
        session.commit()
        session.refresh(db_obj)
        return db_obj

    def update(self, session: Session, *, db_obj: CropObservation, obj_in: CropObservationUpdate) -> CropObservation:
        update_data = obj_in.model_dump(exclude_unset=True)
        db_obj.sqlmodel_update(update_data)
        session.add(db_obj)
        session.commit()
        session.refresh(db_obj)
        return db_obj

    def remove(self, session: Session, *, id: UUID) -> Optional[CropObservation]:
        obj = session.get(CropObservation, id)
        if obj:
            session.delete(obj)
            session.commit()
        return obj


observations = CRUDObservation()
