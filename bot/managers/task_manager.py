import logging
import re
import json
from datetime import date, datetime, time, timedelta
from bot.db import (
    add_task as db_add_task,
    get_tasks as db_get_tasks,
    update_task as db_update_task,
    delete_task as db_delete_task,
    complete_task_with_recurrence as db_complete_task,
    get_due_task_reminders as db_get_due_reminders,
    mark_task_reminded as db_mark_reminded,
)
from bot.time_utils import app_timezone, local_date, local_now, parse_local_datetime

logger = logging.getLogger(__name__)

# --- Constants ---

TASK_PRIORITY_LABELS = {
    "alta": "🔴 Alta",
    "media": "🟠 Média",
    "média": "🟠 Média",
    "normal": "⚪ Normal",
    "baixa": "🟢 Baixa",
}

TASK_RECURRENCE_LABELS = {
    "diaria": "Diária",
    "semanal": "Semanal",
    "mensal": "Mensal",
}

TASK_FILTER_ALIASES = {
    "hoje": "today",
    "today": "today",
    "semana": "week",
    "week": "week",
    "atrasadas": "overdue",
    "overdue": "overdue",
    "concluidas": "completed",
    "concluídas": "completed",
    "done": "completed",
    "completed": "completed",
    "todas": "all",
    "all": "all",
    "pendentes": "pending",
    "pending": "pending",
}

TASK_PREFIXES = (
    "crie uma tarefa ", "criar tarefa ", "adicione uma tarefa ",
    "adicionar tarefa ", "nova tarefa ", "tarefa: ",
    "crie um lembrete para ", "crie um lembrete de ", "crie um lembrete ",
    "criar lembrete para ", "criar lembrete de ", "criar lembrete ",
    "adicione um lembrete para ", "adicione um lembrete de ", "adicione um lembrete ",
    "adicionar lembrete para ", "adicionar lembrete de ", "adicionar lembrete ",
    "novo lembrete para ", "novo lembrete de ", "novo lembrete ",
    "lembrete: ", "lembrete para ", "lembrete de ", "me avise para ",
    "me avise de ", "me avise pra ", "avise-me para ", "avise-me de ",
    "me lembre de ", "me lembre para ", "me lembre pra ", "me lembra de ",
    "me lembra para ", "me lembra pra ", "lembre-me de ", "lembre-me para ",
    "lembre-me pra ", "lembra-me de ", "lembra-me para ", "lembra-me pra ",
    "me lembrar de ", "anote uma tarefa ", "anotar tarefa ",
)

from bot.managers.common_utils import (
    RELATIVE_AMOUNT_PATTERN,
    WEEKDAYS,
    EMAIL_RE,
    _parse_relative_amount,
    _next_weekday,
    _parse_due_date,
)

# --- Date/Time Parsing Utils --- (Removed, now in common_utils.py)

def _parse_due_time(text):
    lowered = text.lower()
    lowered = re.sub(
        rf"\b(?:em|daqui\s+a?)\s+(?:{RELATIVE_AMOUNT_PATTERN})\s*(?:minutos?|min|horas?|h)\b",
        " ",
        lowered,
    )
    if re.search(r"\b(meio dia|meio-dia)\b", lowered):
        return time(12, 0)
    if re.search(r"\b(meia noite|meia-noite)\b", lowered):
        return time(0, 0)

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
    return time(hour, minute)

# --- Metadata Parsing ---

def _parse_priority(text):
    lowered = text.lower()
    if re.search(r"(!alta|\balta\b|\burgente\b|\bprioridade[:=]\s*alta\b|\bp1\b)", lowered):
        return "alta"
    if re.search(r"(\bmedia\b|\bmédia\b|\bprioridade[:=]\s*(media|média)\b|\bp2\b)", lowered):
        return "media"
    if re.search(r"(\bbaixa\b|\bprioridade[:=]\s*baixa\b|\bp3\b)", lowered):
        return "baixa"
    return "normal"

def _parse_category(text):
    tag_match = re.search(r"(?:^|\s)#([\wÀ-ÿ-]+)", text)
    if tag_match:
        return tag_match.group(1).lower()
    category_match = re.search(r"\b(?:categoria|cat)[:=]\s*([\wÀ-ÿ-]+)", text, re.IGNORECASE)
    return category_match.group(1).lower() if category_match else None

