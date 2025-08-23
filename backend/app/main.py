import sentry_sdk
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.routing import APIRoute
from pydantic import ValidationError
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.core.config import settings
from app.utils.log import get_structured_logger, setup_logging
from app.utils.logging_middleware import setup_logging_middleware
from app.utils_errors import (
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.utils_request_id import RequestIdMiddleware

# Setup structured logging as early as possible
setup_logging(log_level=settings.LOG_LEVEL)

# Get logger for this module
logger = get_structured_logger(__name__)


def custom_generate_unique_id(route: APIRoute) -> str:
    # Use the first tag if present, otherwise fallback to the route name
    tag = route.tags[0] if route.tags else route.name
    return f"{tag}-{route.name}"


def custom_openapi():
    """
    Custom OpenAPI schema generator to set Project Verdify metadata and security schemes.

    Sets the title, version, description, and security schemes to match
    the OpenAPI specification requirements.
    """
    if app.openapi_schema:
        return app.openapi_schema

    from fastapi.openapi.utils import get_openapi

    openapi_schema = get_openapi(
        title="Project Verdify MVP API",
        version="2.0",
        description=(
            "REST API for AI-powered greenhouse MVP. HTTPS required for all endpoints. "
            "Metric units on wire. ETag used for config/plan. Device identity via device_name (verdify-aabbcc). "
            "Rate limiting applies to telemetry endpoints to prevent DoS attacks."
        ),
        routes=app.routes,
    )

    # Add security schemes matching the OpenAPI specification
    openapi_schema["components"]["securitySchemes"] = {
        "UserJWT": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "User JWT for app/admin calls",
        },
        "DeviceToken": {
            "type": "apiKey",
            "in": "header",
            "name": "X-Device-Token",
            "description": "Long-lived device token for controllers",
        },
    }

    # Add license information
    openapi_schema["info"]["license"] = {
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    }

    # Add server information
    openapi_schema["servers"] = [{"url": "https://api.verdify.ai/api/v1"}]

    # Add tags for API organization
    openapi_schema["tags"] = [
        {
            "name": "Authentication",
            "description": "User and device authentication endpoints including registration, login, and token management",
        },
        {
            "name": "Onboarding",
            "description": "Device discovery, claiming, and initial setup endpoints",
        },
        {
            "name": "Config",
            "description": "Configuration management including publishing, fetching, and diff operations",
        },
        {"name": "Plan", "description": "Cultivation plan management and retrieval"},
        {
            "name": "Telemetry",
            "description": "Device telemetry ingestion endpoints for sensors, actuators, status, and inputs",
        },
        {
            "name": "CRUD",
            "description": "Create, read, update, delete operations for resources like greenhouses, controllers, sensors, actuators",
        },
        {"name": "Meta", "description": "Health and metadata endpoints"},
    ]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)
    logger.info("Sentry monitoring enabled", extra={"dsn_configured": True})

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)

# Log application startup
logger.info(
    "FastAPI application starting",
    extra={
        "project_name": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "api_version": settings.API_V1_STR,
        "debug_mode": settings.DEBUG if hasattr(settings, "DEBUG") else False,
    },
)

# Override the OpenAPI schema with our custom metadata
app.openapi = custom_openapi

# Add middleware in correct order:
# 1. Request ID middleware (generates/preserves request IDs)
app.add_middleware(RequestIdMiddleware)

# 2. GZip compression middleware
app.add_middleware(GZipMiddleware, minimum_size=500)

# 3. Logging middleware (logs requests with correlation)
setup_logging_middleware(app)

# 3. CORS middleware
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info(
        "CORS middleware enabled", extra={"allowed_origins": settings.all_cors_origins}
    )

# Register exception handlers for standardized error responses
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(ValidationError, validation_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Include API routes
app.include_router(api_router, prefix=settings.API_V1_STR)


# Add startup and shutdown event handlers for logging
@app.on_event("startup")
async def startup_event():
    """Log application startup completion and bootstrap mappers."""
    # Import models and bootstrap mappers for early failure detection
    import app.models as models

    models.bootstrap_mappers()

    logger.info(
        "Application startup completed",
        extra={
            "status": "ready",
            "api_docs_url": f"{settings.API_V1_STR}/docs",
            "health_check_url": f"{settings.API_V1_STR}/health",
        },
    )


@app.on_event("shutdown")
async def shutdown_event():
    """Log application shutdown."""
    logger.info("Application shutdown initiated")
