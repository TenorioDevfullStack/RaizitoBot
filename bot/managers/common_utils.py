import re
import os
from datetime import date, datetime, time, timedelta
from bot.time_utils import local_date, local_now, parse_local_datetime, app_timezone

RELATIVE_AMOUNT_PATTERN = r"\d{1,3}|um|uma|uns|umas|alguns|algumas|poucos|poucas"

WEEKDAYS = {
    "segunda": 0, "terca": 1, "terça": 1, "quarta": 2, "quinta": 3,
    "sexta": 4, "sabado": 5, "sábado": 5, "domingo": 6,
}

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

def _parse_relative_amount(raw_amount, unit):
    value = raw_amount.strip().lower()
    if value.isdigit():
        return int(value)
    if value in {"um", "uma"}:
        return 1
    if unit.startswith("h"):
        return 2
    return 5

def _next_weekday(target_weekday):
    today = local_date()
    days_ahead = (target_weekday - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)

def _parse_due_date(text):
    lowered = text.lower()
    today = local_date()

    if re.search(r"\b(hoje)\b", lowered):
        return today
    if re.search(r"\b(depois de amanha|depois de amanhã)\b", lowered):
        return today + timedelta(days=2)
    if re.search(r"\b(amanha|amanhã)\b", lowered):
        return today + timedelta(days=1)

    days_match = re.search(rf"\b(?:em|daqui\s+a?)\s+({RELATIVE_AMOUNT_PATTERN})\s+dias?\b", lowered)
    if days_match:
        return today + timedelta(days=_parse_relative_amount(days_match.group(1), "dias"))

    date_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", lowered)
    if date_match:
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        year_text = date_match.group(3)
        year = int(year_text) if year_text else today.year
        if year < 100: year += 2000
        try: due = date(year, month, day)
        except ValueError: return None
        if not year_text and due < today:
            due = date(today.year + 1, month, day)
        return due

    for name, weekday in WEEKDAYS.items():
        if re.search(rf"\b{name}\b", lowered):
            return _next_weekday(weekday)
    return None

def _calendar_backend():
    backend = (os.getenv("CALENDAR_BACKEND") or "internal").strip().lower()
    aliases = {
        "local": "internal", "interno": "internal", "agenda_interna": "internal",
        "calendar": "google", "google_calendar": "google", "gcal": "google", "ambos": "both",
    }
    return aliases.get(backend, backend if backend in {"internal", "google", "both"} else "internal")

def _calendar_uses_internal():
    return _calendar_backend() in {"internal", "both"}

def _calendar_uses_google():
    return _calendar_backend() in {"google", "both"}
