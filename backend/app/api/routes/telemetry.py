"""
Telemetry ingestion endpoints.

Handles ingestion of sensor readings, actuator events, controller status,
input events, and mixed batches with idempotency and rate limiting.

Endpoints:
- POST /telemetry/sensors - Ingest sensor readings
- POST /telemetry/actuators - Ingest actuator events
- POST /telemetry/status - Ingest controller status
- POST /telemetry/inputs - Ingest input/button events
- POST /telemetry/batch - Ingest mixed telemetry batch
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app.api.deps import CurrentDevice, SessionDep
from app.core.rate_limit import (
    RateLimiter,
    create_rate_limit_headers,
    create_retry_after_header,
    get_rate_limiter,
)
from app.crud.idempotency import (
    check_idempotency,
    hash_request_body,
    store_idempotent_response,
)
from app.models import Controller
from app.models.telemetry import (
    IngestResult,
    TelemetryActuators,
    TelemetryBatch,
    TelemetryInputs,
    TelemetrySensors,
    TelemetryStatus,
)
from app.utils_errors import ErrorResponse
from app.utils_request_id import get_request_id

router = APIRouter()


async def _get_request_body_hash(request: Request) -> str:
    """Get hash of request body for idempotency checking."""
    body = await request.body()
    return hash_request_body(body)


def _convert_uuids_to_strings(obj: Any) -> Any:
    """Recursively convert UUID objects to strings for JSON serialization."""
    if isinstance(obj, uuid.UUID):
        return str(obj)
    elif isinstance(obj, dict):
        return {key: _convert_uuids_to_strings(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_convert_uuids_to_strings(item) for item in obj]
    else:
        return obj


async def _handle_idempotency(
    session: Session,
    request: Request,
    controller: Controller,
    idempotency_key: str | None,
) -> JSONResponse | None:
    """
    Check idempotency and return cached response if request already processed.

    Returns:
        JSONResponse if request is duplicate, None if request is new
    """
    if not idempotency_key:
        return None

    body_hash = await _get_request_body_hash(request)

    cached_response = check_idempotency(
        session, key=idempotency_key, controller_id=controller.id, body_hash=body_hash
    )

    if cached_response:
        # Return cached response with idempotent indication
        response_body = cached_response.get("body")
        if response_body:
            content = json.loads(response_body)
            # Add idempotent warning to indicate this was a replay
            if "warnings" not in content:
                content["warnings"] = []
            content["warnings"].append("Request already processed (idempotent)")
        else:
            # Default response for idempotent requests
            content = {
                "accepted": 0,
                "rejected": 0,
                "warnings": ["Request already processed (idempotent)"],
            }

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=content,
            headers={"X-Request-Id": get_request_id(request)},
        )

    return None


async def _check_rate_limit(
    controller: Controller, rate_limiter: RateLimiter, endpoint_type: str = "telemetry"
) -> JSONResponse | None:
    """
    Check rate limit and return 429 response if exceeded.

    Returns:
        JSONResponse with 429 status if rate limit exceeded, None if within limits
    """
    is_allowed, rate_limit = await rate_limiter.check_rate_limit(
        str(controller.id), endpoint_type
    )

    if not is_allowed:
        # Rate limit exceeded
        headers = {
            **create_rate_limit_headers(rate_limit),
            **create_retry_after_header(rate_limit),
        }

        error_response = ErrorResponse(
            error_code="E429_TOO_MANY_REQUESTS",
            message=f"Rate limit exceeded. Try again in {rate_limit.reset_time - int(datetime.now(timezone.utc).timestamp())} seconds.",
            request_id="rate-limit-check",  # Will be replaced by actual request ID
        )

        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=error_response.model_dump(mode="json"),
            headers=headers,
        )

    return None


async def _store_response(
    session: Session,
    controller: Controller,
    idempotency_key: str | None,
    request: Request,
    response_body: dict[str, Any],
) -> None:
    """Store response for idempotency replay."""
    if idempotency_key:
        body_hash = await _get_request_body_hash(request)

        store_idempotent_response(
            session,
            key=idempotency_key,
            controller_id=controller.id,
            body_hash=body_hash,
            response_status=202,
            response_body=json.dumps(_convert_uuids_to_strings(response_body)),
        )

        # Force commit to ensure it's persisted
        session.commit()


def _process_sensor_telemetry(
    sensors_data: TelemetrySensors, controller: Controller
) -> IngestResult:
    """
    Process sensor telemetry data.

    For MVP: validates data and returns success counts.
    In production: would store to TimescaleDB.
    """
    accepted = 0
    rejected = 0
    errors = []

    # Validate and count readings
    for reading in sensors_data.readings:
        try:
            # Basic validation - sensor exists and belongs to controller
            # In production: validate sensor_id against controller's sensors
            # For now: just count as accepted
            accepted += 1
        except Exception as e:
            rejected += 1
            errors.append(
                {
                    "error_code": "SENSOR_PROCESSING_ERROR",
                    "message": f"Failed to process sensor reading {reading.sensor_id}: {str(e)}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

    return IngestResult(accepted=accepted, rejected=rejected, errors=errors)


def _process_actuator_telemetry(
    actuators_data: TelemetryActuators, controller: Controller
) -> IngestResult:
    """
    Process actuator telemetry data.

    For MVP: validates data and returns success counts.
    In production: would store to TimescaleDB.
    """
    accepted = 0
    rejected = 0
    errors = []

    # Validate and count events
    for event in actuators_data.events:
        try:
            # Basic validation - actuator exists and belongs to controller
            # In production: validate actuator_id against controller's actuators
            # For now: just count as accepted
            accepted += 1
        except Exception as e:
            rejected += 1
            errors.append(
                {
                    "error_code": "ACTUATOR_PROCESSING_ERROR",
                    "message": f"Failed to process actuator event {event.actuator_id}: {str(e)}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

    return IngestResult(accepted=accepted, rejected=rejected, errors=errors)


def _process_status_telemetry(
    status_data: TelemetryStatus, controller: Controller
) -> IngestResult:
    """
    Process status telemetry data.

    For MVP: validates data and returns success.
    In production: would store to TimescaleDB.
    """
    try:
        # Validate stages are within range
        if not (-3 <= status_data.temp_stage <= 3):
            raise ValueError(
                f"temp_stage {status_data.temp_stage} outside range [-3, 3]"
            )

        if not (-3 <= status_data.humi_stage <= 3):
            raise ValueError(
                f"humi_stage {status_data.humi_stage} outside range [-3, 3]"
            )

        # In production: store status data
        return IngestResult(accepted=1, rejected=0, errors=[])

    except Exception as e:
        return IngestResult(
            accepted=0,
            rejected=1,
            errors=[
                {
                    "error_code": "STATUS_PROCESSING_ERROR",
                    "message": f"Failed to process status: {str(e)}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
        )


def _process_input_telemetry(
    inputs_data: TelemetryInputs, controller: Controller
) -> IngestResult:
    """
    Process input telemetry data.

    For MVP: validates data and returns success counts.
    In production: would store to TimescaleDB.
    """
    accepted = 0
    rejected = 0
    errors = []

    # Validate and count events
    for event in inputs_data.inputs:  # Fixed: inputs_data.inputs not .events
        try:
            # Basic validation - button kind is valid
            # In production: validate button configuration exists for controller
            # For now: just count as accepted
            accepted += 1
        except Exception as e:
            rejected += 1
            errors.append(
                {
                    "error_code": "INPUT_PROCESSING_ERROR",
                    "message": f"Failed to process input event {event.button_kind}: {str(e)}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

    return IngestResult(accepted=accepted, rejected=rejected, errors=errors)


@router.post(
    "/sensors",
    summary="Ingest sensor readings (batch)",
    description="Ingest sensor readings from devices with rate limiting and idempotency",
    response_model=IngestResult,
    responses={
        202: {
            "description": "Accepted",
            "headers": {
                "X-RateLimit-Limit": {
                    "description": "Number of requests allowed per time window",
                    "schema": {"type": "integer"},
                },
                "X-RateLimit-Remaining": {
                    "description": "Number of requests remaining in current window",
                    "schema": {"type": "integer"},
                },
                "X-RateLimit-Reset": {
                    "description": "UTC timestamp when rate limit window resets",
                    "schema": {"type": "integer"},
                },
            },
        },
        400: {"description": "Bad Request"},
        401: {"description": "Unauthorized"},
        429: {"description": "Too Many Requests"},
    },
    status_code=202,
    operation_id="ingestSensorTelemetry",
)
async def ingest_sensor_telemetry(
    request: Request,
    session: SessionDep,
    controller: CurrentDevice,
    sensors_data: TelemetrySensors,
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> JSONResponse:
    """Ingest sensor readings batch."""

    # Check for idempotent request
    idempotent_response = await _handle_idempotency(
        session, request, controller, idempotency_key
    )
    if idempotent_response:
        return idempotent_response

    # Check rate limit
    rate_limit_response = await _check_rate_limit(controller, rate_limiter, "telemetry")
    if rate_limit_response:
        return rate_limit_response

    # Process telemetry
    result = _process_sensor_telemetry(sensors_data, controller)

    # Store response for idempotency
    response_body = result.model_dump(mode="json")
    await _store_response(session, controller, idempotency_key, request, response_body)

    # Get rate limit info for headers
    _, rate_limit = await rate_limiter.check_rate_limit(str(controller.id), "telemetry")
    headers = create_rate_limit_headers(rate_limit)

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=response_body,
        headers={**headers, "X-Request-Id": get_request_id(request)},
    )


@router.post(
    "/actuators",
    summary="Ingest actuator events (batch)",
    description="Ingest actuator state changes from devices with rate limiting and idempotency",
    response_model=IngestResult,
    responses={
        202: {
            "description": "Accepted",
            "headers": {
                "X-RateLimit-Limit": {
                    "description": "Number of requests allowed per time window",
                    "schema": {"type": "integer"},
                },
                "X-RateLimit-Remaining": {
                    "description": "Number of requests remaining in current window",
                    "schema": {"type": "integer"},
                },
                "X-RateLimit-Reset": {
                    "description": "UTC timestamp when rate limit window resets",
                    "schema": {"type": "integer"},
                },
            },
        },
        400: {"description": "Bad Request"},
        401: {"description": "Unauthorized"},
        429: {"description": "Too Many Requests"},
    },
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="ingestActuatorTelemetry",
)
async def ingest_actuator_telemetry(
    request: Request,
    session: SessionDep,
    controller: CurrentDevice,
    actuators_data: TelemetryActuators,
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> JSONResponse:
    """Ingest actuator edge events."""

    # Check for idempotent request
    idempotent_response = await _handle_idempotency(
        session, request, controller, idempotency_key
    )
    if idempotent_response:
        return idempotent_response

    # Check rate limit
    rate_limit_response = await _check_rate_limit(controller, rate_limiter, "telemetry")
    if rate_limit_response:
        return rate_limit_response

    # Process telemetry
    result = _process_actuator_telemetry(actuators_data, controller)

    # Store response for idempotency
    response_body = result.model_dump(mode="json")
    await _store_response(session, controller, idempotency_key, request, response_body)

    # Get rate limit info for headers
    _, rate_limit = await rate_limiter.check_rate_limit(str(controller.id), "telemetry")
    headers = create_rate_limit_headers(rate_limit)

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=response_body,
        headers={**headers, "X-Request-Id": get_request_id(request)},
    )


@router.post(
    "/status",
    summary="Ingest controller status",
    description="Ingest controller status and operational metrics with rate limiting and idempotency",
    response_model=IngestResult,
    responses={
        202: {
            "description": "Accepted",
            "headers": {
                "X-RateLimit-Limit": {
                    "description": "Number of requests allowed per time window",
                    "schema": {"type": "integer"},
                },
                "X-RateLimit-Remaining": {
                    "description": "Number of requests remaining in current window",
                    "schema": {"type": "integer"},
                },
                "X-RateLimit-Reset": {
                    "description": "UTC timestamp when rate limit window resets",
                    "schema": {"type": "integer"},
                },
            },
        },
        400: {"description": "Bad Request"},
        401: {"description": "Unauthorized"},
        429: {"description": "Too Many Requests"},
    },
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="ingestStatusTelemetry",
)
async def ingest_status_telemetry(
    request: Request,
    session: SessionDep,
    controller: CurrentDevice,
    status_data: TelemetryStatus,
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> JSONResponse:
    """Ingest controller status frames."""

    # Check for idempotent request
    idempotent_response = await _handle_idempotency(
        session, request, controller, idempotency_key
    )
    if idempotent_response:
        return idempotent_response

    # Check rate limit
    rate_limit_response = await _check_rate_limit(controller, rate_limiter, "telemetry")
    if rate_limit_response:
        return rate_limit_response

    # Process telemetry
    result = _process_status_telemetry(status_data, controller)

    # Store response for idempotency
    response_body = result.model_dump(mode="json")
    await _store_response(session, controller, idempotency_key, request, response_body)

    # Get rate limit info for headers
    _, rate_limit = await rate_limiter.check_rate_limit(str(controller.id), "telemetry")
    headers = create_rate_limit_headers(rate_limit)

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=response_body,
        headers={**headers, "X-Request-Id": get_request_id(request)},
    )


@router.post(
    "/inputs",
    summary="Ingest input/button events (batch)",
    description="Ingest manual input and button press events from devices with rate limiting and idempotency",
    response_model=IngestResult,
    responses={
        202: {
            "description": "Accepted",
            "headers": {
                "X-RateLimit-Limit": {
                    "description": "Number of requests allowed per time window",
                    "schema": {"type": "integer"},
                },
                "X-RateLimit-Remaining": {
                    "description": "Number of requests remaining in current window",
                    "schema": {"type": "integer"},
                },
                "X-RateLimit-Reset": {
                    "description": "UTC timestamp when rate limit window resets",
                    "schema": {"type": "integer"},
                },
            },
        },
        400: {"description": "Bad Request"},
        401: {"description": "Unauthorized"},
        429: {"description": "Too Many Requests"},
    },
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="ingestInputTelemetry",
)
async def ingest_input_telemetry(
    request: Request,
    session: SessionDep,
    controller: CurrentDevice,
    inputs_data: TelemetryInputs,
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> JSONResponse:
    """Ingest input/button events."""

    # Check for idempotent request
    idempotent_response = await _handle_idempotency(
        session, request, controller, idempotency_key
    )
    if idempotent_response:
        return idempotent_response

    # Check rate limit
    rate_limit_response = await _check_rate_limit(controller, rate_limiter, "telemetry")
    if rate_limit_response:
        return rate_limit_response

    # Process telemetry
    result = _process_input_telemetry(inputs_data, controller)

    # Store response for idempotency
    response_body = result.model_dump(mode="json")
    await _store_response(session, controller, idempotency_key, request, response_body)

    # Get rate limit info for headers
    _, rate_limit = await rate_limiter.check_rate_limit(str(controller.id), "telemetry")
    headers = create_rate_limit_headers(rate_limit)

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=response_body,
        headers={**headers, "X-Request-Id": get_request_id(request)},
    )


@router.post(
    "/batch",
    summary="Ingest mixed telemetry batch",
    description="Ingest a mixed batch of telemetry data (sensors, actuators, status, inputs) with rate limiting and idempotency",
    response_model=IngestResult,
    responses={
        202: {
            "description": "Accepted",
            "headers": {
                "X-RateLimit-Limit": {
                    "description": "Number of requests allowed per time window",
                    "schema": {"type": "integer"},
                },
                "X-RateLimit-Remaining": {
                    "description": "Number of requests remaining in current window",
                    "schema": {"type": "integer"},
                },
                "X-RateLimit-Reset": {
                    "description": "UTC timestamp when rate limit window resets",
                    "schema": {"type": "integer"},
                },
            },
        },
        400: {"description": "Bad Request"},
        401: {"description": "Unauthorized"},
        429: {"description": "Too Many Requests"},
    },
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="ingestTelemetryBatch",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "comprehensive_batch": {
                            "summary": "Complete telemetry batch with all data types",
                            "value": {
                                "sensors": {
                                    "batch_id": "batch_20250813_180500",
                                    "ts_utc": "2025-08-13T18:05:00Z",
                                    "readings": [
                                        {
                                            "sensor_id": "550e8400-e29b-41d4-a716-446655440001",
                                            "kind": "temperature",
                                            "value": 24.6,
                                            "ts_utc": "2025-08-13T18:05:00Z",
                                            "scope": "zone",
                                            "zone_ids": [
                                                "550e8400-e29b-41d4-a716-446655440002"
                                            ],
                                        },
                                        {
                                            "sensor_id": "550e8400-e29b-41d4-a716-446655440003",
                                            "kind": "humidity",
                                            "value": 61.5,
                                            "ts_utc": "2025-08-13T18:05:00Z",
                                            "scope": "greenhouse",
                                        },
                                    ],
                                },
                                "actuators": {
                                    "events": [
                                        {
                                            "actuator_id": "550e8400-e29b-41d4-a716-446655440004",
                                            "ts_utc": "2025-08-13T18:04:45Z",
                                            "state": True,
                                            "reason": "temp_stage_1",
                                        }
                                    ]
                                },
                                "status": {
                                    "ts_utc": "2025-08-13T18:05:00Z",
                                    "temp_stage": 1,
                                    "humi_stage": 0,
                                    "avg_interior_temp_c": 24.6,
                                    "avg_interior_rh_pct": 61.5,
                                    "plan_version": 17,
                                },
                                "inputs": {
                                    "inputs": [
                                        {
                                            "button_kind": "cool",
                                            "ts_utc": "2025-08-13T18:04:30Z",
                                            "action": "pressed",
                                        }
                                    ]
                                },
                            },
                        }
                    }
                }
            }
        }
    },
)
async def ingest_telemetry_batch(
    request: Request,
    session: SessionDep,
    controller: CurrentDevice,
    batch_data: TelemetryBatch,
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    content_encoding: str | None = Header(None, alias="Content-Encoding"),
) -> JSONResponse:
    """Ingest mixed telemetry batch (supports gzip compression)."""

    # Check for idempotent request
    idempotent_response = await _handle_idempotency(
        session, request, controller, idempotency_key
    )
    if idempotent_response:
        return idempotent_response

    # Check rate limit (batch endpoint has different limits)
    rate_limit_response = await _check_rate_limit(controller, rate_limiter, "batch")
    if rate_limit_response:
        return rate_limit_response

    # Process each type of telemetry in the batch
    total_accepted = 0
    total_rejected = 0
    all_errors = []

    # Process sensors
    if batch_data.sensors:
        sensors_batch = TelemetrySensors(
            batch_id=batch_data.batch_id,
            ts_utc=batch_data.ts_utc,
            readings=batch_data.sensors,
        )
        result = _process_sensor_telemetry(sensors_batch, controller)
        total_accepted += result.accepted
        total_rejected += result.rejected
        all_errors.extend([{**e, "context": "sensors"} for e in result.errors])

    # Process actuators
    if batch_data.actuators:
        actuators_batch = TelemetryActuators(
            batch_id=batch_data.batch_id,
            ts_utc=batch_data.ts_utc,
            events=batch_data.actuators,
        )
        result = _process_actuator_telemetry(actuators_batch, controller)
        total_accepted += result.accepted
        total_rejected += result.rejected
        all_errors.extend([{**e, "context": "actuators"} for e in result.errors])

    # Process status
    if batch_data.status:
        result = _process_status_telemetry(batch_data.status, controller)
        total_accepted += result.accepted
        total_rejected += result.rejected
        all_errors.extend([{**e, "context": "status"} for e in result.errors])

    # Process inputs
    if batch_data.inputs:
        inputs_batch = TelemetryInputs(
            batch_id=batch_data.batch_id,
            ts_utc=batch_data.ts_utc,
            events=batch_data.inputs,
        )
        result = _process_input_telemetry(inputs_batch, controller)
        total_accepted += result.accepted
        total_rejected += result.rejected
        all_errors.extend([{**e, "context": "inputs"} for e in result.errors])

    # Create aggregate result
    aggregate_result = IngestResult(
        accepted=total_accepted, rejected=total_rejected, errors=all_errors
    )

    # Store response for idempotency
    response_body = aggregate_result.model_dump(mode="json")
    await _store_response(session, controller, idempotency_key, request, response_body)

    # Get rate limit info for headers
    _, rate_limit = await rate_limiter.check_rate_limit(str(controller.id), "batch")
    headers = create_rate_limit_headers(rate_limit)

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=response_body,
        headers={**headers, "X-Request-Id": get_request_id(request)},
    )
