"""Real-terminal integration tests. Skipped unless explicitly enabled on Windows.

Run on the Windows MT5 host (DEMO account recommended):
    set MT5_RUN_INTEGRATION=1
    pytest -m windows_mt5 -v
"""

import os
import sys

import pytest

from app.core.config import AdapterKind, Settings
from app.market_data.timeframes import Timeframe
from app.services import build_services

pytestmark = [
    pytest.mark.windows_mt5,
    pytest.mark.skipif(sys.platform != "win32", reason="MetaTrader5 package requires Windows"),
    pytest.mark.skipif(os.getenv("MT5_RUN_INTEGRATION") != "1", reason="set MT5_RUN_INTEGRATION=1 to enable"),
]


@pytest.fixture(scope="module")
def services():
    pytest.importorskip("MetaTrader5")
    svc = build_services(Settings(mt5_adapter=AdapterKind.MT5))
    assert svc.connector.connect(), svc.connector.state.last_error_message
    yield svc
    svc.connector.shutdown()


def test_terminal_and_account(services):
    assert services.connector.state.broker_connected
    info = services.connector.run(lambda a: a.account_info())
    assert info is not None and info["currency"]


def test_symbol_discovery(services):
    mapping = services.symbols.mapping()
    assert any(m.broker_symbol for m in mapping.values()), mapping


@pytest.mark.parametrize("tf", list(Timeframe))
def test_candles(services, tf):
    pair = next(p for p, m in services.symbols.mapping().items() if m.broker_symbol)
    series = services.market.get_candles(pair, tf, 100)
    assert len(series.candles) > 0
    errors = [i for i in series.validation.issues if i.severity == "ERROR"]
    assert not errors, errors  # FUTURE_BAR here usually means MT5_SERVER_TIMEZONE is wrong


def test_tick(services):
    pair = next(p for p, m in services.symbols.mapping().items() if m.broker_symbol)
    tick = services.market.get_tick(pair)
    assert tick.ask >= tick.bid > 0
    assert not tick.clock_skew_suspected, "check MT5_SERVER_TIMEZONE"
