"""
Meta endpoints for health checks and metadata.

This module provides endpoints that don't require authentication:
- /health - Health status for load balancers and monitoring
- /meta/sensor-kinds - Available sensor types for device configuration
- /meta/actuator-kinds - Available actuator types for device configuration

All endpoints match the OpenAPI specification exactly.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.models import ActuatorKind, SensorKind

router = APIRouter()


@router.get(
    "/health",
    summary="Health check endpoint",
    description="Returns service health status for load balancers and monitoring",
    response_model=dict,
    responses={
        200: {
            "description": "Service is healthy",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "timestamp": "2025-08-13T18:05:00Z",
                        "version": "1.0.0",
                    }
                }
            },
        },
        503: {
            "description": "Service unavailable",
            "content": {
                "application/json": {
                    "example": {
                        "status": "unhealthy",
                        "timestamp": "2025-08-13T18:05:00Z",
                        "error": "Database connection failed",
                    }
                }
            },
        },
    },
    operation_id="getHealthStatus",
)
async def get_health_status():
    """
    Get API health status.

    Returns health information including:
    - Service status (healthy/unhealthy)
    - Current timestamp
    - API version

    This endpoint is used by load balancers and monitoring systems
    to check if the service is available and responsive.
    """
    try:
        # Basic health check - could be extended to check database, Redis, etc.
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "version": "2.0",
        }
    except Exception as e:
        # Return 503 for any system errors
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "timestamp": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "error": str(e),
            },
        )


@router.get(
    "/meta/sensor-kinds",
    summary="Get available sensor kinds",
    description="Returns list of supported sensor types for device configuration",
    response_model=dict,
    responses={
        200: {
            "description": "List of sensor kinds",
            "content": {
                "application/json": {
                    "example": {
                        "sensor_kinds": [
                            "temperature",
                            "humidity",
                            "vpd",
                            "co2",
                            "light",
                            "soil_moisture",
                        ]
                    }
                }
            },
        },
        503: {
            "description": "Service unavailable (meta service down)",
            "content": {
                "application/json": {
                    "example": {"error": "Meta service temporarily unavailable"}
                }
            },
        },
    },
    operation_id="getSensorKinds",
)
async def get_sensor_kinds():
    """
    Get all supported sensor kinds.

    Returns a list of sensor types that can be configured on controllers.
    This information is used by device configuration UIs to present
    available sensor options to users.

    Returns:
        dict: Object with sensor_kinds array containing all supported sensor types
    """
    try:
        # Get all sensor kinds from the enum
        sensor_kinds = [kind.value for kind in SensorKind]

        return {"sensor_kinds": sensor_kinds}
    except Exception as e:
        raise HTTPException(
            status_code=503, detail={"error": f"Meta service error: {str(e)}"}
        )


@router.get(
    "/meta/actuator-kinds",
    summary="Get available actuator kinds",
    description="Returns list of supported actuator types for device configuration",
    response_model=dict,
    responses={
        200: {
            "description": "List of actuator kinds",
            "content": {
                "application/json": {
                    "example": {
                        "actuator_kinds": [
                            "fan",
                            "heater",
                            "vent",
                            "fogger",
                            "irrigation_valve",
                            "fertilizer_valve",
                            "pump",
                            "light",
                        ]
                    }
                }
            },
        },
        503: {
            "description": "Service unavailable (meta service down)",
            "content": {
                "application/json": {
                    "example": {"error": "Meta service temporarily unavailable"}
                }
            },
        },
    },
    operation_id="getActuatorKinds",
)
async def get_actuator_kinds():
    """
    Get all supported actuator kinds.

    Returns a list of actuator types that can be configured on controllers.
    This information is used by device configuration UIs to present
    available actuator options to users.

    Returns:
        dict: Object with actuator_kinds array containing all supported actuator types
    """
    try:
        # Get all actuator kinds from the enum
        actuator_kinds = [kind.value for kind in ActuatorKind]

        return {"actuator_kinds": actuator_kinds}
    except Exception as e:
        raise HTTPException(
            status_code=503, detail={"error": f"Meta service error: {str(e)}"}
        )