def _parse_recurrence(text):
    lowered = text.lower()
    if re.search(r"\b(todo dia|todos os dias|diaria|diária|diariamente)\b", lowered):
        return "diaria"
    if re.search(r"\b(toda semana|semanal|semanalmente)\b", lowered):
        return "semanal"
    if re.search(r"\b(todo mes|todo mês|mensal|mensalmente)\b", lowered):
        return "mensal"
    return None

def _parse_reminder_at(text, due_date, due_time):
    lowered = text.lower()
    now = local_now()

    relative_match = re.search(
        rf"\b(?:lembrete|lembrar|avisar|me\s+lembre|me\s+lembra|lembre-me|lembra-me)?\s*"
        rf"(?:em|daqui\s+a?)\s+({RELATIVE_AMOUNT_PATTERN})\s*(minutos?|min|horas?|h)\b",
        lowered,
    )
    if not relative_match:
        relative_match = re.search(
            rf"\b({RELATIVE_AMOUNT_PATTERN})\s*(minutos?|min|horas?|h)\s+"
            r"(?:a partir de agora|de agora)\b",
            lowered,
        )
    if relative_match:
        amount = _parse_relative_amount(relative_match.group(1), relative_match.group(2))
        unit = relative_match.group(2)
        delta = timedelta(hours=amount) if unit.startswith("h") else timedelta(minutes=amount)
        return (now + delta).isoformat(timespec="minutes")

    if due_date and due_time:
        if isinstance(due_date, str): due_date = date.fromisoformat(due_date)
        if isinstance(due_time, str): due_time = time.fromisoformat(due_time)
        return datetime.combine(due_date, due_time, tzinfo=app_timezone()).isoformat(timespec="minutes")

    if due_date and re.search(r"\b(lembrete|lembrar|me lembre|lembre-me)\b", lowered):
        if isinstance(due_date, str): due_date = date.fromisoformat(due_date)
        return datetime.combine(due_date, time(9, 0), tzinfo=app_timezone()).isoformat(timespec="minutes")

    return None

# --- Title Cleanup ---

def _strip_task_metadata(text):
    cleaned = text.strip()
    cleaned = re.sub(r"^(?:titulo|título|nome|texto|descricao|descrição)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    patterns = [
        r"\b(?:prioridade|cat|categoria)[:=]\s*[\wÀ-ÿ-]+\b",
        r"(?:^|\s)#[\wÀ-ÿ-]+",
        r"\b(!alta|p1|p2|p3|urgente|prioridade alta|prioridade media|prioridade média|prioridade baixa)\b",
        r"\b(todo dia|todos os dias|diaria|diária|diariamente|toda semana|semanal|semanalmente|todo mes|todo mês|mensal|mensalmente)\b",
        r"\b(hoje|amanha|amanhã|depois de amanha|depois de amanhã)\b",
        rf"\b(?:em|daqui\s+a?)\s+(?:{RELATIVE_AMOUNT_PATTERN})\s+dias?\b",
        rf"\b(?:lembrete|lembrar|avisar|me\s+lembre|me\s+lembra|lembre-me|lembra-me)?\s*"
        rf"(?:em|daqui\s+a?)\s+(?:{RELATIVE_AMOUNT_PATTERN})\s*(?:minutos?|min|horas?|h)\b",
        rf"\b(?:{RELATIVE_AMOUNT_PATTERN})\s*(?:minutos?|min|horas?|h)\s+(?:a partir de agora|de agora)\b",
        r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b",
        r"\b(?:segunda|terca|terça|quarta|quinta|sexta|sabado|sábado|domingo)\b",
        r"\b(?:as|às|a|@)\s*\d{1,2}(?:[:h]\d{0,2})?\b",
        r"\b\d{1,2}h\d{0,2}\b",
        r"\b\d{1,2}\s*horas?\b",
        r"\b(meio dia|meio-dia|meia noite|meia-noite)\b",
        r"\b(da tarde|tarde|da noite|noite|da madrugada|madrugada|da manha|da manhã)\b",
    ]
    for pattern in patterns:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip(" -,.")

