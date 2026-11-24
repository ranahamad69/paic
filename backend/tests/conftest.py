"""Shared fixtures. All tests run against the MockAdapter; no MT5 or broker account needed."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.core.config import AdapterKind, Settings
from app.core.timeutil import parse_timezone
from app.main import create_app
from app.market_data.service import MarketDataService
from app.mt5_connector.connector import MT5Connector
from app.mt5_connector.mock_adapter import MockAdapter
from app.symbol_manager.manager import SymbolManager

TOKEN = "test-token-not-a-secret"
# Wednesday mid-session, so the forming bar and weekend gaps are predictable.
FIXED_NOW = datetime(2026, 11, 25, 10, 30, tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime = FIXED_NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class FakeMonotonic:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def make_settings(**overrides) -> Settings:
    base = dict(
        _env_file=None,
        mt5_adapter=AdapterKind.MOCK,
        api_auth_token=TOKEN,
        rate_limit_per_minute=10_000,
        mt5_server_timezone="UTC",
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def adapter(clock: FakeClock) -> MockAdapter:
    return MockAdapter(server_tz=UTC, clock=clock)


@pytest.fixture
def connector(adapter: MockAdapter) -> MT5Connector:
    conn = MT5Connector(adapter, reconnect_interval_seconds=15, monotonic=FakeMonotonic())
    assert conn.connect()
    return conn


@pytest.fixture
def symbols(connector: MT5Connector) -> SymbolManager:
    return SymbolManager(connector, make_settings().symbol_universe)


@pytest.fixture
def market(connector: MT5Connector, symbols: SymbolManager, clock: FakeClock) -> MarketDataService:
    return MarketDataService(connector, symbols, "UTC", tick_max_age_seconds=30, clock=clock)


def build_client(settings: Settings, adapter: MockAdapter, clock: FakeClock) -> TestClient:
    app = create_app(settings, adapter=adapter)
    app.state.services.market._clock = clock  # deterministic "now" for candle/tick checks
    return TestClient(app)


@pytest.fixture
def client(adapter: MockAdapter, clock: FakeClock):
    with build_client(make_settings(), adapter, clock) as c:
        yield c


@pytest.fixture
def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def utc_plus_2():
    return parse_timezone("UTC+2")
