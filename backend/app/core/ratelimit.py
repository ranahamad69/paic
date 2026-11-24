"""Small in-process sliding-window rate limiter (per client IP).

Adequate for a single-process private deployment. For multiple workers or a
public deployment, enforce limits at a reverse proxy or move state to Redis.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

EXEMPT_PATHS = frozenset({"/api/v1/health"})


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, per_minute: int) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._limit = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with self._lock:
            window = self._hits[key]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= self._limit:
                retry = max(1, int(60 - (now - window[0])))
                return JSONResponse(
                    status_code=429,
                    content={"error": {"code": "rate_limited", "message": "Too many requests"}},
                    headers={"Retry-After": str(retry)},
                )
            window.append(now)
        return await call_next(request)
