from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlmodel import Session
from typing import List, Optional
from datetime import datetime, timezone
from pathlib import Path
import shutil
import uuid

from app.api.deps import get_current_user, SessionDep  # Changed get_session to SessionDep
from app.crud.crop import crop
from app.models import (
    User, Crop, CropCreate, CropPublic, CropUpdate,
    ZoneCrop, ZoneCropCreate, ZoneCropPublic, ZoneCropUpdate,
    ZoneCropObservation, ZoneCropObservationCreate, 
    ZoneCropObservationPublic, ZoneCropObservationUpdate,
    Zone, Greenhouse
)

router = APIRouter()

# Helper function to verify zone ownership
def verify_zone_access(zone_id: str, current_user: User, session: Session) -> Zone:
    zone = session.get(Zone, zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    
    greenhouse = session.get(Greenhouse, zone.greenhouse_id)
    if greenhouse.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    return zone

# ===== GLOBAL CROP TEMPLATES =====
@router.get("/", response_model=List[CropPublic])
def list_crops(
    session: SessionDep,
    current_user: User = Depends(get_current_user)
):
    """List all global crop templates"""
    return crop.get_multi(session)

@router.post("/", response_model=CropPublic)
def create_crop(
    crop_in: CropCreate, 
    session: SessionDep,
    current_user: User = Depends(get_current_user)
):
    """Create a new global crop template"""
    return crop.create(session, obj_in=crop_in)

@router.get("/{crop_id}", response_model=CropPublic)
def get_crop(
    crop_id: str, 
    session: SessionDep,
    current_user: User = Depends(get_current_user)
):
    """Get specific crop template"""
    db_crop = crop.get(session, id=crop_id)
    if not db_crop:
        raise HTTPException(status_code=404, detail="Crop not found")
    return db_crop

@router.patch("/{crop_id}", response_model=CropPublic)
def update_crop(
    crop_id: str, 
    crop_in: CropUpdate, 
    session: SessionDep,
    current_user: User = Depends(get_current_user)
):
    """Update crop template"""
    db_crop = crop.get(session, id=crop_id)
    if not db_crop:
        raise HTTPException(status_code=404, detail="Crop not found")
    
    return crop.update(session, db_obj=db_crop, obj_in=crop_in)

@router.delete("/{crop_id}")
def delete_crop(
    crop_id: str, 
    session: SessionDep,
    current_user: User = Depends(get_current_user)
):
    """Delete crop template"""
    db_crop = crop.remove(session, id=crop_id)
    if not db_crop:
        raise HTTPException(status_code=404, detail="Crop not found")
    
    return {"message": "Crop deleted successfully"}

# ===== ZONE CROP MANAGEMENT (Historical tracking) =====
@router.get("/zones/{zone_id}/zone-crop/", response_model=ZoneCropPublic)
def get_zone_crop(
    zone_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user)
):
    """Get the current active crop for a specific zone"""
    zone = verify_zone_access(zone_id, current_user, session)
    
    # Find active crop from historical list
    active_crop = next((zc for zc in zone.zone_crops if zc.is_active), None)
    
    if not active_crop:
        raise HTTPException(status_code=404, detail="No active crop planted in this zone")
    
    return active_crop

@router.get("/zones/{zone_id}/zone-crops/", response_model=List[ZoneCropPublic])
def list_zone_crop_history(
    zone_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user)
):
    """List all crop history (active and inactive) for a specific zone"""
    zone = verify_zone_access(zone_id, current_user, session)
    return zone.zone_crops

