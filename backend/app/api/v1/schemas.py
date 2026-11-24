"""Response models for the read-only v1 API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.market_data.models import DataSource
from app.symbol_manager.models import SymbolMapping, SymbolSpec


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    app_env: str
    time: datetime


class ReadinessResponse(BaseModel):
    ready: bool
    broker_connected: bool
    detail: str | None = None


class ErrorInfo(BaseModel):
    code: int | None = None
    message: str | None = None


class MT5StatusResponse(BaseModel):
    adapter: str
    data_source: DataSource
    package_available: bool
    initialized: bool
    broker_connected: bool
    terminal: dict[str, Any] = Field(default_factory=dict)
    version: str | None = None
    server_timezone: str
    last_error: ErrorInfo
    last_check_utc: datetime | None
    last_connect_attempt_utc: datetime | None
    connect_attempts: int
    read_only: Literal[True] = Field(default=True, description="Phase 1: no order functionality exists")


class AccountResponse(BaseModel):
    """Minimal, masked account metadata. Never includes full login or holder name."""

    data_source: DataSource
    login_masked: str
    account_type: Literal["DEMO", "CONTEST", "REAL", "UNKNOWN"]
    server: str | None
    company: str | None
    currency: str
    leverage: int | None
    balance: float
    equity: float
    margin: float
    margin_free: float
    margin_level: float | None
    floating_profit: float


class SymbolsResponse(BaseModel):
    data_source: DataSource
    count: int
    rejected_count: int = Field(description="Forex records rejected as malformed")
    universe: list[SymbolMapping]
    symbols: list[SymbolSpec]
