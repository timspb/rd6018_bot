"""Canonical time handling for the bot.

Internal timestamps are UTC-aware or epoch seconds. User-facing text is
formatted in USER_TIMEZONE. Naive datetimes from legacy data are interpreted
as UTC at the boundary, never as local server time.
"""
from datetime import datetime, timezone
from typing import Optional

import pytz

from config import USER_TIMEZONE


def get_user_timezone() -> pytz.BaseTzInfo:
    try:
        return pytz.timezone(USER_TIMEZONE)
    except pytz.UnknownTimeZoneError:
        return pytz.timezone("Europe/Moscow")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    """Normalize a datetime; legacy naive values are explicitly treated as UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_datetime(value: str) -> datetime:
    """Parse ISO-8601 text and return an aware UTC datetime."""
    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    return ensure_utc(datetime.fromisoformat(raw))


def timestamp_iso_utc(timestamp: float) -> str:
    return datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def now_user_tz() -> datetime:
    return now_utc().astimezone(get_user_timezone())


def format_time_user_tz(dt: Optional[datetime] = None, fmt: str = "%H:%M:%S") -> str:
    if dt is None:
        dt = now_user_tz()
    else:
        dt = ensure_utc(dt).astimezone(get_user_timezone())
    return dt.strftime(fmt)


def format_datetime_user_tz(dt: Optional[datetime] = None, fmt: str = "%d.%m %H:%M:%S") -> str:
    return format_time_user_tz(dt, fmt)


def timestamp_to_user_tz(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(get_user_timezone())
