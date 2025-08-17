"""
Rate limiting implementation for telemetry endpoints.

Provides token bucket-based rate limiting with per-device limits and Redis-backed
storage for stateless operation across multiple replicas.

For MVP, implements in-memory sliding window rate limiting with future Redis support.
"""

import asyncio
import time
from collections import deque

from pydantic import BaseModel


class RateLimit(BaseModel):
    """Rate limit configuration and state."""

    limit: int  # Requests per window
    window_seconds: int  # Time window in seconds
    remaining: int  # Requests remaining in current window
    reset_time: int  # Unix timestamp when window resets


class RateLimitState:
    """Rate limit state for a specific key."""

    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window_seconds = window_seconds
        self.requests: deque = deque()  # Store request timestamps
        self.lock = asyncio.Lock()

    async def check_and_consume(self) -> RateLimit:
        """Check rate limit and consume one request if allowed."""
        async with self.lock:
            now = time.time()

            # Remove expired requests from the window
            cutoff = now - self.window_seconds
            while self.requests and self.requests[0] <= cutoff:
                self.requests.popleft()

            remaining = self.limit - len(self.requests)
            reset_time = int(now + self.window_seconds)

            if remaining > 0:
                # Allow the request and record it
                self.requests.append(now)
                remaining -= 1

            return RateLimit(
                limit=self.limit,
                window_seconds=self.window_seconds,
                remaining=remaining,
                reset_time=reset_time,
            )


class RateLimiter:
    """
    In-memory rate limiter with sliding window implementation.

    For production use, this should be replaced with Redis-backed implementation
    to support multiple replicas and persistent state.
    """

    def __init__(self):
        self.limits: dict[str, RateLimitState] = {}
        self.default_config = {
            "telemetry": {
                "limit": 100,
                "window_seconds": 60,
            },  # 100 requests per minute
            "batch": {
                "limit": 20,
                "window_seconds": 60,
            },  # 20 batch requests per minute
        }

    def _get_key(self, controller_id: str, endpoint_type: str) -> str:
        """Generate rate limit key for controller and endpoint type."""
        return f"rate_limit:{controller_id}:{endpoint_type}"

    async def check_rate_limit(
        self, controller_id: str, endpoint_type: str = "telemetry"
    ) -> tuple[bool, RateLimit]:
        """
        Check if request is within rate limit.

        Args:
            controller_id: Controller UUID as string
            endpoint_type: Type of endpoint ("telemetry" or "batch")

        Returns:
            Tuple of (is_allowed: bool, rate_limit_info: RateLimit)
        """
        config = self.default_config.get(
            endpoint_type, self.default_config["telemetry"]
        )
        key = self._get_key(controller_id, endpoint_type)

        # Get or create rate limit state for this key
        if key not in self.limits:
            self.limits[key] = RateLimitState(
                limit=config["limit"], window_seconds=config["window_seconds"]
            )

        rate_limit = await self.limits[key].check_and_consume()
        is_allowed = rate_limit.remaining >= 0

        return is_allowed, rate_limit

    def configure_limits(self, endpoint_type: str, limit: int, window_seconds: int):
        """Configure rate limits for an endpoint type."""
        self.default_config[endpoint_type] = {
            "limit": limit,
            "window_seconds": window_seconds,
        }

    async def reset_limits(self, controller_id: str):
        """Reset all rate limits for a controller (admin function)."""
        keys_to_remove = [
            key
            for key in self.limits.keys()
            if key.startswith(f"rate_limit:{controller_id}:")
        ]
        for key in keys_to_remove:
            del self.limits[key]


# Global rate limiter instance
rate_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    """Dependency to get the global rate limiter instance."""
    return rate_limiter


# Rate limit headers helper
def create_rate_limit_headers(rate_limit: RateLimit) -> dict[str, str]:
    """Create standard rate limit headers for HTTP response."""
    return {
        "X-RateLimit-Limit": str(rate_limit.limit),
        "X-RateLimit-Remaining": str(max(0, rate_limit.remaining)),
        "X-RateLimit-Reset": str(rate_limit.reset_time),
    }


def create_retry_after_header(rate_limit: RateLimit) -> dict[str, str]:
    """Create Retry-After header for 429 responses."""
    retry_after = max(1, rate_limit.reset_time - int(time.time()))
    return {"Retry-After": str(retry_after)}
