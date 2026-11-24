"""Candle, tick and validation-report models. All timestamps are timezone-aware UTC."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, Field

from app.market_data.timeframes import Timeframe


class DataSource(StrEnum):
    BROKER = "BROKER"
    MOCK = "MOCK"  # synthetic: must never be displayed as live data


class Candle(BaseModel):
    open_time: AwareDatetime
    close_time: AwareDatetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    real_volume: int = 0
    spread_points: int | None = None
    is_closed: bool = Field(description="False for the bar that is still forming")


class Severity(StrEnum):
    ERROR = "ERROR"  # data must not be used for signals
    WARNING = "WARNING"  # usable but worth surfacing (e.g. gaps, staleness)


class IssueCode(StrEnum):
    MALFORMED_RECORD = "MALFORMED_RECORD"
    INVALID_PRICE = "INVALID_PRICE"
    INCONSISTENT_OHLC = "INCONSISTENT_OHLC"
    NEGATIVE_VOLUME = "NEGATIVE_VOLUME"
    DUPLICATE = "DUPLICATE"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    FUTURE_BAR = "FUTURE_BAR"
    GAP = "GAP"
    WEEKEND_GAP = "WEEKEND_GAP"
    STALE = "STALE"
    EMPTY = "EMPTY"


class ValidationIssue(BaseModel):
    severity: Severity
    code: IssueCode
    index: int | None = Field(default=None, description="Index into the returned candle list, if applicable")
    time: datetime | None = None
    message: str


class ValidationReport(BaseModel):
    is_valid: bool = Field(description="True when there are no ERROR-severity issues")
    issues: list[ValidationIssue] = Field(default_factory=list)
    received: int
    closed_count: int
    has_forming_bar: bool

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity is Severity.ERROR]


class CandleSeries(BaseModel):
    symbol: str = Field(description="Canonical pair, e.g. EURUSD")
    broker_symbol: str
    timeframe: Timeframe
    data_source: DataSource
    server_timezone: str
    retrieved_at: AwareDatetime
    candles: list[Candle]
    validation: ValidationReport


class Tick(BaseModel):
    symbol: str
    broker_symbol: str
    data_source: DataSource
    time: AwareDatetime
    bid: float
    ask: float
    spread: float
    spread_points: float
    age_seconds: float
    is_stale: bool
    clock_skew_suspected: bool = Field(
        description="Tick time is in the future: MT5_SERVER_TIMEZONE is probably misconfigured"
    )
    retrieved_at: AwareDatetime
