"""Deterministic mock broker for tests and offline development.

Everything it returns is SYNTHETIC. The API labels it ``data_source: "MOCK"``;
it must never be presented as live account or market data.

Record shapes mirror the fields the real ``MetaTrader5`` package returns, and
timestamps are emitted in *server time* (like MT5) using the configured server
timezone, so UTC normalisation is exercised end to end.
"""

from __future__ import annotations

import math
import zlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any

from app.core.timeutil import utc_now
from app.market_data.timeframes import Timeframe
from app.mt5_connector.adapter import BrokerAdapter, RawRecord

# MT5 enum values used in records.
CALC_MODE_FOREX = 0
CALC_MODE_CFD = 2
TRADE_MODE_FULL = 4
ACCOUNT_TRADE_MODE_DEMO = 0

_BASE_PRICES = {
    "EURUSD": 1.0850,
    "GBPUSD": 1.2650,
    "USDJPY": 151.20,
    "USDCHF": 0.8850,
    "USDCAD": 1.3600,
    "AUDUSD": 0.6550,
    "NZDUSD": 0.6050,
    "EURGBP": 0.8580,
    "EURJPY": 164.00,
    "EURCHF": 0.9600,
    "EURAUD": 1.6550,
    "EURCAD": 1.4750,
    "GBPJPY": 191.30,
    "GBPCHF": 1.1200,
    "GBPAUD": 1.9300,
    "GBPCAD": 1.7200,
    "AUDJPY": 99.00,
    "AUDNZD": 1.0830,
    "AUDCAD": 0.8900,
    "CADJPY": 111.20,
}


def _forex_symbol(name: str, base: str, quote: str, price: float) -> RawRecord:
    jpy = quote == "JPY"
    digits = 3 if jpy else 5
    point = 10.0**-digits
    return {
        "name": name,
        "path": f"Forex\\{base}{quote}",
        "description": f"{base} vs {quote} (MOCK)",
        "currency_base": base,
        "currency_profit": quote,
        "currency_margin": base,
        "trade_calc_mode": CALC_MODE_FOREX,
        "trade_mode": TRADE_MODE_FULL,
        "digits": digits,
        "point": point,
        "trade_tick_size": point,
        # Mock value only; real tick value depends on account currency and broker.
        "trade_tick_value": 1.0,
        "trade_contract_size": 100_000.0,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
        "trade_stops_level": 0,
        "trade_freeze_level": 0,
        "spread": 12 if jpy else 10,
        "visible": False,
        "select": False,
        "_price": price,
    }


