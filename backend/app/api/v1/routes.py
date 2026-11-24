"""Read-only v1 endpoints. Phase 1 deliberately exposes NO trading endpoints."""

from __future__ import annotations

import math
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status

from app.api.v1.schemas import (
    AccountResponse,
    ErrorInfo,
    HealthResponse,
    MT5StatusResponse,
    ReadinessResponse,
    SymbolsResponse,
)
from app.core.errors import BrokerDataError
from app.core.security import mask_identifier, require_auth
from app.core.timeutil import utc_now
from app.market_data.models import CandleSeries, DataSource, Tick
from app.market_data.timeframes import Timeframe
from app.services import Services

router = APIRouter(prefix="/api/v1")
protected = APIRouter(prefix="/api/v1", dependencies=[Depends(require_auth)])

SymbolPath = Annotated[str, Path(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9._#+\-]+$")]

_ACCOUNT_TYPES = {0: "DEMO", 1: "CONTEST", 2: "REAL"}


def get_services(request: Request) -> Services:
    return request.app.state.services


ServicesDep = Annotated[Services, Depends(get_services)]


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health(services: ServicesDep) -> HealthResponse:
    """Liveness: the process is up. Does not touch the broker."""
    return HealthResponse(app_env=services.settings.app_env, time=utc_now())


@router.get("/ready", response_model=ReadinessResponse, tags=["health"])
def ready(services: ServicesDep, response: Response) -> ReadinessResponse:
    """Readiness: 200 only when the broker connection is usable, else 503."""
    state = services.connector.health_check()
    ok = state.initialized and state.broker_connected
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(ready=ok, broker_connected=state.broker_connected, detail=state.last_error_message)


@protected.get("/mt5/status", response_model=MT5StatusResponse, tags=["mt5"])
def mt5_status(services: ServicesDep) -> MT5StatusResponse:
    state = services.connector.health_check()
    adapter = services.connector.adapter
    return MT5StatusResponse(
        adapter=adapter.name,
        data_source=DataSource.MOCK if adapter.is_mock else DataSource.BROKER,
        package_available=state.package_available,
        initialized=state.initialized,
        broker_connected=state.broker_connected,
        terminal=state.terminal,
        version=state.version,
        server_timezone=services.settings.mt5_server_timezone,
        last_error=ErrorInfo(code=state.last_error_code, message=state.last_error_message),
        last_check_utc=state.last_check_utc,
        last_connect_attempt_utc=state.last_connect_attempt_utc,
        connect_attempts=state.connect_attempts,
    )


def _num(raw: dict, key: str) -> float:
    value = raw.get(key)
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise BrokerDataError(f"Account field {key!r} missing or non-numeric") from exc
    if not math.isfinite(number):
        raise BrokerDataError(f"Account field {key!r} is not finite")
    return number


@protected.get("/account", response_model=AccountResponse, tags=["mt5"])
def account(services: ServicesDep) -> AccountResponse:
    raw = services.connector.run(lambda a: a.account_info())
    if raw is None:
        code, msg = services.connector.last_error()
        raise BrokerDataError(f"Account information unavailable: [{code}] {msg}")
    adapter = services.connector.adapter
    margin_level = raw.get("margin_level")
    return AccountResponse(
        data_source=DataSource.MOCK if adapter.is_mock else DataSource.BROKER,
        login_masked=mask_identifier(raw.get("login")),
        account_type=_ACCOUNT_TYPES.get(raw.get("trade_mode"), "UNKNOWN"),  # type: ignore[arg-type]
        server=raw.get("server"),
        company=raw.get("company"),
        currency=str(raw.get("currency") or ""),
        leverage=int(raw["leverage"]) if raw.get("leverage") is not None else None,
        balance=_num(raw, "balance"),
        equity=_num(raw, "equity"),
        margin=_num(raw, "margin"),
        margin_free=_num(raw, "margin_free"),
        # MT5 reports 0 margin level when no margin is used; expose that as null.
        margin_level=float(margin_level) if margin_level else None,
        floating_profit=_num(raw, "profit"),
    )


@protected.get("/symbols", response_model=SymbolsResponse, tags=["symbols"])
def symbols(
    services: ServicesDep,
    universe_only: Annotated[
        bool, Query(description="Only return symbols mapped from the configured universe")
    ] = False,
    refresh: Annotated[bool, Query(description="Bypass the discovery cache")] = False,
) -> SymbolsResponse:
    mgr = services.symbols
    mgr.refresh(force=refresh)
    mapping = mgr.mapping()
    specs = mgr.forex_symbols()
    if universe_only:
        mapped = {m.broker_symbol for m in mapping.values() if m.broker_symbol}
        specs = [s for s in specs if s.name in mapped]
    return SymbolsResponse(
        data_source=services.market.data_source,
        count=len(specs),
        rejected_count=mgr.rejected_count,
        universe=[mapping[p] for p in mgr.universe],
        symbols=specs,
    )


@protected.get("/market/{symbol}/candles", response_model=CandleSeries, tags=["market"])
def candles(
    services: ServicesDep,
    symbol: SymbolPath,
    timeframe: Timeframe = Timeframe.H4,
    count: Annotated[int, Query(ge=1)] = 500,
    closed_only: Annotated[bool, Query(description="Exclude the bar that is still forming")] = False,
) -> CandleSeries:
    limit = services.settings.candles_max_count
    if count > limit:
        raise HTTPException(status_code=422, detail=f"count must be <= {limit}")
    return services.market.get_candles(symbol, timeframe, count, closed_only=closed_only)


@protected.get("/market/{symbol}/tick", response_model=Tick, tags=["market"])
def tick(services: ServicesDep, symbol: SymbolPath) -> Tick:
    return services.market.get_tick(symbol)
