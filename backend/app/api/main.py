from fastapi import APIRouter

from app.api.routes import greenhouses, login, private, users, utils, zones, equipment, climate
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router, prefix="/login", tags=["login"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(utils.router, prefix="/utils", tags=["utils"])
api_router.include_router(greenhouses.router, prefix="/greenhouses", tags=["greenhouses"])

# Group all per-greenhouse sub-routes under a shared prefix
greenhouse_router = APIRouter(prefix="/greenhouses/{greenhouse_id}", tags=["greenhouse"])
greenhouse_router.include_router(zones.router,      prefix="/zones",      tags=["zones"])
greenhouse_router.include_router(equipment.router,  prefix="/equipment", tags=["equipment"])
greenhouse_router.include_router(climate.router,    prefix="/climate",   tags=["climate"])
api_router.include_router(greenhouse_router)

if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