class MockAdapter(BrokerAdapter):
    name = "mock"
    is_mock = True

    def __init__(
        self,
        server_tz: tzinfo = UTC,
        symbol_suffix: str = "",
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.server_tz = server_tz
        self.clock = clock
        # Failure-injection knobs for tests.
        self.terminal_available = True
        self.broker_connected = True
        self.tick_age_seconds = 1.0
        self.rates_override: dict[tuple[str, Timeframe], list[RawRecord] | None] = {}
        self.initialize_calls = 0
        self._initialized = False
        self._error: tuple[int, str] = (1, "Success")

        self._symbols: dict[str, RawRecord] = {}
        for pair, price in _BASE_PRICES.items():
            name = f"{pair}{symbol_suffix}"
            self._symbols[name] = _forex_symbol(name, pair[:3], pair[3:], price)
        # Non-Forex instruments to exercise filtering.
        gold = _forex_symbol(f"XAUUSD{symbol_suffix}", "XAU", "USD", 2350.0)
        gold["path"] = "Metals\\XAUUSD"
        index = _forex_symbol(f"US500{symbol_suffix}", "USD", "USD", 5200.0)
        index.update(trade_calc_mode=CALC_MODE_CFD, path="Indices\\US500")
        for rec in (gold, index):
            self._symbols[rec["name"]] = rec

    # --- helpers -------------------------------------------------------------
    def _server_epoch(self, moment_utc: datetime) -> int:
        """UTC instant -> MT5-style epoch of the server wall clock."""
        wall = moment_utc.astimezone(self.server_tz).replace(tzinfo=None)
        return int((wall - datetime(1970, 1, 1)).total_seconds())

    def _require(self) -> bool:
        if not self._initialized:
            self._error = (-10004, "No IPC connection")
            return False
        return True

    def _public(self, rec: RawRecord) -> RawRecord:
        return {k: v for k, v in rec.items() if not k.startswith("_")}

    # --- BrokerAdapter -------------------------------------------------------
    def initialize(self) -> bool:
        self.initialize_calls += 1
        if not self.terminal_available:
            self._initialized = False
            self._error = (-10003, "IPC initialize failed, MetaTrader 5 x64 not found")
            return False
        self._initialized = True
        self._error = (1, "Success")
        return True

    def shutdown(self) -> None:
        self._initialized = False

    def last_error(self) -> tuple[int, str]:
        return self._error

    def version(self) -> tuple[Any, ...] | None:
        return (500, 4000, "01 Jan 2026") if self._require() else None

    def terminal_info(self) -> RawRecord | None:
        if not self._require() or not self.terminal_available:
            return None
        return {
            "name": "MOCK MetaTrader 5",
            "company": "Mock Broker Ltd",
            "path": "C:\\MOCK\\terminal",
            "data_path": "C:\\MOCK\\data",
            "connected": self.broker_connected,
            "trade_allowed": False,
            "build": 4000,
            "ping_last": 25_000,
        }

    def account_info(self) -> RawRecord | None:
        if not self._require() or not self.broker_connected:
            return None
        return {
            "login": 12345678,
            "name": "Mock Trader",
            "server": "MockBroker-Demo",
            "company": "Mock Broker Ltd",
            "currency": "USD",
            "trade_mode": ACCOUNT_TRADE_MODE_DEMO,
            "leverage": 100,
            "balance": 10_000.0,
            "equity": 10_000.0,
            "margin": 0.0,
            "margin_free": 10_000.0,
            "margin_level": 0.0,
            "profit": 0.0,
        }

    def symbols_get(self) -> list[RawRecord] | None:
        if not self._require():
            return None
        return [self._public(r) for r in self._symbols.values()]

    def symbol_info(self, symbol: str) -> RawRecord | None:
        if not self._require():
            return None
        rec = self._symbols.get(symbol)
        return self._public(rec) if rec else None

    def symbol_select(self, symbol: str, enable: bool = True) -> bool:
        if not self._require() or symbol not in self._symbols:
            return False
        self._symbols[symbol]["visible"] = enable
        self._symbols[symbol]["select"] = enable
        return True

    def symbol_info_tick(self, symbol: str) -> RawRecord | None:
        if not self._require() or not self.broker_connected:
            return None
        rec = self._symbols.get(symbol)
        if rec is None:
            return None
        now = self.clock() - timedelta(seconds=self.tick_age_seconds)
        mid = self._price(symbol, now)
        half_spread = rec["spread"] * rec["point"] / 2
        epoch = self._server_epoch(now)
        return {
            "time": epoch,
            "time_msc": epoch * 1000,
            "bid": round(mid - half_spread, rec["digits"]),
            "ask": round(mid + half_spread, rec["digits"]),
            "last": 0.0,
            "volume": 0,
        }

    def copy_rates_from_pos(
        self, symbol: str, timeframe: Timeframe, start_pos: int, count: int
    ) -> list[RawRecord] | None:
        if not self._require():
            return None
        if (symbol, timeframe) in self.rates_override:
            return self.rates_override[(symbol, timeframe)]
        rec = self._symbols.get(symbol)
        if rec is None:
            self._error = (-4301, "Unknown symbol")
            return None

        step = timeframe.duration
        now_server = self.clock().astimezone(self.server_tz).replace(tzinfo=None)
        anchor = datetime(1970, 1, 1)
        # Open time (server wall clock) of the currently forming bar.
        current = anchor + step * ((now_server - anchor) // step)

        bars: list[datetime] = []
        t = current
        while len(bars) < start_pos + count:
            if t.weekday() < 5:  # no bars on server-time Saturday/Sunday
                bars.append(t)
            t -= step
        bars = bars[start_pos:][::-1]

        digits = rec["digits"]
        out: list[RawRecord] = []
        for open_wall in bars:
            open_utc = open_wall.replace(tzinfo=self.server_tz).astimezone(UTC)
            o = self._price(symbol, open_utc)
            c = self._price(symbol, open_utc + step)
            wiggle = abs(o) * 0.0008 * (1 + step / timedelta(days=1))
            out.append(
                {
                    "time": int((open_wall - anchor).total_seconds()),
                    "open": round(o, digits),
                    "high": round(max(o, c) + wiggle, digits),
                    "low": round(min(o, c) - wiggle, digits),
                    "close": round(c, digits),
                    "tick_volume": 1000 + (zlib.crc32(f"{symbol}{open_wall}".encode()) % 500),
                    "spread": rec["spread"],
                    "real_volume": 0,
                }
            )
        return out

    def _price(self, symbol: str, moment: datetime) -> float:
        """Smooth deterministic price path."""
        base = self._symbols[symbol]["_price"]
        seed = zlib.crc32(symbol.encode()) % 1000
        hours = moment.timestamp() / 3600
        return base * (
            1
            + 0.010 * math.sin(hours / 240 + seed)
            + 0.003 * math.sin(hours / 17 + seed / 7)
            + 0.001 * math.sin(hours / 3 + seed / 3)
        )
