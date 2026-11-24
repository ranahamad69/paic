"""Validated symbol specification and mapping models."""

from __future__ import annotations

from enum import IntEnum, StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ISO-4217 fiat currencies commonly quoted as Forex pairs. Metals (XAU/XAG),
# crypto and index "currencies" are intentionally excluded.
FIAT_CURRENCIES = frozenset(
    "USD EUR GBP JPY CHF CAD AUD NZD SEK NOK DKK PLN HUF CZK TRY ZAR MXN SGD HKD CNH ILS THB RON".split()
)


class CalcMode(IntEnum):
    """Subset of MT5 ``SYMBOL_CALC_MODE_*`` values."""

    FOREX = 0
    FUTURES = 1
    CFD = 2
    CFDINDEX = 3
    CFDLEVERAGE = 4
    FOREX_NO_LEVERAGE = 5


FOREX_CALC_MODES = frozenset({CalcMode.FOREX, CalcMode.FOREX_NO_LEVERAGE})


class TradeMode(IntEnum):
    """MT5 ``SYMBOL_TRADE_MODE_*``. Informational only in Phase 1."""

    DISABLED = 0
    LONGONLY = 1
    SHORTONLY = 2
    CLOSEONLY = 3
    FULL = 4


class SymbolSpec(BaseModel):
    """Broker contract specification needed later for risk calculations.

    Values come from the broker and differ between brokers; never assume
    pip value, contract size or volume rules are universal.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Broker symbol name, e.g. 'EURUSD.r'")
    canonical: str = Field(description="Base+quote, e.g. 'EURUSD'")
    description: str = ""
    path: str = ""
    currency_base: str
    currency_profit: str
    currency_margin: str
    calc_mode: int
    trade_mode: int
    digits: int = Field(ge=0, le=10)
    point: float = Field(gt=0)
    tick_size: float = Field(gt=0)
    tick_value: float | None = Field(
        default=None, description="Account-currency value of one tick; None if unavailable"
    )
    contract_size: float = Field(gt=0)
    volume_min: float = Field(gt=0)
    volume_max: float = Field(gt=0)
    volume_step: float = Field(gt=0)
    stops_level_points: int = Field(ge=0)
    freeze_level_points: int = Field(ge=0)
    spread_points: int | None = Field(default=None, ge=0)
    visible: bool = False

    @model_validator(mode="after")
    def _check_volumes(self) -> SymbolSpec:
        if self.volume_max < self.volume_min:
            raise ValueError("volume_max < volume_min")
        return self


class MappingStatus(StrEnum):
    MAPPED = "MAPPED"
    MISSING = "MISSING"
    AMBIGUOUS = "AMBIGUOUS"


class SymbolMapping(BaseModel):
    canonical: str
    broker_symbol: str | None
    status: MappingStatus
    source: str = Field(description="'override', 'exact', 'unique_candidate' or 'none'")
    candidates: list[str] = Field(default_factory=list)