@router.post("/zones/{zone_id}/zone-crop/", response_model=ZoneCropPublic)
def plant_crop_in_zone(
    zone_id: str,
    zone_crop: ZoneCropCreate, 
    session: SessionDep,
    current_user: User = Depends(get_current_user)
):
    """Plant a crop in a zone (only one active per zone)"""
    zone = verify_zone_access(zone_id, current_user, session)
    
    # Check if zone already has an active crop
    active_crop = next((zc for zc in zone.zone_crops if zc.is_active), None)
    
    if active_crop:
        raise HTTPException(status_code=400, detail="Zone already has an active crop. Harvest or deactivate existing crop first.")
    
    # Verify the crop exists
    db_crop = crop.get(session, id=zone_crop.crop_id)
    if not db_crop:
        raise HTTPException(status_code=404, detail="Crop template not found")
    
    db_zone_crop = ZoneCrop.model_validate(zone_crop, update={"zone_id": zone_id})
    session.add(db_zone_crop)
    session.commit()
    session.refresh(db_zone_crop)
    return db_zone_crop

@router.patch("/zones/{zone_id}/zone-crop/", response_model=ZoneCropPublic)
def update_zone_crop(
    zone_id: str,
    zone_crop: ZoneCropUpdate, 
    session: SessionDep,
    current_user: User = Depends(get_current_user)
):
    """Update the active crop in a zone (harvest, change crop, etc.)"""
    zone = verify_zone_access(zone_id, current_user, session)
    
    # Find active crop
    active_crop = next((zc for zc in zone.zone_crops if zc.is_active), None)
    
    if not active_crop:
        raise HTTPException(status_code=404, detail="No active crop planted in this zone")
    
    # If changing crop, verify new crop exists
    if zone_crop.crop_id:
        db_crop = crop.get(session, id=zone_crop.crop_id)
        if not db_crop:
            raise HTTPException(status_code=404, detail="Crop template not found")
    
    zone_crop_data = zone_crop.model_dump(exclude_unset=True)
    active_crop.sqlmodel_update(zone_crop_data)
    session.add(active_crop)
    session.commit()
    session.refresh(active_crop)
    return active_crop

@router.delete("/zones/{zone_id}/zone-crop/")
def harvest_crop_from_zone(
    zone_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user)
):
    """Harvest/deactivate crop from zone (keeps historical record)"""
    zone = verify_zone_access(zone_id, current_user, session)
    
    # Find active crop
    active_crop = next((zc for zc in zone.zone_crops if zc.is_active), None)
    
    if not active_crop:
        raise HTTPException(status_code=404, detail="No active crop planted in this zone")
    
    # Deactivate instead of delete to preserve history
    active_crop.is_active = False
    active_crop.end_date = datetime.now(timezone.utc)
    
    session.add(active_crop)
    session.commit()
    session.refresh(active_crop)
    
    return {"message": "Crop harvested successfully (historical record preserved)"}

@router.delete("/zones/{zone_id}/zone-crops/{zone_crop_id}")
def permanently_delete_zone_crop(
    zone_id: str,
    zone_crop_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user)
):
    """Permanently delete a specific zone crop instance (use with caution)"""
    zone = verify_zone_access(zone_id, current_user, session)
    
    zone_crop_obj = session.get(ZoneCrop, zone_crop_id)
    if not zone_crop_obj or zone_crop_obj.zone_id != zone.id:
        raise HTTPException(status_code=404, detail="Zone crop not found in this zone")
    
    session.delete(zone_crop_obj)
    session.commit()
    return {"message": "Zone crop permanently deleted"}

# ===== AI DATA ENDPOINTS =====
@router.get("/zones/{zone_id}/crop-analytics/")
def get_zone_crop_analytics(
    zone_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user)
):
    """Get historical crop data for AI analysis"""
    zone = verify_zone_access(zone_id, current_user, session)
    
    analytics = {
        "zone_id": zone_id,
        "total_crops_grown": len(zone.zone_crops),
        "active_crops": len([zc for zc in zone.zone_crops if zc.is_active]),
        "completed_crops": len([zc for zc in zone.zone_crops if not zc.is_active]),
        "crop_history": [
            {
                "crop_name": zc.crop.name,
                "start_date": zc.start_date,
                "end_date": zc.end_date,
                "final_yield": zc.final_yield,
                "area_sqm": zc.area_sqm,
                "days_grown": (zc.end_date - zc.start_date).days if zc.end_date else None,
                "observations_count": len(zc.observations)
            }
            for zc in zone.zone_crops
        ]
    }
    
    return analytics

