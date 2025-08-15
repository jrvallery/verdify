from fastapi import APIRouter, Depends, HTTPException
from typing import List
# ...existing code...
from app.api.deps import get_current_user, SessionDep
from app.crud.cropTemplates import cropTemplates
from app.models import (
    User,
    CropTemplate, CropTemplateCreate, CropTemplatePublic, CropTemplateUpdate,
)

router = APIRouter()

@router.get("/", response_model=List[CropTemplatePublic])
def list_crop_templates(
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    return cropTemplates.get_multi(session)

@router.post("/", response_model=CropTemplatePublic)
def create_crop_template(
    crop_in: CropTemplateCreate,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    return cropTemplates.create(session, obj_in=crop_in)

@router.get("/{crop_template_id}", response_model=CropTemplatePublic)
def get_crop_template(
    crop_template_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    db_obj = cropTemplates.get(session, id=crop_template_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Crop template not found")
    return db_obj

@router.patch("/{crop_template_id}", response_model=CropTemplatePublic)
def update_crop_template(
    crop_template_id: str,
    crop_in: CropTemplateUpdate,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    db_obj = cropTemplates.get(session, id=crop_template_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Crop template not found")
    return cropTemplates.update(session, db_obj=db_obj, obj_in=crop_in)

@router.delete("/{crop_template_id}")
def delete_crop_template(
    crop_template_id: str,
    session: SessionDep,
    current_user: User = Depends(get_current_user),
):
    db_obj = cropTemplates.remove(session, id=crop_template_id)
    if not db_obj:
        raise HTTPException(status_code=404, detail="Crop template not found")
    return {"message": "Crop template deleted successfully"}
