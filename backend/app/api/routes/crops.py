from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from datetime import datetime, timezone

from app.api.deps import get_current_user, SessionDep
from app.crud.crop import crops
from app.models import (
    User, Zone, Greenhouse,
    Crop, CropCreate, CropPublic, CropUpdate,
    CropTemplate, CropObservation,
)

router = APIRouter()

def verify_zone_access(zone_id: str, current_user: User, session: Session) -> Zone:
    zone = session.get(Zone, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    greenhouse = session.get(Greenhouse, zone.greenhouse_id)
    if greenhouse.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return zone

@router.get("/zones/{zone_id}/crop/", response_model=CropPublic)
def get_crop(
    zone_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    zone = verify_zone_access(zone_id, current_user, session)
    active_crop = session.exec(
        select(Crop).where(Crop.zone_id == zone.id, Crop.is_active == True)
    ).first()
    if not active_crop:
        raise HTTPException(status_code=404, detail="No active crop planted in this zone")
    return active_crop

@router.get("/zones/{zone_id}/crops/", response_model=List[CropPublic])
def list_crop_history(
    zone_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    zone = verify_zone_access(zone_id, current_user, session)
    return session.exec(select(Crop).where(Crop.zone_id == zone.id)).all()

@router.post("/zones/{zone_id}/crop/", response_model=CropPublic)
def plant_crop(
    zone_id: str,
    crop_in: CropCreate,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    zone = verify_zone_access(zone_id, current_user, session)

    existing_active = session.exec(
        select(Crop).where(Crop.zone_id == zone.id, Crop.is_active == True)
    ).first()
    if existing_active:
        raise HTTPException(status_code=400, detail="Zone already has an active crop. Harvest or deactivate existing crop first.")

    # Verify crop template exists
    tpl = session.get(CropTemplate, crop_in.crop_template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Crop template not found")

    # Enforce zone_id from path
    create_obj = CropCreate.model_validate(crop_in, update={"zone_id": zone_id})
    return crops.create(session, obj_in=create_obj)

@router.patch("/zones/{zone_id}/crop/", response_model=CropPublic)
def update_crop(
    zone_id: str,
    crop_in: CropUpdate,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    zone = verify_zone_access(zone_id, current_user, session)
    active_crop = session.exec(
        select(Crop).where(Crop.zone_id == zone.id, Crop.is_active == True)
    ).first()
    if not active_crop:
        raise HTTPException(status_code=404, detail="No active crop planted in this zone")
    return crops.update(session, db_obj=active_crop, obj_in=crop_in)

@router.delete("/zones/{zone_id}/crop/")
def harvest_crop(
    zone_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    zone = verify_zone_access(zone_id, current_user, session)
    active_crop = session.exec(
        select(Crop).where(Crop.zone_id == zone.id, Crop.is_active == True)
    ).first()
    if not active_crop:
        raise HTTPException(status_code=404, detail="No active crop planted in this zone")

    active_crop.is_active = False
    active_crop.end_date = datetime.now(timezone.utc)
    session.add(active_crop)
    session.commit()
    session.refresh(active_crop)
    return {"message": "Crop harvested successfully (historical record preserved)"}

@router.delete("/zones/{zone_id}/crops/{crop_id}")
def permanently_delete_zone_crop(
    zone_id: str,
    crop_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    zone = verify_zone_access(zone_id, current_user, session)
    crop = session.get(Crop, crop_id)
    if not crop or crop.zone_id != zone.id:
        raise HTTPException(status_code=404, detail="Crop not found in this zone")
    session.delete(crop)
    session.commit()
    return {"message": "Crop permanently deleted"}

@router.get("/zones/{zone_id}/crop-analytics/")
def get_zone_crop_analytics(
    zone_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    zone = verify_zone_access(zone_id, current_user, session)
    crops_in_zone = session.exec(select(Crop).where(Crop.zone_id == zone.id)).all()

    def obs_count(c_id):
        return len(session.exec(select(CropObservation).where(CropObservation.crop_id == c_id)).all())

    analytics = {
        "zone_id": zone_id,
        "total_crops_grown": len(crops_in_zone),
        "active_crops": len([c for c in crops_in_zone if c.is_active]),
        "completed_crops": len([c for c in crops_in_zone if not c.is_active]),
        "crop_history": [
            {
                "crop_name": (session.get(CropTemplate, c.crop_template_id).name if c.crop_template_id else None),
                "start_date": c.start_date,
                "end_date": c.end_date,
                "final_yield": c.final_yield,
                "area_sqm": c.area_sqm,
                "days_grown": (c.end_date - c.start_date).days if c.end_date else None,
                "observations_count": obs_count(c.id),
            }
            for c in crops_in_zone
        ],
    }
    return analytics