def _clean_task_title(text):
    return _strip_task_metadata(text) or text.strip()

# --- Public API (Manager Level) ---

def parse_task_text(text):
    stripped = text.strip()
    lowered = stripped.lower()
    for prefix in TASK_PREFIXES:
        if lowered.startswith(prefix):
            return stripped[len(prefix):].strip()

    polite_match = re.match(
        r"^(?:por favor,\s*)?(?:raizito,\s*)?"
        r"(?:cria|crie|criar|adiciona|adicione|adicionar|configura|configure)\s+"
        r"(?:um\s+)?lembrete\s+(?:para|de)?\s*(.+)$",
        stripped, flags=re.IGNORECASE,
    )
    if polite_match: return polite_match.group(1).strip()

    reminder_match = re.match(
        r"^(?:por favor,\s*)?(?:raizito,\s*)?"
        r"(?:me\s+lembra|me\s+lembre|lembra-me|lembre-me|me\s+avisa|me\s+avise|avisa-me|avise-me)\s+"
        r"(?:(?:de|para|pra)\s+)?(.+)$",
        stripped, flags=re.IGNORECASE,
    )
    return reminder_match.group(1).strip() if reminder_match else None

def parse_task_payload(text):
    due_date = _parse_due_date(text)
    due_time = _parse_due_time(text)
    priority = _parse_priority(text)
    category = _parse_category(text)
    recurrence = _parse_recurrence(text)
    reminder_at = _parse_reminder_at(text, due_date, due_time)
    if reminder_at and not due_date:
        reminder_dt = parse_local_datetime(reminder_at)
        if reminder_dt:
            due_date = reminder_dt.date()
            due_time = reminder_dt.time().replace(second=0, microsecond=0)
    title = _clean_task_title(text)

    return {
        "title": title,
        "due_date": due_date.isoformat() if due_date else None,
        "due_time": due_time.isoformat(timespec="minutes") if due_time else None,
        "priority": priority,
        "category": category,
        "recurrence": recurrence,
        "reminder_at": reminder_at,
    }

def parse_task_update_payload(update_text, full_text=None, prefix=""):
    source_text = (full_text or update_text).strip()
    lowered = source_text.lower()
    updates = {}
    payload = parse_task_payload(update_text or source_text)

    if payload.get("due_date"): updates["due_date"] = payload["due_date"]
    if payload.get("due_time"): updates["due_time"] = payload["due_time"]
    if payload.get("reminder_at"): updates["reminder_at"] = payload["reminder_at"]
    if payload.get("category"): updates["category"] = payload["category"]
    if payload.get("recurrence"): updates["recurrence"] = payload["recurrence"]
    if bool(re.search(r"\b(prioridade|p1|p2|p3|urgente|alta|media|média|normal|baixa)\b", source_text.lower())):
        updates["priority"] = payload["priority"]

    if re.search(r"\b(?:sem|remover|remove|tirar|tire|limpar|limpe)\s+(?:prazo|data|vencimento)\b", lowered):
        updates["due_date"] = None
        updates["due_time"] = None
    if re.search(r"\b(?:sem|remover|remove|tirar|tire|limpar|limpe)\s+(?:horario|horário|hora)\b", lowered):
        updates["due_time"] = None
    if re.search(r"\b(?:sem|remover|remove|tirar|tire|limpar|limpe)\s+(?:lembrete|alerta|aviso)\b", lowered):
        updates["reminder_at"] = None
    if re.search(r"\b(?:sem|remover|remove|tirar|tire|limpar|limpe)\s+(?:categoria|tag)\b", lowered):
        updates["category"] = None
    if re.search(r"\b(?:sem|remover|remove|tirar|tire|limpar|limpe)\s+(?:recorrencia|recorrência|repeticao|repetição)\b", lowered):
        updates["recurrence"] = None

    title_text = _strip_task_metadata(update_text or "")
    if title_text and title_text.lower() not in {"alta", "media", "média", "normal", "baixa", "p1", "p2", "p3"}:
        updates["title"] = title_text

    return updates

# --- Formatting ---

