import pytest

from app.core.errors import SymbolAmbiguousError, SymbolNotFoundError
from app.mt5_connector.connector import MT5Connector
from app.mt5_connector.mock_adapter import MockAdapter, _forex_symbol
from app.symbol_manager.manager import SymbolManager, build_mapping, is_forex_record, spec_from_record
from app.symbol_manager.models import MappingStatus
from tests.conftest import FakeMonotonic


def _manager(adapter: MockAdapter, universe=("EURUSD", "USDJPY"), overrides=None) -> SymbolManager:
    conn = MT5Connector(adapter, monotonic=FakeMonotonic())
    assert conn.connect()
    return SymbolManager(conn, list(universe), overrides)


def test_forex_filter_excludes_metals_and_indices(symbols):
    names = {s.name for s in symbols.forex_symbols()}
    assert "EURUSD" in names and "USDJPY" in names
    assert "XAUUSD" not in names  # metal, not fiat
    assert "US500" not in names  # CFD calc mode
    assert len(names) == 20


@pytest.mark.parametrize(
    "rec,expected",
    [
        ({"trade_calc_mode": 0, "currency_base": "EUR", "currency_profit": "USD"}, True),
        ({"trade_calc_mode": 5, "currency_base": "USD", "currency_profit": "JPY"}, True),
        ({"trade_calc_mode": 0, "currency_base": "BTC", "currency_profit": "USD"}, False),
        ({"trade_calc_mode": 2, "currency_base": "EUR", "currency_profit": "USD"}, False),
        ({"trade_calc_mode": 0, "currency_base": "USD", "currency_profit": "USD"}, False),
        ({}, False),
    ],
)
def test_is_forex_record(rec, expected):
    assert is_forex_record(rec) is expected


def test_spec_captures_contract_details_jpy_vs_non_jpy(symbols):
    eur = symbols.resolve("EURUSD")
    jpy = symbols.resolve("USDJPY")
    assert (eur.digits, eur.point) == (5, 1e-5)
    assert (jpy.digits, jpy.point) == (3, 1e-3)
    for s in (eur, jpy):
        assert s.contract_size == 100_000 and s.volume_min == 0.01 and s.volume_step == 0.01
        assert s.tick_size > 0 and s.stops_level_points >= 0


def test_suffix_symbols_map_to_canonical(clock):
    mgr = _manager(MockAdapter(symbol_suffix=".r", clock=clock))
    mapping = mgr.mapping()
    assert mapping["EURUSD"].broker_symbol == "EURUSD.r"
    assert mapping["EURUSD"].source == "unique_candidate"
    assert mgr.resolve("EURUSD").name == "EURUSD.r"
    assert mgr.resolve("EURUSD.r").canonical == "EURUSD"


def test_ambiguous_without_override_then_resolved_by_override(clock):
    adapter = MockAdapter(symbol_suffix=".r", clock=clock)
    adapter._symbols["EURUSD.pro"] = _forex_symbol("EURUSD.pro", "EUR", "USD", 1.08)
    mgr = _manager(adapter)
    assert mgr.mapping()["EURUSD"].status is MappingStatus.AMBIGUOUS
    with pytest.raises(SymbolAmbiguousError):
        mgr.resolve("EURUSD")

    mgr2 = _manager(adapter, overrides={"EURUSD": "EURUSD.pro"})
    assert mgr2.resolve("EURUSD").name == "EURUSD.pro"
    assert mgr2.mapping()["EURUSD"].source == "override"


def test_exact_name_preferred_over_suffixed_variant(symbols, adapter):
    adapter._symbols["EURUSD.ecn"] = _forex_symbol("EURUSD.ecn", "EUR", "USD", 1.08)
    symbols.refresh(force=True)
    assert symbols.mapping()["EURUSD"].broker_symbol == "EURUSD"


def test_invalid_override_is_missing_not_silently_ignored(clock):
    mgr = _manager(MockAdapter(clock=clock), overrides={"EURUSD": "GBPUSD"})
    assert mgr.mapping()["EURUSD"].status is MappingStatus.MISSING


def test_missing_pair_reported(clock):
    adapter = MockAdapter(clock=clock)
    del adapter._symbols["USDJPY"]
    mgr = _manager(adapter)
    assert mgr.mapping()["USDJPY"].status is MappingStatus.MISSING
    with pytest.raises(SymbolNotFoundError):
        mgr.resolve("USDJPY")


@pytest.mark.parametrize("bad", ["../etc", "EUR USD", "x" * 40, "EU"])
def test_resolve_rejects_bad_input(symbols, bad):
    with pytest.raises(SymbolNotFoundError):
        symbols.resolve(bad)


def test_malformed_symbol_record_rejected_and_counted(symbols, adapter):
    bad = _forex_symbol("EURCHF", "EUR", "CHF", 0.96)
    bad["point"] = 0  # invalid
    adapter._symbols["EURCHF"] = bad
    symbols.refresh(force=True)
    assert symbols.rejected_count == 1
    assert "EURCHF" not in {s.name for s in symbols.forex_symbols()}


def test_spec_from_record_zero_tick_value_becomes_none():
    rec = {k: v for k, v in _forex_symbol("EURUSD", "EUR", "USD", 1.0).items() if not k.startswith("_")}
    rec["trade_tick_value"] = 0.0
    assert spec_from_record(rec).tick_value is None


def test_discovery_is_cached(symbols, adapter):
    symbols.forex_symbols()
    adapter._symbols["EURNOK"] = _forex_symbol("EURNOK", "EUR", "NOK", 11.5)
    assert "EURNOK" not in {s.name for s in symbols.forex_symbols()}
    symbols.refresh(force=True)
    assert "EURNOK" in {s.name for s in symbols.forex_symbols()}


def test_ensure_selected_enables_hidden_symbol(symbols, adapter):
    spec = symbols.resolve("EURUSD")
    assert adapter._symbols["EURUSD"]["visible"] is False
    symbols.ensure_selected(spec)
    assert adapter._symbols["EURUSD"]["visible"] is True


def test_build_mapping_pure():
    specs = [
        spec_from_record({k: v for k, v in _forex_symbol(n, n[:3], n[3:6], 1.0).items() if not k.startswith("_")})
        for n in ("EURUSDm", "GBPUSD")
    ]
    m = build_mapping(["EURUSD", "GBPUSD", "AUDUSD"], specs, {})
    assert m["EURUSD"].broker_symbol == "EURUSDm"
    assert m["GBPUSD"].source == "exact"
    assert m["AUDUSD"].status is MappingStatus.MISSING
