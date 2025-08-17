# from fastapi import APIRouter, HTTPException, status
# from uuid import UUID

# from app.api.deps import SessionDep, CurrentUser
# from app.models import (
#     Greenhouse,
#     GreenhousePublic,
#     GreenhouseClimateUpdate,
#     GreenhouseClimateRead,
# )

# router = APIRouter()

# @router.put("/",response_model=GreenhousePublic,status_code=status.HTTP_200_OK,)
# def update_climate(
#     greenhouse_id: UUID,
#     climate_in: GreenhouseClimateUpdate,
#     session: SessionDep,
#     current_user: CurrentUser,
# ) -> Greenhouse:
#     gh = session.get(Greenhouse, greenhouse_id)
#     if not gh:
#         raise HTTPException(status.HTTP_404_NOT_FOUND, "Greenhouse not found")
#     if not (current_user.is_superuser or gh.owner_id == current_user.id):
#         raise HTTPException(status.HTTP_403_FORBIDDEN, "Not enough permissions")

#     updates = climate_in.model_dump(exclude_unset=True)
#     for field, value in updates.items():
#         setattr(gh, field, value)

#     session.add(gh)
#     session.commit()
#     session.refresh(gh)
#     return gh


# @router.get("/", response_model=GreenhouseClimateRead, status_code=status.HTTP_200_OK,)
# def read_climate(
#     greenhouse_id: UUID,
#     session: SessionDep,
#     current_user: CurrentUser,
# ) -> GreenhouseClimateRead:
#     gh = session.get(Greenhouse, greenhouse_id)
#     if not gh:
#         raise HTTPException(status.HTTP_404_NOT_FOUND, "Greenhouse not found")
#     if not (current_user.is_superuser or gh.owner_id == current_user.id):
#         raise HTTPException(status.HTTP_403_FORBIDDEN, "Not enough permissions")

#     return GreenhouseClimateRead(
#         temperature=gh.temperature,
#         humidity=gh.humidity,
#         outside_temperature=gh.outside_temperature,
#         outside_humidity=gh.outside_humidity,
#     )
