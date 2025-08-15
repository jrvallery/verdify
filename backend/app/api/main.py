from fastapi import APIRouter

from app.api.routes import greenhouses, login, private, users, utils, zones, controller, climate, sensors, crops, cropTemplates, observations
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router, prefix="/login", tags=["login"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(utils.router, prefix="/utils", tags=["utils"])
api_router.include_router(greenhouses.router, prefix="/greenhouses", tags=["greenhouses"])
api_router.include_router(crops.router, prefix="/crops", tags=["crops"])
api_router.include_router(cropTemplates.router, prefix="/crop-templates", tags=["crop-templates"])
api_router.include_router(observations.router, prefix="/observations", tags=["observations"])

# Create a sub-router for greenhouse-specific routes
greenhouse_subrouter = APIRouter()

# greenhouse_subrouter.include_router(climate.router, prefix="/climate", tags=["climate"])
greenhouse_subrouter.include_router(controller.router, prefix="/controllers", tags=["controllers"])
greenhouse_subrouter.include_router(zones.router, prefix="/zones", tags=["zones"])

# Mount the sub-router under the greenhouse path
api_router.include_router(greenhouse_subrouter, prefix="/greenhouses/{greenhouse_id}")

# Mount sensors under controllers
api_router.include_router(sensors.router, prefix="/greenhouses/{greenhouse_id}/controllers/{controller_id}/sensors", tags=["sensors"])

if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
