"""
Logging middleware for Project Verdify API.

Provides structured logging with request correlation and user/device context.
"""

import time
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.utils.log import (
    clear_context,
    get_structured_logger,
    log_request_end,
    log_request_start,
)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that provides structured logging for all requests.

    Features:
    - Logs request start and completion with timing
    - Correlates logs with request ID
    - Includes user/device context when available
    - Provides structured JSON logging format
    - Handles errors and exceptions in logging context
    """

    def __init__(self, app, skip_paths: list | None = None):
        """
        Initialize logging middleware.

        Args:
            app: FastAPI application instance
            skip_paths: List of paths to skip logging (e.g., health checks)
        """
        super().__init__(app)
        self.skip_paths = skip_paths or ["/health", "/docs", "/redoc", "/openapi.json"]
        self.logger = get_structured_logger("verdify.middleware")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip logging for certain paths to reduce noise
        if any(request.url.path.startswith(path) for path in self.skip_paths):
            return await call_next(request)

        start_time = time.time()

        try:
            # Try to extract user/device context from request state
            # This will be set by authentication dependencies
            user = getattr(request.state, "current_user", None)
            device = getattr(request.state, "current_device", None)

            # Log request start with context
            log_request_start(request, user=user, device=device)

            # Process request
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log successful completion
            log_request_end(request, response.status_code, duration_ms)

            return response

        except Exception as e:
            # Calculate duration for failed requests
            duration_ms = (time.time() - start_time) * 1000

            # Log the error
            self.logger.error(
                "Request failed with exception",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                    "exception_type": type(e).__name__,
                    "exception_message": str(e),
                },
                exc_info=e,
            )

            # Re-raise the exception to be handled by other middleware/handlers
            raise

        finally:
            # Always clear context after request
            clear_context()


def setup_logging_middleware(app) -> None:
    """
    Setup logging middleware on the FastAPI app.

    Args:
        app: FastAPI application instance
    """
    # Add logging middleware (should be after RequestIdMiddleware but before CORS)
    app.add_middleware(LoggingMiddleware)
