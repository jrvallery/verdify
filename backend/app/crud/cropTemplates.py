from typing import List, Optional
from uuid import UUID

from sqlmodel import Session, select

from app.models import CropTemplate, CropTemplateCreate, CropTemplateUpdate


class CRUDCropTemplate:
    def get(self, session: Session, *, id: UUID) -> Optional[CropTemplate]:
        return session.get(CropTemplate, id)

    def get_multi(self, session: Session, *, skip: int = 0, limit: int = 100) -> List[CropTemplate]:
        statement = select(CropTemplate).offset(skip).limit(limit)
        return session.exec(statement).all()

    def create(self, session: Session, *, obj_in: CropTemplateCreate) -> CropTemplate:
        db_obj = CropTemplate.model_validate(obj_in)
        session.add(db_obj)
        session.commit()
        session.refresh(db_obj)
        return db_obj

    def update(self, session: Session, *, db_obj: CropTemplate, obj_in: CropTemplateUpdate) -> CropTemplate:
        update_data = obj_in.model_dump(exclude_unset=True)
        db_obj.sqlmodel_update(update_data)
        session.add(db_obj)
        session.commit()
        session.refresh(db_obj)
        return db_obj

    def remove(self, session: Session, *, id: UUID) -> Optional[CropTemplate]:
        obj = session.get(CropTemplate, id)
        if obj:
            session.delete(obj)
            session.commit()
        return obj


cropTemplates = CRUDCropTemplate()
