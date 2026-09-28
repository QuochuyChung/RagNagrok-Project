"""
Request ID middleware.

Generates or propagates an ``X-Request-ID`` for every incoming request,
stores it in a context variable for structured logging, and echoes it
back in the response header.
"""

from __future__ import annotations

import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_ctx


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that attaches a unique request ID to each request.

    * If the incoming request already has an ``X-Request-ID`` header, that
      value is reused (allows callers to propagate their own trace IDs).
    * Otherwise, a new UUID4 is generated.
    * The ID is stored in ``request_id_ctx`` (a context var) so it is
      available to every log call within the request scope.
    * The ID is added to ``request.state.request_id`` for use in handlers.
    * The ID is echoed back as the ``X-Request-ID`` response header.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Store in context var for structured logging
        token = request_id_ctx.set(request_id)

        # Also expose on request.state for handlers that need it directly
        request.state.request_id = request_id

        try:
            response: Response = await call_next(request)
        finally:
            request_id_ctx.reset(token)

        response.headers["X-Request-ID"] = request_id
        return response
