"""Read-only retrieval of candles and latest ticks for a resolved Forex symbol."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import datetime

from app.core.errors import BrokerDataError
from app.core.timeutil import parse_timezone, server_epoch_to_utc, utc_now
from app.market_data.models import Candle, CandleSeries, DataSource, Tick
from app.market_data.timeframes import Timeframe
from app.market_data.validation import FUTURE_TOLERANCE, parse_bars, validate_candles
from app.mt5_connector.connector import MT5Connector
from app.symbol_manager.manager import SymbolManager


class MarketDataService:
    def __init__(
        self,
        connector: MT5Connector,
        symbols: SymbolManager,
        server_timezone: str,
        tick_max_age_seconds: float,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._connector = connector
        self._symbols = symbols
        self._server_tz_name = server_timezone
        self._server_tz = parse_timezone(server_timezone)
        self._tick_max_age = tick_max_age_seconds
        self._clock = clock

    @property
    def data_source(self) -> DataSource:
        return DataSource.MOCK if self._connector.adapter.is_mock else DataSource.BROKER

    def get_candles(self, symbol: str, timeframe: Timeframe, count: int, closed_only: bool = False) -> CandleSeries:
        spec = self._symbols.resolve(symbol)
        self._symbols.ensure_selected(spec)
        # +1 so that `count` closed bars remain when the forming bar is dropped.
        fetch = count + 1 if closed_only else count
        raw = self._connector.run(lambda a: a.copy_rates_from_pos(spec.name, timeframe, 0, fetch))
        if raw is None:
            code, msg = self._connector.last_error()
            raise BrokerDataError(f"No {timeframe} history for {spec.name}: [{code}] {msg}")
        now = self._clock()
        candles, parse_issues = parse_bars(raw, timeframe, self._server_tz, now)
        report = validate_candles(candles, timeframe, self._server_tz, now, parse_issues)
        out: list[Candle] = candles
        if closed_only:
            out = [c for c in candles if c.is_closed][-count:]
        return CandleSeries(
            symbol=spec.canonical,
            broker_symbol=spec.name,
            timeframe=timeframe,
            data_source=self.data_source,
            server_timezone=self._server_tz_name,
            retrieved_at=now,
            candles=out,
            validation=report,
        )

    def get_tick(self, symbol: str) -> Tick:
        spec = self._symbols.resolve(symbol)
        self._symbols.ensure_selected(spec)
        raw = self._connector.run(lambda a: a.symbol_info_tick(spec.name))
        if raw is None:
            code, msg = self._connector.last_error()
            raise BrokerDataError(f"No tick for {spec.name}: [{code}] {msg}")
        try:
            bid, ask = float(raw["bid"]), float(raw["ask"])
            msc = raw.get("time_msc")
            epoch = float(msc) / 1000 if msc else float(raw["time"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BrokerDataError(f"Malformed tick for {spec.name}: {exc}") from exc
        if not (math.isfinite(bid) and math.isfinite(ask)) or bid <= 0 or ask <= 0 or ask < bid:
            raise BrokerDataError(f"Invalid quote for {spec.name}: bid={bid} ask={ask}")

        now = self._clock()
        tick_time = server_epoch_to_utc(epoch, self._server_tz)
        age = (now - tick_time).total_seconds()
        skew = tick_time > now + FUTURE_TOLERANCE
        spread = ask - bid
        return Tick(
            symbol=spec.canonical,
            broker_symbol=spec.name,
            data_source=self.data_source,
            time=tick_time,
            bid=bid,
            ask=ask,
            spread=round(spread, spec.digits + 1),
            spread_points=round(spread / spec.point, 1),
            age_seconds=round(age, 3),
            # Fail closed: a future-dated tick is treated as stale as well.
            is_stale=skew or age > self._tick_max_age,
            clock_skew_suspected=skew,
            retrieved_at=now,
        )
