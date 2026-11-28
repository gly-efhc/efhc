"""HTTP timing middleware backed by safe aggregate metrics."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from app.core.runtime_observability import runtime_observability
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    """Record status and latency without request content."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = int(response.status_code)
            return response
        finally:
            duration_ms = (time.perf_counter() - started) * 1000.0
            runtime_observability.record(
                method=request.method,
                route=request.url.path,
                status_code=status_code,
                duration_ms=duration_ms,
            )
            if "response" in locals():
                response.headers.setdefault(
                    "Server-Timing",
                    f"app;dur={duration_ms:.2f}",
                )
                response.headers.setdefault(
                    "X-Response-Time-Ms",
                    f"{duration_ms:.2f}",
                )
