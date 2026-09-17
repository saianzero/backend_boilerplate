"""
Optional request/response timing middleware (DEBUG level).

    from src.middleware.logging_middleware import LoggingMiddleware
    app.add_middleware(LoggingMiddleware)
"""

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        logger.debug(f"Request: {request.method} {request.url.path}")

        response = await call_next(request)

        duration = round(time.time() - start_time, 4)
        logger.debug(
            f"Response status: {response.status_code} | Duration: {duration}s for Request: {request.method} {request.url.path}"
        )

        return response
