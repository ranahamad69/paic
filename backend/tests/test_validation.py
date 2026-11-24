from datetime import UTC, datetime, timedelta

from app.core.timeutil import parse_timezone
from app.market_data.models import IssueCode, Severity
from app.market_data.timeframes import Timeframe
from app.market_data.validation import parse_bars, validate_candles
from tests.conftest import FIXED_NOW

H1 = Timeframe.H1


def epoch(dt: datetime) -> int:
    """Server wall-clock datetime (naive) -> MT5-style epoch."""
    return int((dt - datetime(1970, 1, 1)).total_seconds())


def bar(t: datetime, o=1.1000, h=1.1010, low=1.0990, c=1.1005, vol=100) -> dict:
    return {"time": epoch(t), "open": o, "high": h, "low": low, "close": c, "tick_volume": vol, "spread": 10}


def hourly(start: datetime, n: int) -> list[dict]:
    return [bar(start + timedelta(hours=i)) for i in range(n)]


def run(raw, tf=H1, tz=UTC, now=FIXED_NOW):
    candles, issues = parse_bars(raw, tf, tz, now)
    return candles, validate_candles(candles, tf, tz, now, issues)


def codes(report):
    return [i.code for i in report.issues]


def test_clean_series_with_forming_bar():
    # 06:00..10:00 UTC; now is 10:30 so the 10:00 bar is still forming.
    candles, rep = run(hourly(datetime(2026, 11, 25, 6), 5))
    assert rep.is_valid and rep.issues == []
    assert rep.received == 5 and rep.closed_count == 4 and rep.has_forming_bar
    assert candles[-1].is_closed is False and all(c.is_closed for c in candles[:-1])
    assert candles[0].open_time.tzinfo is not None
    assert candles[0].close_time - candles[0].open_time == timedelta(hours=1)


def test_server_timezone_is_converted_to_utc(utc_plus_2):
    # Server UTC+2: wall-clock 12:00 is 10:00 UTC -> forming at 10:30 UTC.
    candles, rep = run(hourly(datetime(2026, 11, 25, 9), 4), tz=utc_plus_2)
    assert candles[-1].open_time == datetime(2026, 11, 25, 10, tzinfo=UTC)
    assert rep.is_valid and rep.has_forming_bar


def test_wrong_timezone_shows_up_as_future_bars():
    # Broker is UTC+2 but configured as UTC: newest bars appear 2h in the future.
    _, rep = run(hourly(datetime(2026, 11, 25, 9), 4), tz=UTC)
    assert not rep.is_valid
    assert IssueCode.FUTURE_BAR in codes(rep)


def test_duplicate_bar_is_error():
    raw = hourly(datetime(2026, 11, 25, 5), 3)
    raw.insert(2, dict(raw[1]))
    _, rep = run(raw)
    assert not rep.is_valid and IssueCode.DUPLICATE in codes(rep)


def test_out_of_order_is_error():
    raw = hourly(datetime(2026, 11, 25, 5), 4)
    raw[1], raw[2] = raw[2], raw[1]
    _, rep = run(raw)
    assert IssueCode.OUT_OF_ORDER in codes(rep) and not rep.is_valid


def test_inconsistent_ohlc_and_bad_prices():
    t = datetime(2026, 11, 25, 5)
    raw = [
        bar(t, h=1.0980),  # high below low
        bar(t + timedelta(hours=1), c=1.2),  # close above high
        bar(t + timedelta(hours=2), o=float("nan")),
        bar(t + timedelta(hours=3), low=0.0),
        bar(t + timedelta(hours=4), vol=-1),
    ]
    _, rep = run(raw)
    found = codes(rep)
    assert found.count(IssueCode.INCONSISTENT_OHLC) == 2
    assert found.count(IssueCode.INVALID_PRICE) == 2
    assert IssueCode.NEGATIVE_VOLUME in found
    assert not rep.is_valid


def test_malformed_record_is_reported_not_crashing():
    raw = hourly(datetime(2026, 11, 25, 5), 2) + [{"time": "garbage"}, {"open": 1.0}]
    candles, rep = run(raw)
    assert len(candles) == 2
    assert codes(rep).count(IssueCode.MALFORMED_RECORD) == 2
    assert not rep.is_valid


def test_empty_series_is_error():
    _, rep = run([])
    assert not rep.is_valid and codes(rep) == [IssueCode.EMPTY]


def test_intraday_gap_is_warning():
    t = datetime(2026, 11, 25, 2)
    raw = [bar(t), bar(t + timedelta(hours=1)), bar(t + timedelta(hours=4))]
    _, rep = run(raw)
    gap = [i for i in rep.issues if i.code is IssueCode.GAP]
    assert len(gap) == 1 and gap[0].severity is Severity.WARNING and "2 bar(s)" in gap[0].message
    assert rep.is_valid  # gaps are warnings


def test_weekend_gap_classified_separately():
    fri = datetime(2026, 11, 20, 22)  # Friday 22:00 server time
    mon = datetime(2026, 11, 23, 0)  # Monday 00:00
    _, rep = run([bar(fri), bar(fri + timedelta(hours=1)), bar(mon)])
    assert codes(rep) == [IssueCode.WEEKEND_GAP]


def test_long_outage_spanning_weekend_is_plain_gap():
    _, rep = run([bar(datetime(2026, 11, 18, 10)), bar(datetime(2026, 11, 24, 10))])
    assert IssueCode.GAP in codes(rep) and IssueCode.WEEKEND_GAP not in codes(rep)


def test_stale_history_warning():
    _, rep = run(hourly(datetime(2026, 11, 10, 5), 3))
    assert IssueCode.STALE in codes(rep)


def test_unclosed_bar_not_last_is_error():
    raw = hourly(datetime(2026, 11, 25, 9), 2) + [bar(datetime(2026, 11, 25, 8))]
    _, rep = run(raw)
    assert not rep.is_valid


def test_d1_forming_bar_respects_server_midnight():
    tz = parse_timezone("UTC+2")
    raw = [bar(datetime(2026, 11, d)) for d in (23, 24, 25)]
    candles, rep = run(raw, tf=Timeframe.D1, tz=tz)
    # 25 Nov server midnight = 24 Nov 22:00 UTC; closes 25 Nov 22:00 UTC > now -> forming.
    assert candles[-1].open_time == datetime(2026, 11, 24, 22, tzinfo=UTC)
    assert rep.has_forming_bar and rep.closed_count == 2 and rep.is_valid
