"""Terminal initialisation, status, account/terminal metadata and shutdown."""

from __future__ import annotations

from app.core.config import AdapterKind, Settings
from app.core.timeutil import parse_timezone
from app.mt5_connector.adapter import BrokerAdapter
from app.mt5_connector.connector import MT5Connector


def build_adapter(settings: Settings) -> BrokerAdapter:
    if settings.mt5_adapter is AdapterKind.MOCK:
        from app.mt5_connector.mock_adapter import MockAdapter

        return MockAdapter(
            server_tz=parse_timezone(settings.mt5_server_timezone),
            symbol_suffix=settings.mock_symbol_suffix,
        )
    from app.mt5_connector.mt5_adapter import MT5Adapter

    return MT5Adapter(settings)


__all__ = ["BrokerAdapter", "MT5Connector", "build_adapter"]
