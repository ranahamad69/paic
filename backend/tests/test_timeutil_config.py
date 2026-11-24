from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.core.config import AdapterKind, Settings
from app.core.security import mask_identifier
from app.core.timeutil import parse_timezone, server_epoch_to_utc


@pytest.mark.parametrize(
    "text,offset",
    [("UTC", 0), ("GMT", 0), ("UTC+2", 2), ("UTC+03:00", 3), ("GMT-5", -5), ("UTC+0530", 5.5)],
)
def test_parse_fixed_offsets(text, offset):
    tz = parse_timezone(text)
    assert datetime(2026, 1, 1, tzinfo=tz).utcoffset() == timedelta(hours=offset)


def test_parse_iana_zone_handles_dst():
    tz = parse_timezone("Europe/Athens")
    assert datetime(2026, 1, 15, tzinfo=tz).utcoffset() == timedelta(hours=2)
    assert datetime(2026, 7, 15, tzinfo=tz).utcoffset() == timedelta(hours=3)


@pytest.mark.parametrize("bad", ["Mars/Olympus", "UTC+25", "", "+2"])
def test_parse_rejects_invalid(bad):
    with pytest.raises(ValueError):
        parse_timezone(bad)


def test_server_epoch_to_utc_shifts_by_server_offset():
    # MT5 reports 2026-11-25 12:00 server wall-clock as this epoch.
    epoch = int((datetime(2026, 11, 25, 12, 0) - datetime(1970, 1, 1)).total_seconds())
    result = server_epoch_to_utc(epoch, parse_timezone("UTC+2"))
    assert result == datetime(2026, 11, 25, 10, 0, tzinfo=UTC)
    assert result.tzinfo is not None


def test_settings_parse_csv_and_json(monkeypatch):
    monkeypatch.setenv("SYMBOL_UNIVERSE", "eurusd, gbpusd")
    monkeypatch.setenv("SYMBOL_MAP_OVERRIDES", '{"eurusd": "EURUSD.pro"}')
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173,https://x.example")
    s = Settings(_env_file=None)
    assert s.symbol_universe == ["EURUSD", "GBPUSD"]
    assert s.symbol_map_overrides == {"EURUSD": "EURUSD.pro"}
    assert s.cors_allowed_origins == ["http://localhost:5173", "https://x.example"]


def test_settings_defaults_are_safe():
    s = Settings(_env_file=None)
    assert s.mt5_adapter is AdapterKind.MT5  # mock data only on explicit opt-in
    assert s.api_auth_token is None  # protected endpoints fail closed until configured
    assert s.cors_allowed_origins == []
    assert len(s.symbol_universe) == 20


def test_settings_reject_bad_timezone():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, mt5_server_timezone="Nowhere/Land")


def test_secrets_not_rendered_in_repr():
    s = Settings(_env_file=None, mt5_password="hunter2", api_auth_token="tok")
    assert "hunter2" not in repr(s) and "tok'" not in repr(s)


@pytest.mark.parametrize("value,expected", [(12345678, "*****678"), ("12", "**"), (None, ""), ("", "")])
def test_mask_identifier(value, expected):
    assert mask_identifier(value) == expected
