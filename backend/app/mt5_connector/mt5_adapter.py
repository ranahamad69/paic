"""Adapter over the official ``MetaTrader5`` Python package.

The package only works on Windows alongside an installed MT5 desktop terminal,
so it is imported lazily: the application still starts (reporting the broker
as unavailable) on Linux/macOS or when the package is missing.

READ-ONLY: this module must never call order placement/modification/closing
functions. ``tests/test_safety.py`` enforces this.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import Settings
from app.core.errors import BrokerUnavailableError
from app.core.security import mask_identifier
from app.market_data.timeframes import Timeframe
from app.mt5_connector.adapter import BrokerAdapter, RawRecord

logger = logging.getLogger(__name__)

_TIMEFRAME_ATTR = {Timeframe.H1: "TIMEFRAME_H1", Timeframe.H4: "TIMEFRAME_H4", Timeframe.D1: "TIMEFRAME_D1"}


def _record(obj: Any) -> RawRecord | None:
    """MT5 returns namedtuples; convert to a plain dict."""
    if obj is None:
        return None
    if hasattr(obj, "_asdict"):
        return dict(obj._asdict())
    return dict(obj)


class MT5Adapter(BrokerAdapter):
    name = "mt5"
    is_mock = False

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._mt5: Any = None

    def _module(self) -> Any:
        if self._mt5 is None:
            try:
                import MetaTrader5  # type: ignore[import-not-found]  # noqa: N813
            except ImportError as exc:
                raise BrokerUnavailableError(
                    "MetaTrader5 package is not installed (requires Windows with the MT5 terminal)"
                ) from exc
            self._mt5 = MetaTrader5
        return self._mt5

    def initialize(self) -> bool:
        mt5 = self._module()
        s = self._settings
        kwargs: dict[str, Any] = {"timeout": s.mt5_timeout_ms, "portable": s.mt5_portable}
        if s.mt5_login is not None:
            kwargs["login"] = s.mt5_login
        if s.mt5_password is not None:
            kwargs["password"] = s.mt5_password.get_secret_value()
        if s.mt5_server:
            kwargs["server"] = s.mt5_server
        args = (s.mt5_terminal_path,) if s.mt5_terminal_path else ()
        logger.info(
            "Initialising MT5 terminal (login=%s, server=%s, path_configured=%s)",
            mask_identifier(s.mt5_login) or "<terminal default>",
            s.mt5_server or "<terminal default>",
            bool(s.mt5_terminal_path),
        )
        return bool(mt5.initialize(*args, **kwargs))

    def shutdown(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()

    def last_error(self) -> tuple[int, str]:
        if self._mt5 is None:
            return (-1, "MetaTrader5 package not loaded")
        code, message = self._mt5.last_error()
        return int(code), str(message)

    def version(self) -> tuple[Any, ...] | None:
        result = self._module().version()
        return tuple(result) if result is not None else None

    def terminal_info(self) -> RawRecord | None:
        return _record(self._module().terminal_info())

    def account_info(self) -> RawRecord | None:
        return _record(self._module().account_info())

    def symbols_get(self) -> list[RawRecord] | None:
        result = self._module().symbols_get()
        if result is None:
            return None
        return [r for r in (_record(s) for s in result) if r is not None]

    def symbol_info(self, symbol: str) -> RawRecord | None:
        return _record(self._module().symbol_info(symbol))

    def symbol_select(self, symbol: str, enable: bool = True) -> bool:
        return bool(self._module().symbol_select(symbol, enable))

    def symbol_info_tick(self, symbol: str) -> RawRecord | None:
        return _record(self._module().symbol_info_tick(symbol))

    def copy_rates_from_pos(
        self, symbol: str, timeframe: Timeframe, start_pos: int, count: int
    ) -> list[RawRecord] | None:
        mt5 = self._module()
        rates = mt5.copy_rates_from_pos(symbol, getattr(mt5, _TIMEFRAME_ATTR[timeframe]), start_pos, count)
        if rates is None:
            return None
        # numpy structured array -> list of dicts with native Python scalars
        names = rates.dtype.names or ()
        return [{n: row[n].item() for n in names} for row in rates]
