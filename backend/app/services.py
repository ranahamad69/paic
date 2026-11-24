"""Explicit service container (no hidden globals). Built once per app instance."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.market_data.service import MarketDataService
from app.mt5_connector import BrokerAdapter, MT5Connector, build_adapter
from app.symbol_manager import SymbolManager


@dataclass
class Services:
    settings: Settings
    connector: MT5Connector
    symbols: SymbolManager
    market: MarketDataService


def build_services(settings: Settings, adapter: BrokerAdapter | None = None) -> Services:
    connector = MT5Connector(
        adapter or build_adapter(settings),
        reconnect_interval_seconds=settings.mt5_reconnect_interval_seconds,
    )
    symbols = SymbolManager(connector, settings.symbol_universe, settings.symbol_map_overrides)
    market = MarketDataService(connector, symbols, settings.mt5_server_timezone, settings.tick_max_age_seconds)
    return Services(settings=settings, connector=connector, symbols=symbols, market=market)
