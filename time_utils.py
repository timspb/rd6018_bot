"""
time_utils.py — утилиты для работы с часовыми поясами v2.6
Все временные метки приводятся к USER_TIMEZONE из config.
"""
import pytz
from datetime import datetime
from typing import Optional

from config import USER_TIMEZONE


def get_user_timezone() -> pytz.BaseTzInfo:
    """Получить объект часового пояса пользователя."""
    try:
        return pytz.timezone(USER_TIMEZONE)
    except pytz.UnknownTimeZoneError:
        # Fallback на Moscow если указан неверный timezone
        return pytz.timezone("Europe/Moscow")


def now_user_tz() -> datetime:
    """Текущее время в часовом поясе пользователя."""
    utc_now = datetime.utcnow().replace(tzinfo=pytz.UTC)
    user_tz = get_user_timezone()
    return utc_now.astimezone(user_tz)


def format_time_user_tz(dt: Optional[datetime] = None, fmt: str = "%H:%M:%S") -> str:
    """Форматировать время в часовом поясе пользователя."""
    if dt is None:
        dt = now_user_tz()
    elif dt.tzinfo is None:
        # Если datetime naive, считаем что это UTC
        dt = dt.replace(tzinfo=pytz.UTC).astimezone(get_user_timezone())
    elif dt.tzinfo != get_user_timezone():
        # Конвертируем в пользовательский часовой пояс
        dt = dt.astimezone(get_user_timezone())
    
    return dt.strftime(fmt)


def format_datetime_user_tz(dt: Optional[datetime] = None, fmt: str = "%d.%m %H:%M:%S") -> str:
    """Форматировать дату и время в часовом поясе пользователя."""
    return format_time_user_tz(dt, fmt)


def timestamp_to_user_tz(timestamp: float) -> datetime:
    """Конвертировать timestamp в datetime с пользовательским часовым поясом."""
    utc_dt = datetime.utcfromtimestamp(timestamp).replace(tzinfo=pytz.UTC)
    return utc_dt.astimezone(get_user_timezone())