"""UTC normalisation helpers.

MetaTrader 5 reports bar and tick times as Unix-epoch seconds *in the broker's
trade-server timezone* (the server's wall-clock time encoded as if it were
UTC). To get true UTC we interpret the epoch as naive server wall-clock time,
attach the configured server timezone, and convert to UTC.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_OFFSET_RE = re.compile(r"^(?:UTC|GMT)\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?$", re.IGNORECASE)


def parse_timezone(value: str) -> tzinfo:
    """Parse ``"UTC"``, ``"UTC+2"``, ``"GMT-05:30"`` or an IANA zone name."""
    text = value.strip()
    if text.upper() in {"UTC", "GMT", "Z"}:
        return UTC
    match = _OFFSET_RE.match(text)
    if match:
        sign, hours, minutes = match.groups()
        delta = timedelta(hours=int(hours), minutes=int(minutes or 0))
        if delta > timedelta(hours=14):
            raise ValueError(f"UTC offset out of range: {value!r}")
        return timezone(-delta if sign == "-" else delta)
    try:
        return ZoneInfo(text)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown timezone: {value!r}") from exc


def server_epoch_to_utc(epoch_seconds: float, server_tz: tzinfo) -> datetime:
    """Convert an MT5 server-time epoch to a timezone-aware UTC datetime."""
    wall_clock = datetime(1970, 1, 1) + timedelta(seconds=float(epoch_seconds))
    return wall_clock.replace(tzinfo=server_tz).astimezone(UTC)


def utc_now() -> datetime:
    return datetime.now(UTC)
