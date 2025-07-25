from fastapi import APIRouter

from app.api.routes import greenhouses, login, private, users, utils, zones, equipment
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(greenhouses.router)
api_router.include_router(zones.router)
api_router.include_router(equipment.router)

if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