# ===== CROP OBSERVATIONS =====
@router.get("/zones/{zone_id}/observations/", response_model=List[ZoneCropObservationPublic])
def list_zone_crop_observations(
    zone_id: str, 
    session: SessionDep,
    current_user: User = Depends(get_current_user)
):
    """List observations for the active crop in a zone"""
    zone = verify_zone_access(zone_id, current_user, session)
    
    active_crop = next((zc for zc in zone.zone_crops if zc.is_active), None)
    if not active_crop:
        raise HTTPException(status_code=404, detail="No active crop planted in this zone")
    
    return active_crop.observations

@router.get("/zone-crops/{zone_crop_id}/observations/", response_model=List[ZoneCropObservationPublic])
def list_zone_crop_observations_by_id(
    zone_crop_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user)
):
    """List observations for a specific zone crop (including historical crops)"""
    zone_crop = session.get(ZoneCrop, zone_crop_id)
    if not zone_crop:
        raise HTTPException(status_code=404, detail="Zone crop not found")
    
    # Verify access through zone ownership
    zone = verify_zone_access(zone_crop.zone_id, current_user, session)
    
    return zone_crop.observations

UPLOAD_DIR = Path("static/uploads/observations")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
@router.post("/zones/{zone_id}/observations/", response_model=ZoneCropObservationPublic)
def create_zone_crop_observation(
    zone_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
    file: Optional[UploadFile] = File(None),
    # Use Form fields instead of Pydantic model for multipart data
    notes: Optional[str] = Form(None),
    height_cm: Optional[float] = Form(None),
    health_score: Optional[int] = Form(None),
    observed_at: Optional[str] = Form(None)
):
    """Add observation to the active crop in a zone"""
    # Debug logging
    print(f"Received form data:")
    print(f"  notes: {notes} (type: {type(notes)})")
    print(f"  height_cm: {height_cm} (type: {type(height_cm)})")
    print(f"  health_score: {health_score} (type: {type(health_score)})")
    print(f"  file: {file.filename if file else None}")
    
    zone = verify_zone_access(zone_id, current_user, session)
    
    active_crop = next((zc for zc in zone.zone_crops if zc.is_active), None)
    if not active_crop:
        raise HTTPException(status_code=404, detail="No active crop planted in this zone")
    
    # Handle file upload if provided
    image_url = None
    if file and file.filename:
        ext = file.filename.split(".")[-1]
        observation_id = uuid.uuid4()
        greenhouse_id = zone.greenhouse_id

        filename = f"{current_user.id}_{greenhouse_id}_{zone_id}_{active_crop.id}_{observation_id}.{ext}"
        file_path = UPLOAD_DIR / filename

        # Save file
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        image_url = str(file_path)
    
    # Parse datetime if provided, otherwise use current time
    parsed_observed_at = datetime.now(timezone.utc)
    if observed_at:
        try:
            parsed_observed_at = datetime.fromisoformat(observed_at.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid datetime format")
    
    # Create observation object with better error handling
    try:
        observation_data = {
            "zone_crop_id": active_crop.id,
            "observed_at": parsed_observed_at
        }
        
        # Only add fields that are not None
        if notes is not None and notes.strip():
            observation_data["notes"] = notes.strip()
        if height_cm is not None:
            observation_data["height_cm"] = float(height_cm)
        if health_score is not None:
            observation_data["health_score"] = int(health_score)
        if image_url is not None:
            observation_data["image_url"] = image_url
        
        print(f"Creating observation with data: {observation_data}")
        
        db_observation = ZoneCropObservation(**observation_data)
        session.add(db_observation)
        session.commit()
        session.refresh(db_observation)
        return db_observation
        
    except Exception as e:
        print(f"Error creating observation: {e}")
        session.rollback()
        raise HTTPException(status_code=400, detail=f"Error creating observation: {str(e)}")

