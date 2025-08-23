"""
Structured logging utilities for Project Verdify API.

Provides request correlation, user/device context, and structured log formats
for better observability and debugging of complex flows.
"""

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from typing import Any

from fastapi import Request

from app.models import Controller, User

# Context variables for storing request context across async boundaries
_request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
_user_context: ContextVar[dict[str, Any] | None] = ContextVar("user", default=None)
_device_context: ContextVar[dict[str, Any] | None] = ContextVar("device", default=None)


class StructuredFormatter(logging.Formatter):
    """
    JSON-structured log formatter that includes request context.

    Formats logs as JSON with consistent fields:
    - timestamp: ISO format timestamp
    - level: Log level (INFO, ERROR, etc.)
    - message: The log message
    - request_id: Request correlation ID
    - user: User context (if available)
    - device: Device context (if available)
    - module: Python module name
    - function: Function name where log was called
    """
    
    _std = {
        "name","msg","args","levelname","levelno","pathname","filename","module",
        "exc_info","exc_text","stack_info","lineno","funcName","created","msecs",
        "relativeCreated","thread","threadName","processName","process","message",
    }

    def formatTime(self, record, datefmt=None):
        # ISO 8601 with timezone
        from datetime import datetime, timezone
        return datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()

    def format(self, record: logging.LogRecord) -> str:
        base = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Contexts
        request_id = _request_id_context.get()
        if request_id:
            base["request_id"] = request_id
        user_context = _user_context.get()
        if user_context:
            base["user"] = user_context
        device_context = _device_context.get()
        if device_context:
            base["device"] = device_context

        # Merge custom extras (anything added via logger(..., extra={...}))
        for k, v in record.__dict__.items():
            if k not in self._std and k not in base and not k.startswith("_"):
                base[k] = v

        if record.exc_info:
            base["exception"] = self.formatException(record.exc_info)

        return json.dumps(base, default=str)


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure structured logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Create formatter
    formatter = StructuredFormatter()

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Set specific loggers to appropriate levels
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.INFO)


def set_request_context(request: Request) -> None:
    """
    Set request context for logging correlation.

    Args:
        request: FastAPI request object
    """
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    _request_id_context.set(request_id)


def set_user_context(user: User) -> None:
    """
    Set user context for logging.

    Args:
        user: Authenticated user object
    """
    user_context = {
        "id": str(user.id),
        "email": user.email,
        "is_superuser": user.is_superuser,
        "is_active": user.is_active,
    }
    _user_context.set(user_context)


def set_device_context(controller: Controller) -> None:
    """
    Set device context for logging.

    Args:
        controller: Authenticated controller/device object
    """
    device_context = {
        "id": str(controller.id),
        "device_name": controller.device_name,
        "label": controller.label,
        "is_climate_controller": controller.is_climate_controller,
        "greenhouse_id": str(controller.greenhouse_id)
        if controller.greenhouse_id
        else None,
    }
    _device_context.set(device_context)


def clear_context() -> None:
    """Clear all logging context variables."""
    _request_id_context.set(None)
    _user_context.set(None)
    _device_context.set(None)


def get_structured_logger(name: str) -> logging.Logger:
    """
    Get a logger with structured formatting.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def log_request_start(
    request: Request, user: User | None = None, device: Controller | None = None
) -> None:
    """
    Log the start of a request with context.

    Args:
        request: FastAPI request object
        user: Authenticated user (if available)
        device: Authenticated device (if available)
    """
    logger = get_structured_logger("verdify.request")

    # Set contexts
    set_request_context(request)
    if user:
        set_user_context(user)
    if device:
        set_device_context(device)

    # Log request start
    logger.info(
        "Request started",
        extra={
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "user_agent": request.headers.get("user-agent"),
            "client_ip": request.client.host if request.client else None,
        },
    )


def log_request_end(
    request: Request, status_code: int, duration_ms: float | None = None
) -> None:
    """
    Log the end of a request.

    Args:
        request: FastAPI request object
        status_code: HTTP response status code
        duration_ms: Request duration in milliseconds
    """
    logger = get_structured_logger("verdify.request")

    extra_data = {
        "status_code": status_code,
        "method": request.method,
        "path": request.url.path,
    }

    if duration_ms is not None:
        extra_data["duration_ms"] = duration_ms

    logger.info("Request completed", extra=extra_data)


def log_authentication_event(
    event_type: str, success: bool, details: dict[str, Any] | None = None
) -> None:
    """
    Log authentication-related events.

    Args:
        event_type: Type of auth event (login, token_refresh, device_auth, etc.)
        success: Whether the authentication was successful
        details: Additional event details (should not include credentials)
    """
    logger = get_structured_logger("verdify.auth")

    log_data = {
        "event_type": event_type,
        "success": success,
    }

    if details:
        # Ensure we don't log sensitive information
        safe_details = {
            k: v
            for k, v in details.items()
            if k not in ("password", "token", "device_token", "secret")
        }
        log_data.update(safe_details)

    level = logging.INFO if success else logging.WARNING
    message = f"Authentication {event_type}: {'success' if success else 'failed'}"

    logger.log(level, message, extra=log_data)


def log_database_operation(
    operation: str,
    table: str,
    record_id: str | uuid.UUID | None = None,
    success: bool = True,
    error: str | None = None,
) -> None:
    """
    Log database operations for audit trails.

    Args:
        operation: Database operation (create, read, update, delete)
        table: Database table name
        record_id: Record identifier
        success: Whether operation succeeded
        error: Error message if operation failed
    """
    logger = get_structured_logger("verdify.database")

    log_data = {
        "operation": operation,
        "table": table,
        "success": success,
    }

    if record_id:
        log_data["record_id"] = str(record_id)

    if error:
        log_data["error"] = error

    level = logging.INFO if success else logging.ERROR
    message = f"Database {operation} on {table}: {'success' if success else 'failed'}"

    logger.log(level, message, extra=log_data)


def log_telemetry_event(
    event_type: str,
    controller_id: str | uuid.UUID,
    data_points: int,
    success: bool = True,
    error: str | None = None,
) -> None:
    """
    Log telemetry ingestion events.

    Args:
        event_type: Type of telemetry (sensor_readings, actuator_states, etc.)
        controller_id: ID of the controller sending telemetry
        data_points: Number of data points processed
        success: Whether processing succeeded
        error: Error message if processing failed
    """
    logger = get_structured_logger("verdify.telemetry")

    log_data = {
        "event_type": event_type,
        "controller_id": str(controller_id),
        "data_points": data_points,
        "success": success,
    }

    if error:
        log_data["error"] = error

    level = logging.INFO if success else logging.ERROR
    message = f"Telemetry {event_type}: {'processed' if success else 'failed'}"

    logger.log(level, message, extra=log_data)
