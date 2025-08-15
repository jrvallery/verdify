from typing import List, Optional
from uuid import UUID

from sqlmodel import Session, select

from app.models import Crop, CropCreate, CropUpdate


class CRUDCrop:
    def get(self, session: Session, *, id: UUID) -> Optional[Crop]:
        return session.get(Crop, id)

    def get_multi(self, session: Session, *, skip: int = 0, limit: int = 100) -> List[Crop]:
        statement = select(Crop).offset(skip).limit(limit)
        return session.exec(statement).all()

    def create(self, session: Session, *, obj_in: CropCreate) -> Crop:
        db_obj = Crop.model_validate(obj_in)
        session.add(db_obj)
        session.commit()
        session.refresh(db_obj)
        return db_obj

    def update(self, session: Session, *, db_obj: Crop, obj_in: CropUpdate) -> Crop:
        update_data = obj_in.model_dump(exclude_unset=True)
        db_obj.sqlmodel_update(update_data)
        session.add(db_obj)
        session.commit()
        session.refresh(db_obj)
        return db_obj

    def remove(self, session: Session, *, id: UUID) -> Optional[Crop]:
        obj = session.get(Crop, id)
        if obj:
            session.delete(obj)
            session.commit()
        return obj


crops = CRUDCrop()
