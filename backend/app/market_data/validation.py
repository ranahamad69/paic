"""Pure functions that convert raw MT5 bars to candles and detect data problems.

Nothing is silently fixed: problems are reported in a ``ValidationReport`` and
``is_valid`` is False whenever any ERROR-severity issue exists, so downstream
consumers can fail closed.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, tzinfo
from typing import Any

from app.core.timeutil import server_epoch_to_utc
from app.market_data.models import Candle, IssueCode, Severity, ValidationIssue, ValidationReport
from app.market_data.timeframes import Timeframe

#: A bar timestamp this far ahead of "now" indicates a timezone misconfiguration.
FUTURE_TOLERANCE = timedelta(minutes=2)
#: Longest gap that can still be a normal weekend closure (Fri close -> Mon open, plus slack).
MAX_WEEKEND_GAP = timedelta(hours=72)


def parse_bars(
    raw: Iterable[Mapping[str, Any]], timeframe: Timeframe, server_tz: tzinfo, now: datetime
) -> tuple[list[Candle], list[ValidationIssue]]:
    """Convert raw bars to candles. Unparseable records are reported and skipped."""
    candles: list[Candle] = []
    issues: list[ValidationIssue] = []
    for i, rec in enumerate(raw):
        try:
            open_time = server_epoch_to_utc(float(rec["time"]), server_tz)
            close_time = open_time + timeframe.duration
            candles.append(
                Candle(
                    open_time=open_time,
                    close_time=close_time,
                    open=float(rec["open"]),
                    high=float(rec["high"]),
                    low=float(rec["low"]),
                    close=float(rec["close"]),
                    tick_volume=int(rec.get("tick_volume", 0)),
                    real_volume=int(rec.get("real_volume", 0) or 0),
                    spread_points=int(rec["spread"]) if rec.get("spread") is not None else None,
                    is_closed=close_time <= now,
                )
            )
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    code=IssueCode.MALFORMED_RECORD,
                    index=None,
                    message=f"Raw record #{i} could not be parsed: {type(exc).__name__}: {exc}",
                )
            )
    return candles, issues


def _issue(sev: Severity, code: IssueCode, idx: int, c: Candle, msg: str) -> ValidationIssue:
    return ValidationIssue(severity=sev, code=code, index=idx, time=c.open_time, message=msg)


def _contains_server_weekend(start_utc: datetime, end_utc: datetime, server_tz: tzinfo) -> bool:
    """True if the half-open interval [start, end) touches a server-time Saturday."""
    t = start_utc
    while t < end_utc:
        if t.astimezone(server_tz).weekday() == 5:
            return True
        t += timedelta(hours=1)
    return False


def validate_candles(
    candles: list[Candle],
    timeframe: Timeframe,
    server_tz: tzinfo,
    now: datetime,
    prior_issues: Iterable[ValidationIssue] = (),
) -> ValidationReport:
    issues = list(prior_issues)
    step = timeframe.duration

    if not candles:
        issues.append(ValidationIssue(severity=Severity.ERROR, code=IssueCode.EMPTY, message="No candles returned"))

    seen: set[datetime] = set()
    for idx, c in enumerate(candles):
        prices = (c.open, c.high, c.low, c.close)
        if any(not math.isfinite(p) or p <= 0 for p in prices):
            issues.append(
                _issue(Severity.ERROR, IssueCode.INVALID_PRICE, idx, c, f"Non-positive or non-finite price {prices}")
            )
        elif c.high < c.low or not (c.low <= c.open <= c.high) or not (c.low <= c.close <= c.high):
            issues.append(_issue(Severity.ERROR, IssueCode.INCONSISTENT_OHLC, idx, c, f"OHLC inconsistent {prices}"))
        if c.tick_volume < 0 or c.real_volume < 0:
            issues.append(_issue(Severity.ERROR, IssueCode.NEGATIVE_VOLUME, idx, c, "Negative volume"))
        if c.open_time > now + FUTURE_TOLERANCE:
            issues.append(
                _issue(
                    Severity.ERROR, IssueCode.FUTURE_BAR, idx, c, "Bar opens in the future; check MT5_SERVER_TIMEZONE"
                )
            )
        if not c.is_closed and idx != len(candles) - 1:
            issues.append(_issue(Severity.ERROR, IssueCode.FUTURE_BAR, idx, c, "Unclosed bar is not the newest bar"))
        if c.open_time in seen:
            issues.append(_issue(Severity.ERROR, IssueCode.DUPLICATE, idx, c, "Duplicate bar open time"))
        seen.add(c.open_time)

        if idx == 0:
            continue
        prev = candles[idx - 1]
        delta = c.open_time - prev.open_time
        if delta < timedelta(0):
            issues.append(
                _issue(
                    Severity.ERROR,
                    IssueCode.OUT_OF_ORDER,
                    idx,
                    c,
                    f"Bar earlier than previous ({prev.open_time.isoformat()})",
                )
            )
        elif delta > step:
            missing = int(delta / step) - 1
            weekend = delta <= MAX_WEEKEND_GAP + step and _contains_server_weekend(
                prev.open_time + step, c.open_time, server_tz
            )
            code = IssueCode.WEEKEND_GAP if weekend else IssueCode.GAP
            issues.append(
                _issue(Severity.WARNING, code, idx, c, f"{missing} bar(s) missing after {prev.open_time.isoformat()}")
            )

    if candles:
        newest = candles[-1]
        if newest.close_time < now - (step + MAX_WEEKEND_GAP):
            issues.append(
                _issue(
                    Severity.WARNING,
                    IssueCode.STALE,
                    len(candles) - 1,
                    newest,
                    "Newest bar is older than expected; history may be stale",
                )
            )

    closed = sum(c.is_closed for c in candles)
    return ValidationReport(
        is_valid=not any(i.severity is Severity.ERROR for i in issues),
        issues=issues,
        received=len(candles),
        closed_count=closed,
        has_forming_bar=bool(candles) and not candles[-1].is_closed,
    )
