import pytest

from app.mt5_connector.mock_adapter import MockAdapter, _forex_symbol
from tests.conftest import FakeClock, build_client, make_settings

PROTECTED = [
    "/api/v1/mt5/status",
    "/api/v1/account",
    "/api/v1/symbols",
    "/api/v1/market/EURUSD/candles",
    "/api/v1/market/EURUSD/tick",
]


def test_health_is_public(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_ready_when_connected(client):
    assert client.get("/api/v1/ready").json()["ready"] is True


@pytest.mark.parametrize("path", PROTECTED)
def test_protected_endpoints_require_token(client, path):
    r = client.get(path)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "http_error"
    assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401


@pytest.mark.parametrize("path", PROTECTED)
def test_auth_fails_closed_when_token_unset(adapter, clock, path):
    with build_client(make_settings(api_auth_token=None), adapter, clock) as c:
        r = c.get(path, headers={"Authorization": "Bearer anything"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "auth_not_configured"


def test_status_labels_mock(client, auth):
    body = client.get("/api/v1/mt5/status", headers=auth).json()
    assert body["adapter"] == "mock" and body["data_source"] == "MOCK"
    assert body["broker_connected"] is True and body["read_only"] is True


def test_account_is_masked(client, auth):
    r = client.get("/api/v1/account", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["login_masked"] == "*****678"
    assert body["account_type"] == "DEMO" and body["data_source"] == "MOCK"
    assert body["margin_level"] is None
    assert "12345678" not in r.text and "Mock Trader" not in r.text  # no full login or holder name


def test_symbols_endpoint(client, auth):
    body = client.get("/api/v1/symbols", headers=auth).json()
    assert body["count"] == 20 and len(body["universe"]) == 20
    assert all(m["status"] == "MAPPED" for m in body["universe"])
    assert {"digits", "point", "contract_size", "volume_step", "stops_level_points"} <= set(body["symbols"][0])


def test_candles_endpoint(client, auth):
    r = client.get("/api/v1/market/EURUSD/candles?timeframe=D1&count=30", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["timeframe"] == "D1" and len(body["candles"]) == 30
    assert body["validation"]["is_valid"] is True
    assert body["candles"][0]["open_time"].endswith("Z")


def test_candles_default_h4_500(client, auth):
    body = client.get("/api/v1/market/EURUSD/candles", headers=auth).json()
    assert body["timeframe"] == "H4" and len(body["candles"]) == 500


@pytest.mark.parametrize("query", ["timeframe=M5", "count=0", "count=999999", "count=abc"])
def test_candles_bad_params(client, auth, query):
    r = client.get(f"/api/v1/market/EURUSD/candles?{query}", headers=auth)
    assert r.status_code == 422
    assert r.json()["error"]["code"] in {"validation_error", "http_error"}


def test_tick_endpoint(client, auth):
    body = client.get("/api/v1/market/EURUSD/tick", headers=auth).json()
    assert body["ask"] > body["bid"] and body["is_stale"] is False and body["data_source"] == "MOCK"


def test_unknown_symbol_404(client, auth):
    r = client.get("/api/v1/market/ABCXYZ/tick", headers=auth)
    assert r.status_code == 404 and r.json()["error"]["code"] == "symbol_not_found"


def test_ambiguous_symbol_409(auth):
    clock = FakeClock()
    adapter = MockAdapter(symbol_suffix=".r", clock=clock)
    adapter._symbols["EURUSD.pro"] = _forex_symbol("EURUSD.pro", "EUR", "USD", 1.08)
    with build_client(make_settings(), adapter, clock) as c:
        r = c.get("/api/v1/market/EURUSD/tick", headers=auth)
        assert r.status_code == 409 and r.json()["error"]["code"] == "symbol_ambiguous"
        assert c.get("/api/v1/market/EURUSD.pro/tick", headers=auth).status_code == 200


def test_app_starts_when_terminal_unavailable(auth):
    clock = FakeClock()
    adapter = MockAdapter(clock=clock)
    adapter.terminal_available = False
    with build_client(make_settings(), adapter, clock) as c:
        assert c.get("/api/v1/health").status_code == 200
        assert c.get("/api/v1/ready").status_code == 503
        status = c.get("/api/v1/mt5/status", headers=auth).json()
        assert status["initialized"] is False and status["last_error"]["code"] == -10003
        r = c.get("/api/v1/market/EURUSD/candles", headers=auth)
        assert r.status_code == 503 and r.json()["error"]["code"] == "broker_unavailable"


def test_broker_disconnect_returns_503(client, auth, adapter):
    adapter.broker_connected = False
    assert client.get("/api/v1/account", headers=auth).status_code == 503
    assert client.get("/api/v1/ready").status_code == 503


def test_rate_limit(adapter, clock, auth):
    with build_client(make_settings(rate_limit_per_minute=3), adapter, clock) as c:
        codes = [c.get("/api/v1/mt5/status", headers=auth).status_code for _ in range(5)]
        assert codes == [200, 200, 200, 429, 429]
        assert c.get("/api/v1/health").status_code == 200  # exempt


def test_cors_only_for_configured_origins(adapter, clock):
    settings = make_settings(cors_allowed_origins=["http://localhost:5173"])
    with build_client(settings, adapter, clock) as c:
        ok = c.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
        bad = c.get("/api/v1/health", headers={"Origin": "http://evil.example"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in bad.headers