def format_task_due(task):
    due_date = task.get("due_date")
    due_time = task.get("due_time")
    if not due_date: return "Sem prazo"
    try: formatted = date.fromisoformat(due_date).strftime("%d/%m/%Y")
    except ValueError: formatted = due_date
    if due_time: formatted += f" às {due_time}"
    return formatted

def format_task_card(task):
    header_icon = "✅" if task["is_completed"] else ("⏰" if task.get("reminder_at") else "📝")
    priority_label = TASK_PRIORITY_LABELS.get((task.get("priority") or "normal").lower(), "⚪ Normal")
    lines = [
        f"{header_icon} #{task['id']} · {task['title']}",
        f"   Status: {'✅ Concluída' if task['is_completed'] else '🟡 Pendente'}",
        f"   📅 Prazo: {format_task_due(task)}",
        f"   🚦 Prioridade: {priority_label}",
    ]
    if task.get("category"): lines.append(f"   🏷️ Categoria: {task['category']}")
    if task.get("recurrence"):
        lines.append(f"   🔁 Recorrência: {TASK_RECURRENCE_LABELS.get(task['recurrence'], task['recurrence'])}")
    if task.get("reminder_at"):
        parsed = parse_local_datetime(task["reminder_at"])
        lines.append(f"   ⏰ Lembrete: {parsed.strftime('%d/%m/%Y às %H:%M') if parsed else task['reminder_at']}")
    return "\n".join(lines)

def format_task_summary_line(task):
    parts = [
        f"#{task['id']} {task['title']}",
        f"📅 {format_task_due(task)}",
        f"Prioridade: {TASK_PRIORITY_LABELS.get((task.get('priority') or 'normal').lower(), '⚪ Normal')}",
    ]
    if task.get("category"): parts.append(f"🏷️ {task['category']}")
    if task.get("reminder_at"):
        parsed = parse_local_datetime(task["reminder_at"])
        parts.append(f"⏰ {parsed.strftime('%d/%m/%Y %H:%M') if parsed else task['reminder_at']}")
    return " · ".join(parts)

def _task_list_title(task_filter="pending", category=None, require_reminder=False):
    title = "Lembretes" if require_reminder else "Tarefas"
    if task_filter != "pending": title += f" ({task_filter})"
    if category: title += f" #{category}"
    return title

def _task_created_message(task_id, payload):
    details = [
        f"✅ Tarefa criada",
        f"🆔 ID: #{task_id}",
        f"📝 Título: {payload['title']}",
    ]
    due_str = format_task_due(payload)
    if due_str != "Sem prazo": details.append(f"📅 Prazo: {due_str}")
    details.append(f"🚦 Prioridade: {TASK_PRIORITY_LABELS.get(payload['priority'], payload['priority'])}")
    if payload.get("category"): details.append(f"🏷️ Categoria: {payload['category']}")
    if payload.get("recurrence"): details.append(f"🔁 Recorrência: {TASK_RECURRENCE_LABELS.get(payload['recurrence'], payload['recurrence'])}")
    if payload.get("reminder_at"):
        parsed = parse_local_datetime(payload["reminder_at"])
        details.append(f"⏰ Lembrete: {parsed.strftime('%d/%m/%Y %H:%M') if parsed else payload['reminder_at']}")
    return "\n".join(details)

def format_tasks(tasks, title="Tarefas"):
    if not tasks: return f"📭 {title}\nNenhum item encontrado."
    lines = [f"📋 {title} · {len(tasks)} item(ns)"]
    for task in tasks:
        lines.append("")
        lines.append(format_task_card(task))
    return "\n".join(lines)

# --- Service Wrappers ---

def handle_create_task(user_id, text):
    payload = parse_task_payload(text)
    task_id = db_add_task(user_id, **payload)
    return task_id, payload

def handle_list_tasks(user_id, task_filter="pending", category=None, require_reminder=False):
    return db_get_tasks(user_id, task_filter=task_filter, category=category, require_reminder=require_reminder)

def handle_complete_task(user_id, task_id):
    return db_complete_task(task_id, user_id)

def handle_delete_task(user_id, task_id):
    return db_delete_task(task_id, user_id)

def handle_edit_task(user_id, task_id, update_text):
    updates = parse_task_update_payload(update_text)
    if not updates: return None
    return db_update_task(task_id, user_id, **updates)
