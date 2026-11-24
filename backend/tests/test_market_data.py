from datetime import timedelta

import pytest

from app.core.errors import BrokerDataError, BrokerUnavailableError, SymbolNotFoundError
from app.market_data.models import DataSource
from app.market_data.service import MarketDataService
from app.market_data.timeframes import Timeframe
from app.mt5_connector.connector import MT5Connector
from app.mt5_connector.mock_adapter import MockAdapter
from app.symbol_manager.manager import SymbolManager
from tests.conftest import FakeMonotonic


@pytest.mark.parametrize("tf", list(Timeframe))
def test_candles_for_each_timeframe(market, tf):
    series = market.get_candles("EURUSD", tf, 200)
    assert series.data_source is DataSource.MOCK
    assert series.timeframe is tf and len(series.candles) == 200
    assert series.validation.is_valid, series.validation.issues
    assert series.validation.has_forming_bar
    times = [c.open_time for c in series.candles]
    assert times == sorted(times) and len(set(times)) == len(times)


def test_closed_only_returns_exact_count_of_closed_bars(market):
    series = market.get_candles("GBPJPY", Timeframe.H4, 50, closed_only=True)
    assert len(series.candles) == 50 and all(c.is_closed for c in series.candles)


def test_mock_server_offset_round_trip(clock, utc_plus_2):
    adapter = MockAdapter(server_tz=utc_plus_2, symbol_suffix="m", clock=clock)
    conn = MT5Connector(adapter, monotonic=FakeMonotonic())
    conn.connect()
    svc = MarketDataService(conn, SymbolManager(conn, ["EURUSD"]), "UTC+2", 30, clock=clock)
    series = svc.get_candles("EURUSD", Timeframe.H1, 10)
    assert series.broker_symbol == "EURUSDm"
    assert series.validation.is_valid, series.validation.issues
    assert series.candles[-1].open_time <= clock.now < series.candles[-1].close_time


def test_missing_history_raises_broker_data_error(market, adapter):
    adapter.rates_override[("EURUSD", Timeframe.H1)] = None
    with pytest.raises(BrokerDataError):
        market.get_candles("EURUSD", Timeframe.H1, 10)


def test_malformed_broker_bars_flagged_invalid(market, adapter):
    adapter.rates_override[("EURUSD", Timeframe.H1)] = [{"time": 1, "open": "x"}]
    series = market.get_candles("EURUSD", Timeframe.H1, 10)
    assert not series.validation.is_valid


def test_unknown_symbol(market):
    with pytest.raises(SymbolNotFoundError):
        market.get_candles("XXXYYY", Timeframe.H1, 10)


def test_fresh_tick(market):
    tick = market.get_tick("USDJPY")
    assert tick.ask > tick.bid > 0
    assert tick.spread_points == pytest.approx(12, abs=0.6)
    assert tick.age_seconds == pytest.approx(1.0)
    assert not tick.is_stale and not tick.clock_skew_suspected
    assert tick.time.tzinfo is not None


def test_stale_tick_flagged(market, adapter):
    adapter.tick_age_seconds = 600
    assert market.get_tick("EURUSD").is_stale


def test_future_tick_flags_clock_skew_and_stale(market, adapter):
    adapter.tick_age_seconds = -3600  # e.g. server timezone misconfigured
    tick = market.get_tick("EURUSD")
    assert tick.clock_skew_suspected and tick.is_stale


@pytest.mark.parametrize(
    "raw",
    [
        {"time": 1, "bid": 1.1, "ask": 1.0},  # crossed
        {"time": 1, "bid": 0.0, "ask": 1.0},
        {"time": 1, "bid": float("nan"), "ask": 1.0},
        {"time": 1, "ask": 1.0},  # missing bid
    ],
)
def test_invalid_tick_rejected(market, adapter, monkeypatch, raw):
    monkeypatch.setattr(adapter, "symbol_info_tick", lambda s: raw)
    with pytest.raises(BrokerDataError):
        market.get_tick("EURUSD")


def test_tick_when_disconnected_fails_closed(market, adapter):
    adapter.broker_connected = False
    with pytest.raises(BrokerUnavailableError):
        market.get_tick("EURUSD")


def test_tick_uses_millisecond_time(market, adapter, monkeypatch, clock):
    epoch_ms = int((clock.now - timedelta(seconds=2.5)).timestamp() * 1000)
    monkeypatch.setattr(
        adapter,
        "symbol_info_tick",
        lambda s: {"time": epoch_ms // 1000, "time_msc": epoch_ms, "bid": 1.1, "ask": 1.1001},
    )
    assert market.get_tick("EURUSD").age_seconds == pytest.approx(2.5)
