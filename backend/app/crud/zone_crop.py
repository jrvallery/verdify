from uuid import UUID

from fastapi import HTTPException
from sqlmodel import Session, and_, func, select

from app.api.permissions import (
    ownership_or_membership_condition,
    user_can_access_greenhouse,
)
from app.models import Greenhouse, Zone, ZoneCrop, ZoneCropCreate, ZoneCropUpdate


class CRUDZoneCrop:
    def get(self, session: Session, *, id: UUID) -> ZoneCrop | None:
        """Get zone crop by ID"""
        return session.get(ZoneCrop, id)

    def get_multi(
        self,
        session: Session,
        *,
        user_id: UUID | None = None,
        zone_id: UUID | None = None,
        greenhouse_id: UUID | None = None,
        crop_id: UUID | None = None,
        is_active: bool | None = None,
        sort: str = "-start_date",
        skip: int = 0,
        limit: int = 100,
    ) -> list[ZoneCrop]:
        """Get multiple zone crops with filtering and sorting"""
        stmt = select(ZoneCrop)

        # Apply user-scoped filtering through greenhouse ownership or membership
        if user_id:
            stmt = (
                stmt.join(Zone, ZoneCrop.zone_id == Zone.id)
                .join(Greenhouse, Zone.greenhouse_id == Greenhouse.id)
                .where(ownership_or_membership_condition(user_id))
            )

        # Apply filters
        if zone_id:
            stmt = stmt.where(ZoneCrop.zone_id == zone_id)
        if greenhouse_id:
            if not user_id:  # If user_id not already applied, add the join
                stmt = stmt.join(Zone, ZoneCrop.zone_id == Zone.id)
            stmt = stmt.where(Zone.greenhouse_id == greenhouse_id)
        if crop_id:
            stmt = stmt.where(ZoneCrop.crop_id == crop_id)
        if is_active is not None:
            stmt = stmt.where(ZoneCrop.is_active == is_active)

        # Apply sorting - support both old and new field names for backwards compatibility
        sort_field = sort.lstrip("-")
        is_desc = sort.startswith("-")

        # Map old field names to new ones
        field_mapping = {
            "planted_at": "start_date",
            "planned_harvest_at": "end_date",
            "harvested_at": "end_date",
        }
        sort_field = field_mapping.get(sort_field, sort_field)

        if sort_field == "start_date":
            stmt = stmt.order_by(
                ZoneCrop.start_date.desc() if is_desc else ZoneCrop.start_date
            )
        elif sort_field == "end_date":
            stmt = stmt.order_by(
                ZoneCrop.end_date.desc() if is_desc else ZoneCrop.end_date
            )
        elif sort_field == "created_at":
            stmt = stmt.order_by(
                ZoneCrop.created_at.desc() if is_desc else ZoneCrop.created_at
            )
        else:
            # Default to start_date
            stmt = stmt.order_by(ZoneCrop.start_date.desc())

        # Apply pagination
        stmt = stmt.offset(skip).limit(limit)

        return session.exec(stmt).all()

    def count(
        self,
        session: Session,
        *,
        user_id: UUID | None = None,
        zone_id: UUID | None = None,
        greenhouse_id: UUID | None = None,
        crop_id: UUID | None = None,
        is_active: bool | None = None,
    ) -> int:
        """Count zone crops with the same filters"""
        stmt = select(func.count(ZoneCrop.id))

        # Apply user-scoped filtering through greenhouse ownership or membership
        if user_id:
            stmt = (
                stmt.join(Zone, ZoneCrop.zone_id == Zone.id)
                .join(Greenhouse, Zone.greenhouse_id == Greenhouse.id)
                .where(ownership_or_membership_condition(user_id))
            )

        if zone_id:
            stmt = stmt.where(ZoneCrop.zone_id == zone_id)
        if greenhouse_id:
            if not user_id:  # If user_id not already applied, add the join
                stmt = stmt.join(Zone, ZoneCrop.zone_id == Zone.id)
            stmt = stmt.where(Zone.greenhouse_id == greenhouse_id)
        if crop_id:
            stmt = stmt.where(ZoneCrop.crop_id == crop_id)
        if is_active is not None:
            stmt = stmt.where(ZoneCrop.is_active == is_active)

        return session.exec(stmt).one()

    def create(
        self, session: Session, *, obj_in: ZoneCropCreate, user_id: UUID
    ) -> ZoneCrop:
        """Create new zone crop with one-active-per-zone constraint (operators can create)"""
        # Validate zone access (owner or operator)
        if not self.validate_zone_access(
            session, zone_id=obj_in.zone_id, user_id=user_id
        ):
            raise HTTPException(
                status_code=403, detail="Not authorized to access this zone"
            )

        # Check if zone already has an active crop
        existing_active = session.exec(
            select(ZoneCrop).where(
                and_(ZoneCrop.zone_id == obj_in.zone_id, ZoneCrop.is_active.is_(True))
            )
        ).first()

        if existing_active:
            raise HTTPException(
                status_code=409,
                detail="Zone already has an active crop. Only one active crop per zone is allowed.",
            )

        db_obj = ZoneCrop.model_validate(obj_in)
        session.add(db_obj)
        session.commit()
        session.refresh(db_obj)
        return db_obj

    def update(
        self,
        session: Session,
        *,
        db_obj: ZoneCrop,
        obj_in: ZoneCropUpdate,
        user_id: UUID,
    ) -> ZoneCrop:
        """Update zone crop with access validation (operators can update)"""
        # Validate zone access (owner or operator)
        if not self.validate_zone_access(
            session, zone_id=db_obj.zone_id, user_id=user_id
        ):
            raise HTTPException(
                status_code=403, detail="Not authorized to access this zone"
            )

        update_data = obj_in.model_dump(exclude_unset=True)
        db_obj.sqlmodel_update(update_data)
        session.add(db_obj)
        session.commit()
        session.refresh(db_obj)
        return db_obj

    def remove(self, session: Session, *, id: UUID, user_id: UUID) -> ZoneCrop | None:
        """Delete zone crop with ownership validation (owner only)"""
        obj = session.get(ZoneCrop, id)
        if obj:
            # Validate zone ownership (owner only for delete)
            if not self.validate_zone_ownership(
                session, zone_id=obj.zone_id, user_id=user_id
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Only greenhouse owners can delete zone crops",
                )

            session.delete(obj)
            session.commit()
        return obj

    def validate_zone_access(
        self, session: Session, zone_id: UUID, user_id: UUID
    ) -> bool:
        """Validate that user can access the greenhouse containing the zone (owner or operator)"""
        zone = session.get(Zone, zone_id)
        if not zone:
            return False

        return user_can_access_greenhouse(session, zone.greenhouse_id, user_id)

    def validate_zone_ownership(
        self, session: Session, zone_id: UUID, user_id: UUID
    ) -> bool:
        """Validate that user owns the greenhouse containing the zone (owner only)"""
        zone = session.get(Zone, zone_id)
        if not zone:
            return False

        greenhouse = session.get(Greenhouse, zone.greenhouse_id)
        return greenhouse is not None and greenhouse.user_id == user_id


zone_crop = CRUDZoneCrop()
