from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session, func, select

from app.models import (
    Greenhouse,
    Zone,
    ZoneCrop,
    ZoneCropObservation,
    ZoneCropObservationCreate,
    ZoneCropObservationUpdate,
)
from app.models.enums import ObservationType


class CRUDObservation:
    def get(self, session: Session, *, id: UUID) -> ZoneCropObservation | None:
        """Get observation by ID"""
        return session.get(ZoneCropObservation, id)

    def get_multi(
        self,
        session: Session,
        *,
        user_id: UUID | None = None,
        zone_crop_id: UUID | None = None,
        zone_id: UUID | None = None,
        greenhouse_id: UUID | None = None,
        observation_type: ObservationType | str | None = None,
        sort: str = "-observation_date",
        skip: int = 0,
        limit: int = 100,
    ) -> list[ZoneCropObservation]:
        """Get multiple observations with filtering and sorting"""
        stmt = select(ZoneCropObservation)

        # Apply user-scoped filtering through greenhouse ownership
        if user_id:
            stmt = (
                stmt.join(ZoneCrop, ZoneCropObservation.zone_crop_id == ZoneCrop.id)
                .join(Zone, ZoneCrop.zone_id == Zone.id)
                .join(Greenhouse, Zone.greenhouse_id == Greenhouse.id)
                .where(Greenhouse.user_id == user_id)
            )

        # Apply filters
        if zone_crop_id:
            stmt = stmt.where(ZoneCropObservation.zone_crop_id == zone_crop_id)

        if zone_id:
            # Join with ZoneCrop to filter by zone_id if not already joined
            if not user_id:
                stmt = stmt.join(
                    ZoneCrop, ZoneCropObservation.zone_crop_id == ZoneCrop.id
                )
            stmt = stmt.where(ZoneCrop.zone_id == zone_id)

        if greenhouse_id:
            # Join through ZoneCrop and Zone if not already joined
            if not user_id and not zone_id:
                stmt = stmt.join(
                    ZoneCrop, ZoneCropObservation.zone_crop_id == ZoneCrop.id
                ).join(Zone, ZoneCrop.zone_id == Zone.id)
            elif not user_id:
                stmt = stmt.join(Zone, ZoneCrop.zone_id == Zone.id)
            stmt = stmt.where(Zone.greenhouse_id == greenhouse_id)

        if observation_type:
            stmt = stmt.where(ZoneCropObservation.observation_type == observation_type)

        # Apply sorting with field mapping
        sort_field = sort.lstrip("-")
        is_desc = sort.startswith("-")

        # Map observation_date to observed_at for backwards compatibility
        field_mapping = {"observation_date": "observed_at"}
        sort_field = field_mapping.get(sort_field, sort_field)

        if sort_field == "observed_at":
            stmt = stmt.order_by(
                ZoneCropObservation.observed_at.desc()
                if is_desc
                else ZoneCropObservation.observed_at
            )
        elif sort_field == "created_at":
            stmt = stmt.order_by(
                ZoneCropObservation.created_at.desc()
                if is_desc
                else ZoneCropObservation.created_at
            )
        else:
            # Default to observed_at descending
            stmt = stmt.order_by(ZoneCropObservation.observed_at.desc())

        # Apply pagination
        stmt = stmt.offset(skip).limit(limit)

        return session.exec(stmt).all()

    def count(
        self,
        session: Session,
        *,
        user_id: UUID | None = None,
        zone_crop_id: UUID | None = None,
        zone_id: UUID | None = None,
        greenhouse_id: UUID | None = None,
        observation_type: ObservationType | str | None = None,
    ) -> int:
        """Count observations with the same filters"""
        stmt = select(func.count(ZoneCropObservation.id))

        # Apply user-scoped filtering through greenhouse ownership
        if user_id:
            stmt = (
                stmt.join(ZoneCrop, ZoneCropObservation.zone_crop_id == ZoneCrop.id)
                .join(Zone, ZoneCrop.zone_id == Zone.id)
                .join(Greenhouse, Zone.greenhouse_id == Greenhouse.id)
                .where(Greenhouse.user_id == user_id)
            )

        if zone_crop_id:
            stmt = stmt.where(ZoneCropObservation.zone_crop_id == zone_crop_id)

        if zone_id:
            # Join with ZoneCrop to filter by zone_id if not already joined
            if not user_id:
                stmt = stmt.join(
                    ZoneCrop, ZoneCropObservation.zone_crop_id == ZoneCrop.id
                )
            stmt = stmt.where(ZoneCrop.zone_id == zone_id)

        if greenhouse_id:
            # Join through ZoneCrop and Zone if not already joined
            if not user_id and not zone_id:
                stmt = stmt.join(
                    ZoneCrop, ZoneCropObservation.zone_crop_id == ZoneCrop.id
                ).join(Zone, ZoneCrop.zone_id == Zone.id)
            elif not user_id:
                stmt = stmt.join(Zone, ZoneCrop.zone_id == Zone.id)
            stmt = stmt.where(Zone.greenhouse_id == greenhouse_id)

        if observation_type:
            stmt = stmt.where(ZoneCropObservation.observation_type == observation_type)

        return session.exec(stmt).one()

    def create(
        self, session: Session, *, obj_in: ZoneCropObservationCreate, user_id: UUID
    ) -> ZoneCropObservation:
        """Create new observation with ownership validation"""
        # Validate zone crop ownership
        if not self.validate_zone_crop_ownership(
            session, zone_crop_id=obj_in.zone_crop_id, user_id=user_id
        ):
            raise HTTPException(
                status_code=403, detail="Not authorized to access this zone crop"
            )

        db_obj = ZoneCropObservation.model_validate(obj_in)
        session.add(db_obj)
        session.commit()
        session.refresh(db_obj)
        return db_obj

    def update(
        self,
        session: Session,
        *,
        db_obj: ZoneCropObservation,
        obj_in: ZoneCropObservationUpdate,
        user_id: UUID,
    ) -> ZoneCropObservation:
        """Update observation with ownership validation"""
        # Validate zone crop ownership
        if not self.validate_zone_crop_ownership(
            session, zone_crop_id=db_obj.zone_crop_id, user_id=user_id
        ):
            raise HTTPException(
                status_code=403, detail="Not authorized to access this zone crop"
            )

        update_data = obj_in.model_dump(exclude_unset=True)
        db_obj.sqlmodel_update(update_data)
        session.add(db_obj)
        session.commit()
        session.refresh(db_obj)
        return db_obj

    def remove(
        self, session: Session, *, id: UUID, user_id: UUID
    ) -> ZoneCropObservation | None:
        """Delete observation with ownership validation"""
        obj = session.get(ZoneCropObservation, id)
        if obj:
            # Validate zone crop ownership
            if not self.validate_zone_crop_ownership(
                session, zone_crop_id=obj.zone_crop_id, user_id=user_id
            ):
                raise HTTPException(
                    status_code=403, detail="Not authorized to access this zone crop"
                )

            session.delete(obj)
            session.commit()
        return obj

    def validate_zone_crop_ownership(
        self, session: Session, zone_crop_id: UUID, user_id: UUID
    ) -> bool:
        """Validate that user owns the greenhouse containing the zone crop"""
        zone_crop = session.get(ZoneCrop, zone_crop_id)
        if not zone_crop:
            return False

        zone = session.get(Zone, zone_crop.zone_id)
        if not zone:
            return False

        greenhouse = session.get(Greenhouse, zone.greenhouse_id)
        return greenhouse is not None and greenhouse.user_id == user_id


observation = CRUDObservation()
