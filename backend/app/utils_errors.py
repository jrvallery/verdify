"""
Standardized error handling and envelope formatting for Project Verdify API.

Provides consistent error response format with request traceability and proper HTTP status codes.
"""

import traceback
from datetime import datetime, timezone

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.utils_request_id import get_request_id


class ErrorDetail(BaseModel):
    """Individual error detail for field-specific validation errors."""

    field: str | None = Field(None, description="Field name that caused the error")
    message: str = Field(..., description="Human-readable error message")
    code: str | None = Field(None, description="Machine-readable error code")


class ErrorResponse(BaseModel):
    """
    Standardized error response envelope matching OpenAPI specification.

    Used for all 4xx and 5xx responses to ensure consistent error handling
    across the entire API surface.
    """

    error_code: str = Field(
        ..., description="Standardized error code (e.g., E400_BAD_REQUEST)"
    )
    message: str = Field(..., description="Human-readable error message")
    details: str | list[ErrorDetail] | None = Field(
        None, description="Optional detailed information or field-specific errors"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when error occurred",
    )
    request_id: str = Field(
        ..., description="Unique request identifier for correlation"
    )


# Standard error code mappings following the OpenAPI specification
ERROR_CODE_MAP = {
    400: "E400_BAD_REQUEST",
    401: "E401_UNAUTHORIZED",
    403: "E403_FORBIDDEN",
    404: "E404_NOT_FOUND",
    409: "E409_CONFLICT",
    412: "E412_PRECONDITION_FAILED",
    422: "E422_UNPROCESSABLE_ENTITY",
    429: "E429_TOO_MANY_REQUESTS",
    500: "E500_INTERNAL_SERVER_ERROR",
    503: "E503_SERVICE_UNAVAILABLE",
}


def create_error_response(
    request: Request,
    status_code: int,
    message: str,
    details: str | list[ErrorDetail] | None = None,
    error_code: str | None = None,
) -> JSONResponse:
    """
    Create a standardized error response with proper envelope format.

    Args:
        request: FastAPI request object (for request ID extraction)
        status_code: HTTP status code
        message: Human-readable error message
        details: Optional detailed error information
        error_code: Optional custom error code (auto-generated if not provided)

    Returns:
        JSONResponse with standardized error envelope
    """
    if not error_code:
        error_code = ERROR_CODE_MAP.get(status_code, f"E{status_code}_ERROR")

    error_response = ErrorResponse(
        error_code=error_code,
        message=message,
        details=details,
        request_id=get_request_id(request),
    )

    return JSONResponse(
        status_code=status_code,
        content=error_response.model_dump(mode="json"),
        headers={"X-Request-Id": error_response.request_id},
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Global handler for HTTPException to ensure standardized error envelope.

    Converts FastAPI HTTPExceptions into our standardized error format
    while preserving the original status code and message.
    """
    return create_error_response(
        request=request,
        status_code=exc.status_code,
        message=exc.detail,
        details=getattr(exc, "details", None),
    )


async def validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Handler for Pydantic validation errors (422 Unprocessable Entity).

    Converts validation errors into structured field-specific error details.
    """
    details = []

    # Handle Pydantic ValidationError
    if hasattr(exc, "errors"):
        for error in exc.errors():
            field = ".".join(str(loc) for loc in error.get("loc", []))
            details.append(
                ErrorDetail(
                    field=field,
                    message=error.get("msg", "Validation error"),
                    code=error.get("type", "validation_error"),
                )
            )

    return create_error_response(
        request=request,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        message="Validation error",
        details=details,
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Fallback handler for unexpected exceptions.

    Logs the full traceback and returns a generic 500 error to avoid
    exposing internal implementation details.
    """
    # Log the full exception for debugging (in production, this should go to proper logging)
    print(f"Unhandled exception: {exc}")
    print(traceback.format_exc())

    return create_error_response(
        request=request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message="Internal server error",
        details="An unexpected error occurred. Please try again later.",
    )
