"""FastAPI application factory.

Start with:  uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
The app starts even when MT5 is unavailable; status/readiness report the problem.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.routes import protected, router
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.ratelimit import RateLimitMiddleware
from app.mt5_connector import BrokerAdapter
from app.services import build_services

logger = logging.getLogger("app")


def _error(status_code: int, code: str, message: str, **extra: object) -> JSONResponse:
    body: dict[str, object] = {"code": code, "message": message, **extra}
    return JSONResponse(status_code=status_code, content={"error": body})


def create_app(settings: Settings | None = None, adapter: BrokerAdapter | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    services = build_services(settings, adapter)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Never let a broker problem stop the API from starting.
        connected = await run_in_threadpool(services.connector.connect)
        if not connected:
            logger.warning("Starting without broker connection: %s", services.connector.state.last_error_message)
        try:
            yield
        finally:
            await run_in_threadpool(services.connector.shutdown)

    app = FastAPI(
        title="PAIC Forex Swing Platform API",
        version="0.1.0",
        description="Phase 1: read-only MT5 connectivity and market data. No trading endpoints.",
        lifespan=lifespan,
    )
    app.state.services = services

    if settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allowed_origins,
            allow_methods=["GET"],
            allow_headers=["Authorization", "Content-Type"],
            allow_credentials=False,
        )
    app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute)

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.warning("%s: %s", exc.code, exc.message)
        return _error(exc.status_code, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        resp = _error(exc.status_code, "http_error", str(exc.detail))
        if exc.headers:
            resp.headers.update(exc.headers)
        return resp

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [{"loc": list(e.get("loc", ())), "msg": e.get("msg")} for e in exc.errors()]
        return _error(422, "validation_error", "Request validation failed", details=details)

    app.include_router(router)
    app.include_router(protected)
    return app
