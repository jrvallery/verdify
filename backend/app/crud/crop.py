from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session, func, select

from app.models import Crop, CropCreate, CropUpdate


class CRUDCrop:
    def get(self, session: Session, *, id: UUID) -> Crop | None:
        """Get crop by ID"""
        return session.get(Crop, id)

    def get_by_name(self, session: Session, *, name: str) -> Crop | None:
        """Get crop by name (for uniqueness validation)"""
        statement = select(Crop).where(Crop.name == name)
        return session.exec(statement).first()

    def get_multi(
        self, session: Session, *, skip: int = 0, limit: int = 100
    ) -> list[Crop]:
        """Get multiple crops with pagination"""
        statement = select(Crop).offset(skip).limit(limit)
        return session.exec(statement).all()

    def count(self, session: Session) -> int:
        """Count total crops"""
        statement = select(func.count(Crop.id))
        return session.exec(statement).one()

    def create(self, session: Session, *, obj_in: CropCreate) -> Crop:
        """Create new crop with name uniqueness validation"""
        # Check if name already exists
        existing_crop = self.get_by_name(session, name=obj_in.name)
        if existing_crop:
            raise HTTPException(
                status_code=400, detail=f"Crop with name '{obj_in.name}' already exists"
            )

        db_obj = Crop.model_validate(obj_in)
        session.add(db_obj)
        session.commit()
        session.refresh(db_obj)
        return db_obj

    def update(self, session: Session, *, db_obj: Crop, obj_in: CropUpdate) -> Crop:
        """Update crop with name uniqueness validation"""
        # Check for name uniqueness if name is being updated
        if obj_in.name and obj_in.name != db_obj.name:
            existing_crop = self.get_by_name(session, name=obj_in.name)
            if existing_crop:
                raise HTTPException(
                    status_code=400,
                    detail=f"Crop with name '{obj_in.name}' already exists",
                )

        update_data = obj_in.model_dump(exclude_unset=True)
        db_obj.sqlmodel_update(update_data)
        session.add(db_obj)
        session.commit()
        session.refresh(db_obj)
        return db_obj

    def remove(self, session: Session, *, id: UUID) -> Crop | None:
        """Delete crop"""
        obj = session.get(Crop, id)
        if obj:
            session.delete(obj)
            session.commit()
        return obj


crop = CRUDCrop()
