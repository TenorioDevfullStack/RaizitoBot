import os
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_TIMEZONE = "America/Sao_Paulo"


def app_timezone_name():
    return (
        os.getenv("APP_TIMEZONE")
        or os.getenv("BOT_TIMEZONE")
        or os.getenv("GOOGLE_CALENDAR_TIMEZONE")
        or os.getenv("TZ")
        or DEFAULT_TIMEZONE
    ).strip()


def app_timezone():
    name = app_timezone_name() or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_TIMEZONE)


def local_now():
    return datetime.now(app_timezone())


def local_date():
    return local_now().date()


def ensure_local_datetime(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=app_timezone())
    return value.astimezone(app_timezone())


def parse_local_datetime(value):
    if not value:
        return None
    try:
        return ensure_local_datetime(datetime.fromisoformat(value))
    except ValueError:
        return None
