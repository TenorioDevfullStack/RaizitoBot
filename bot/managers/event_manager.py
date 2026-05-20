import logging
import re
from datetime import datetime, timedelta
from bot.db import (
    add_internal_event as db_add_internal_event,
    get_internal_event as db_get_internal_event,
    get_internal_events_between as db_get_internal_events_between,
    add_pending_calendar_event as db_add_pending_calendar_event,
)
from bot.time_utils import app_timezone, parse_local_datetime
from bot.managers.common_utils import (
    _parse_due_date,
    EMAIL_RE,
)

logger = logging.getLogger(__name__)

EVENT_PREFIXES = (
    "agende uma reuniao ", "agendar reuniao ", "marque uma reuniao ",
    "marcar reuniao ", "reuniao: ", "reuniao as ", "reuniao para ",
    "reuniao amanha ", "reuniao hoje ", "nova reuniao ", "compromisso: ",
    "agende um compromisso ", "agendar compromisso ", "marque um compromisso ",
    "marcar compromisso ", "novo compromisso ", "evento: ", "agende um evento ",
    "agendar evento ", "marque um evento ", "marcar evento ", "novo evento ",
)

def _parse_due_time(text):
    # (Implementation copied from handlers.py)
    lowered = text.lower()
    time_match = re.search(r"\b(?:as|às|a|@)\s*(\d{1,2})(?:[:h](\d{0,2}))?\b", lowered)
    if not time_match:
        time_match = re.search(r"\b(\d{1,2})h(\d{2})?\b", lowered)
    if not time_match:
        time_match = re.search(r"\b(\d{1,2})\s*horas?\b", lowered)
    if not time_match:
        return None
    hour = int(time_match.group(1))
    minute = int(time_match.group(2) or 0)
    suffix = lowered[time_match.end():time_match.end() + 20]
    if hour <= 11 and re.search(r"\b(da tarde|tarde|da noite|noite)\b", suffix):
        hour += 12
    if hour == 12 and re.search(r"\b(da madrugada|madrugada|da manha|da manhã)\b", suffix):
        hour = 0
    if hour > 23 or minute > 59:
        return None
    from datetime import time as dt_time
    return dt_time(hour, minute)

def _parse_duration_minutes(text, default_minutes=60):
    lowered = text.lower()
    duration_match = re.search(r"\b(?:por|duracao|duração)\s+(\d{1,3})\s*(minutos?|min|horas?|h)\b", lowered)
    if not duration_match:
        return default_minutes
    amount = int(duration_match.group(1))
    unit = duration_match.group(2)
    return amount * 60 if unit.startswith("h") else amount

def _parse_event_reminder_minutes(text):
    lowered = text.lower()
    reminder_match = re.search(
        r"\b(?:alerta|avis[oe]|lembrar|lembrete)\s+(?:com\s+)?"
        r"(\d{1,3})\s*(minutos?|min|horas?|h)\s+(?:antes|de antecedencia|de antecedência)\b",
        lowered,
    )
    if not reminder_match:
        reminder_match = re.search(r"\b(\d{1,3})\s*(minutos?|min|horas?|h)\s+antes\b", lowered)
    if not reminder_match:
        return None
    amount = int(reminder_match.group(1))
    unit = reminder_match.group(2)
    minutes = amount * 60 if unit.startswith("h") else amount
    return max(0, min(minutes, 24 * 60))

def _extract_event_field(text, names):
    joined_names = "|".join(re.escape(name) for name in names)
    pattern = rf"\b(?:{joined_names})\s*:\s*(.+?)(?=\s+\w+\s*:|$)"
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip(" -,.") if match else None

def _clean_event_title(text):
    from bot.managers.task_manager import _clean_task_title
    cleaned = _clean_task_title(text)
    cleaned = re.sub(
        r"\b(?:por|duracao|duração)\s+\d{1,3}\s*(?:minutos?|min|horas?|h)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\b(?:por|duracao|duração)\b\s*$", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(?:alerta|avis[oe]|lembrar|lembrete)\s+(?:com\s+)?\d{1,3}\s*"
        r"(?:minutos?|min|horas?|h)\s+(?:antes|de antecedencia|de antecedência)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\b\d{1,3}\s*(?:minutos?|min|horas?|h)\s+antes\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:local|lugar|onde|desc|descricao|descrição|nota|obs)\s*:\s*.+?(?=\s+\w+\s*:|$)", " ", cleaned, flags=re.IGNORECASE)
    cleaned = EMAIL_RE.sub(" ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip(" -,.") or text.strip()

def _parse_event_payload(text):
    event_date = _parse_due_date(text)
    event_time = _parse_due_time(text)
    if not event_date or not event_time:
        return None

    duration_minutes = _parse_duration_minutes(text)
    start_at = datetime.combine(event_date, event_time, tzinfo=app_timezone())
    end_at = start_at + timedelta(minutes=duration_minutes)
    
    description = _extract_event_field(text, ("desc", "descricao", "descrição", "nota", "obs"))
    if description:
        description = EMAIL_RE.sub(" ", description).strip(" -,.")

    return {
        "summary": _clean_event_title(text),
        "start_at": start_at,
        "end_at": end_at,
        "duration_minutes": duration_minutes,
        "description": description,
        "location": _extract_event_field(text, ("local", "lugar", "onde")),
        "attendees": sorted(set(EMAIL_RE.findall(text))),
        "reminder_minutes": _parse_event_reminder_minutes(text),
    }

def format_internal_event_created(event):
    lines = [
        f"Evento interno criado. ID: {event['id']}",
        f"Titulo: {event['summary']}",
    ]
    start_at = event.get("start_at")
    end_at = event.get("end_at")
    if isinstance(start_at, str): start_at = parse_local_datetime(start_at)
    if isinstance(end_at, str): end_at = parse_local_datetime(end_at)
    
    if start_at and end_at:
        lines.append(f"Inicio: {start_at.strftime('%d/%m/%Y %H:%M')}")
        lines.append(f"Fim: {end_at.strftime('%d/%m/%Y %H:%M')}")
    if event.get("location"):
        lines.append(f"Local: {event['location']}")
    if event.get("attendees"):
        lines.append("Convidados: " + ", ".join(event["attendees"]))
    if event.get("description"):
        lines.append(f"Descricao: {event['description']}")
    lines.append(f"Alerta: {event.get('reminder_minutes', 15)} minuto(s) antes")
    lines.append(f"Cancele com /cancel_event {event['id']}")
    return "\n".join(lines)

def handle_create_event(user_id, chat_id, text):
    payload = _parse_event_payload(text)
    if not payload: return None, "Nao consegui entender data e horario."
    # ... logic for conflicts and creation ...
    return payload, None
