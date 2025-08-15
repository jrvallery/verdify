from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlmodel import select
from typing import List, Optional
from datetime import datetime, timezone
from pathlib import Path
import shutil
import uuid
import os

from app.api.deps import get_current_user, SessionDep
from app.models import (
    User, Zone, Greenhouse,
    Crop, CropObservation, CropObservationPublic,
)

# Normalize UPLOAD_DIR to a Path with default and ensure it exists
UPLOAD_DIR_STR = os.getenv("UPLOAD_DIR", "static/uploads/observations")
UPLOAD_DIR = Path(UPLOAD_DIR_STR)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter()

def verify_zone_access(zone_id: str, current_user: User, session) -> Zone:
    zone = session.get(Zone, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    greenhouse = session.get(Greenhouse, zone.greenhouse_id)
    if greenhouse.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return zone

@router.get("/zones/{zone_id}/observations/", response_model=List[CropObservationPublic])
def list_crop_observations(
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
    return session.exec(
        select(CropObservation).where(CropObservation.crop_id == active_crop.id)
    ).all()

@router.get("/crops/{crop_id}/observations/", response_model=List[CropObservationPublic])
def list_observations_by_crop_id(
    crop_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    crop = session.get(Crop, crop_id)
    if not crop:
        raise HTTPException(status_code=404, detail="Crop not found")
    # Verify access through crop's zone
    verify_zone_access(crop.zone_id, current_user, session)
    return session.exec(
        select(CropObservation).where(CropObservation.crop_id == crop.id)
    ).all()

@router.post("/zones/{zone_id}/observations/", response_model=CropObservationPublic)
def create_crop_observation(
    zone_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
    file: Optional[UploadFile] = File(None),
    notes: Optional[str] = Form(None),
    height_cm: Optional[float] = Form(None),
    health_score: Optional[int] = Form(None),
    observed_at: Optional[str] = Form(None),
):
    zone = verify_zone_access(zone_id, current_user, session)
    active_crop = session.exec(
        select(Crop).where(Crop.zone_id == zone.id, Crop.is_active == True)
    ).first()
    if not active_crop:
        raise HTTPException(status_code=404, detail="No active crop planted in this zone")

    image_url = None
    if file and file.filename:
        ext = file.filename.split(".")[-1]
        observation_id = uuid.uuid4()
        filename = f"{current_user.id}_{zone.greenhouse_id}_{zone_id}_{active_crop.id}_{observation_id}.{ext}"
        file_path = UPLOAD_DIR / filename
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        image_url = str(file_path)

    parsed_observed_at = datetime.now(timezone.utc)
    if observed_at:
        try:
            parsed_observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid datetime format")

    data = {
        "crop_id": active_crop.id,
        "observed_at": parsed_observed_at,
    }
    if notes and notes.strip():
        data["notes"] = notes.strip()
    if height_cm is not None:
        data["height_cm"] = float(height_cm)
    if health_score is not None:
        data["health_score"] = int(health_score)
    if image_url is not None:
        data["image_url"] = image_url

    db_observation = CropObservation(**data)
    session.add(db_observation)
    session.commit()
    session.refresh(db_observation)
    return db_observation
