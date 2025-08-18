from fastapi import APIRouter

from app.api.routes import (
    actuators,
    auth_extras,
    buttons,
    config_admin,
    config_device,
    controllers_crud,
    crops,  # Re-enabled - import works
    fan_groups,
    greenhouses,
    meta,
    observations,  # Re-enabled for H4 testing
    onboarding,
    plans,
    private,
    sensor_zone_maps,
    sensors,
    state_machine,  # Re-enabled - import works now
    telemetry,  # Re-enabled - import works now
    users,
    utils,
    zone_crops,  # Re-enabled - import works
    zones_crud,  # Re-enabled - import works
)
from app.core.config import settings

api_router = APIRouter()

# Meta endpoints (no authentication required)
api_router.include_router(meta.router, tags=["Meta"])

api_router.include_router(auth_extras.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(
    auth_extras.legacy_login_router, prefix="/login", tags=["Authentication"]
)
api_router.include_router(onboarding.router, tags=["Onboarding"])
api_router.include_router(config_admin.router, tags=["Config"])
api_router.include_router(config_device.router, tags=["Config"])
api_router.include_router(plans.router, tags=["Plan"])
api_router.include_router(
    telemetry.router, prefix="/telemetry", tags=["Telemetry"]
)  # Re-enabled
api_router.include_router(users.router, prefix="/users", tags=["Authentication"])
api_router.include_router(utils.router, prefix="/utils", tags=["Meta"])
api_router.include_router(greenhouses.router, prefix="/greenhouses", tags=["CRUD"])
# api_router.include_router(crops.router, prefix="/crops", tags=["crops"])  # Temporarily disabled

# Top-level CRUD endpoints (per OpenAPI spec)
api_router.include_router(zones_crud.router, prefix="/zones", tags=["CRUD"])
api_router.include_router(
    zone_crops.router, tags=["CRUD"]
)  # Routes already include "/zone-crops" prefix
api_router.include_router(crops.router, prefix="/crops", tags=["CRUD"])

# Enable observations router - routes already include "/observations" prefix
api_router.include_router(observations.router, tags=["CRUD"])
api_router.include_router(controllers_crud.router, prefix="/controllers", tags=["CRUD"])
api_router.include_router(sensors.router, prefix="/sensors", tags=["CRUD"])
api_router.include_router(
    sensor_zone_maps.router, prefix="/sensor-zone-maps", tags=["CRUD"]
)
api_router.include_router(actuators.router, prefix="/actuators", tags=["CRUD"])
api_router.include_router(fan_groups.router, prefix="/fan-groups", tags=["CRUD"])
api_router.include_router(buttons.router, prefix="/buttons", tags=["CRUD"])
api_router.include_router(
    state_machine.router, prefix="/state-machine-rows", tags=["CRUD"]
)  # Re-enabled
api_router.include_router(
    state_machine.fallback_router, prefix="/state-machine-fallback", tags=["CRUD"]
)  # Re-enabled

# Create a sub-router for greenhouse-specific routes
greenhouse_subrouter = APIRouter()

# Remove nested controller routes to avoid duplication with top-level /controllers
# greenhouse_subrouter.include_router(
#     controller.router, prefix="/controllers", tags=["CRUD"]
# )
# Note: zones.router removed - only top-level /zones/ per OpenAPI spec

# Mount the sub-router under the greenhouse path (for future greenhouse-specific endpoints)
# api_router.include_router(greenhouse_subrouter, prefix="/greenhouses/{greenhouse_id}")

if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
