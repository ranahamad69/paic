"""Application settings loaded from environment variables (or a local ``.env`` file).

Secrets (MT5 password, API token) are held as ``SecretStr`` so they are never
rendered by ``repr()``/logging by accident. Nothing here enables trading:
Phase 1 is read-only and contains no execution settings at all.
"""

from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_UNIVERSE = (
    "EURUSD,GBPUSD,USDJPY,USDCHF,USDCAD,AUDUSD,NZDUSD,"
    "EURGBP,EURJPY,EURCHF,EURAUD,EURCAD,"
    "GBPJPY,GBPCHF,GBPAUD,GBPCAD,"
    "AUDJPY,AUDNZD,AUDCAD,CADJPY"
)


class AdapterKind(StrEnum):
    """Which broker adapter backs the connector."""

    MT5 = "mt5"  # official MetaTrader5 package (Windows only)
    MOCK = "mock"  # deterministic synthetic data, always labelled MOCK


def _split_csv(value: Any) -> Any:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    """Runtime configuration. See ``.env.example`` for documentation of each variable."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False)

    # --- App -----------------------------------------------------------------
    app_env: str = "development"
    log_level: str = "INFO"

    # --- API security --------------------------------------------------------
    # Bearer token required by every endpoint except /health and /ready.
    # If unset, protected endpoints fail closed with 503.
    api_auth_token: SecretStr | None = None
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    rate_limit_per_minute: int = Field(default=120, ge=1)

    # --- Broker adapter ------------------------------------------------------
    mt5_adapter: AdapterKind = AdapterKind.MT5
    mt5_terminal_path: str | None = None
    mt5_login: int | None = None
    mt5_password: SecretStr | None = None
    mt5_server: str | None = None
    mt5_timeout_ms: int = Field(default=10_000, ge=1_000)
    mt5_portable: bool = False
    mt5_reconnect_interval_seconds: float = Field(default=15.0, ge=1.0)

    # Broker trade-server timezone. MT5 bar/tick timestamps are expressed in
    # server time, NOT UTC. Accepts an IANA name ("Europe/Athens") or a fixed
    # offset ("UTC+2", "UTC-05:00"). Must be verified per broker.
    mt5_server_timezone: str = "UTC"

    # --- Symbols -------------------------------------------------------------
    symbol_universe: Annotated[list[str], NoDecode] = Field(default_factory=lambda: _split_csv(DEFAULT_UNIVERSE))
    # JSON object mapping canonical pair -> broker symbol, e.g. {"EURUSD": "EURUSD.pro"}
    symbol_map_overrides: Annotated[dict[str, str], NoDecode] = Field(default_factory=dict)

    # --- Market data ---------------------------------------------------------
    tick_max_age_seconds: float = Field(default=30.0, gt=0)
    candles_max_count: int = Field(default=5_000, ge=1, le=50_000)

    # Mock adapter only: optional broker-style suffix to exercise symbol mapping.
    mock_symbol_suffix: str = ""

    @field_validator("cors_allowed_origins", "symbol_universe", mode="before")
    @classmethod
    def _csv(cls, value: Any) -> Any:
        return _split_csv(value)

    @field_validator("symbol_universe")
    @classmethod
    def _upper(cls, value: list[str]) -> list[str]:
        return [v.upper() for v in value]

    @field_validator("symbol_map_overrides", mode="before")
    @classmethod
    def _json_map(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return {}
            parsed = json.loads(value)
            if not isinstance(parsed, dict):
                raise ValueError("SYMBOL_MAP_OVERRIDES must be a JSON object")
            return {str(k).upper(): str(v) for k, v in parsed.items()}
        return value

    @field_validator("mt5_server_timezone")
    @classmethod
    def _tz(cls, value: str) -> str:
        from app.core.timeutil import parse_timezone

        parse_timezone(value)  # raises ValueError if invalid
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
