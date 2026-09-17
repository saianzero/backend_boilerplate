"""
Per-user, per-endpoint rate limiting (slowapi).

Key = ``user:<id>:endpoint:<METHOD>:<path>`` when ``x-user-data`` is present,
otherwise the client IP. Limit string comes from ``RATE_LIMIT_DEFAULT``.
"""

import json

from fastapi import Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.core.config import RATE_LIMIT_DEFAULT


def get_user_identifier(request: Request) -> str:
    """
    Extract user identifier from x-user-data header for rate limiting.
    Falls back to IP address if no valid header is found.
    Combines user identifier with endpoint path for per-user per-endpoint rate limiting.
    """
    try:
        user_data_raw = request.headers.get("x-user-data")
        if user_data_raw:
            user_data = json.loads(user_data_raw)
            user_id = user_data.get("user_id", "").strip()
            if user_id:
                endpoint = f"{request.method}:{request.url.path}"
                return f"user:{user_id}:endpoint:{endpoint}"

        client_ip = request.client.host if request.client else "unknown"
        endpoint = f"{request.method}:{request.url.path}"
        return f"ip:{client_ip}:endpoint:{endpoint}"

    except (json.JSONDecodeError, AttributeError, KeyError):
        client_ip = request.client.host if request.client else "unknown"
        endpoint = f"{request.method}:{request.url.path}"
        return f"ip:{client_ip}:endpoint:{endpoint}"


# Default limit applies to every route. Override per route:
#   from src.middleware.rate_limiting import limiter
#   @router.post("/upload")
#   @limiter.limit("5/minute")
#   async def upload(request: Request, ...):   # ``request`` param is required by slowapi
limiter = Limiter(
    key_func=get_user_identifier, default_limits=[RATE_LIMIT_DEFAULT], headers_enabled=True
)


def setup_rate_limiting(app):
    """
    Configure rate limiting for the FastAPI application.

    Args:
        app: FastAPI application instance
    """
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
