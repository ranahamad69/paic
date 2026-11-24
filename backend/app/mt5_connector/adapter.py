"""Read-only broker adapter interface.

Adapters return *raw, untrusted* broker records as plain dicts/lists. Validation
and normalisation happen in ``symbol_manager`` and ``market_data``.

This interface deliberately has NO order placement, modification or closing
methods. Phase 1 is read-only; execution belongs to a separately authorised
``execution_engine`` in a later phase.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.market_data.timeframes import Timeframe

RawRecord = dict[str, Any]


class BrokerAdapter(ABC):
    """Minimal read-only surface over an MT5-like terminal.

    Methods may raise ``BrokerUnavailableError`` (cannot reach terminal/package)
    and return ``None`` where MT5 itself returns ``None`` (see ``last_error``).
    Implementations are NOT required to be thread-safe; the connector serialises calls.
    """

    #: Short identifier reported by status endpoints ("mt5", "mock").
    name: str = "abstract"
    #: True when data is synthetic. Surfaces as ``data_source: MOCK`` in the API.
    is_mock: bool = False

    @abstractmethod
    def initialize(self) -> bool:
        """Start/attach to the terminal (and log in if credentials are configured)."""

    @abstractmethod
    def shutdown(self) -> None:
        """Release the terminal connection. Must be safe to call repeatedly."""

    @abstractmethod
    def last_error(self) -> tuple[int, str]:
        """Most recent broker error as ``(code, message)``."""

    @abstractmethod
    def version(self) -> tuple[Any, ...] | None: ...

    @abstractmethod
    def terminal_info(self) -> RawRecord | None: ...

    @abstractmethod
    def account_info(self) -> RawRecord | None: ...

    @abstractmethod
    def symbols_get(self) -> list[RawRecord] | None: ...

    @abstractmethod
    def symbol_info(self, symbol: str) -> RawRecord | None: ...

    @abstractmethod
    def symbol_select(self, symbol: str, enable: bool = True) -> bool:
        """Show/hide a symbol in Market Watch (required before data requests). Not a trade action."""

    @abstractmethod
    def symbol_info_tick(self, symbol: str) -> RawRecord | None: ...

    @abstractmethod
    def copy_rates_from_pos(
        self, symbol: str, timeframe: Timeframe, start_pos: int, count: int
    ) -> list[RawRecord] | None:
        """Bars ordered oldest -> newest; ``start_pos=0`` includes the forming bar."""
