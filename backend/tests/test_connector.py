import threading
import time

import pytest

from app.core.config import Settings
from app.core.errors import BrokerUnavailableError
from app.mt5_connector.connector import MT5Connector
from app.mt5_connector.mock_adapter import MockAdapter
from app.mt5_connector.mt5_adapter import MT5Adapter
from tests.conftest import FakeMonotonic


def test_connect_success_populates_state(connector):
    s = connector.state
    assert s.initialized and s.broker_connected
    assert s.terminal["name"] == "MOCK MetaTrader 5"
    assert s.version == "500.4000"


def test_connect_failure_does_not_raise():
    adapter = MockAdapter()
    adapter.terminal_available = False
    conn = MT5Connector(adapter, monotonic=FakeMonotonic())
    assert conn.connect() is False
    assert not conn.state.initialized
    assert conn.state.last_error_code == -10003


def test_missing_package_reports_unavailable_without_raising():
    """On Linux/CI the MetaTrader5 package is absent: the connector must degrade gracefully."""
    pytest.importorskip("fastapi")
    try:
        import MetaTrader5  # noqa: F401

        pytest.skip("MetaTrader5 is installed here")
    except ImportError:
        pass
    conn = MT5Connector(MT5Adapter(Settings(_env_file=None)), monotonic=FakeMonotonic())
    assert conn.connect() is False
    assert conn.state.package_available is False
    with pytest.raises(BrokerUnavailableError):
        conn.run(lambda a: a.account_info())


def test_run_fails_closed_when_broker_disconnected(connector, adapter):
    adapter.broker_connected = False
    with pytest.raises(BrokerUnavailableError, match="not connected to the broker"):
        connector.run(lambda a: a.account_info())
    assert connector.state.broker_connected is False


def test_reconnect_is_throttled():
    adapter = MockAdapter()
    adapter.terminal_available = False
    mono = FakeMonotonic()
    conn = MT5Connector(adapter, reconnect_interval_seconds=15, monotonic=mono)
    conn.connect()
    assert adapter.initialize_calls == 1

    adapter.terminal_available = True
    with pytest.raises(BrokerUnavailableError):
        conn.run(lambda a: a.symbols_get())  # within throttle window: no new attempt
    assert adapter.initialize_calls == 1

    mono.t += 16
    assert conn.run(lambda a: a.symbols_get())  # reconnects and succeeds
    assert adapter.initialize_calls == 2


def test_lost_ipc_triggers_reconnect_after_interval(connector, adapter):
    adapter.shutdown()  # simulate terminal closing underneath us
    with pytest.raises(BrokerUnavailableError):
        connector.run(lambda a: a.symbols_get())
    assert connector.state.initialized is False
    connector._monotonic.t += 16
    assert connector.run(lambda a: a.symbols_get())


def test_unexpected_adapter_exception_marks_down(connector):
    def boom(_):
        raise RuntimeError("IPC pipe broken")

    with pytest.raises(BrokerUnavailableError):
        connector.run(boom)
    assert connector.state.initialized is False
    assert "IPC pipe broken" in connector.state.last_error_message


def test_shutdown_is_idempotent(connector):
    connector.shutdown()
    connector.shutdown()
    assert not connector.state.initialized


def test_calls_are_serialised(connector):
    active = 0
    max_active = 0
    guard = threading.Lock()

    def slow(_):
        nonlocal active, max_active
        with guard:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.01)
        with guard:
            active -= 1

    threads = [threading.Thread(target=connector.run, args=(slow,)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert max_active == 1
