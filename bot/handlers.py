import json
import os
import re
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
from bot.ai_service import get_gemini_response, analyze_image, transcribe_audio
from bot.db import (
    add_internal_event,
    add_pending_calendar_event,
    add_email_draft,
    add_memory,
    add_task,
    cancel_internal_event,
    clear_memories,
    complete_task_with_recurrence,
    confirm_mission_step,
    create_mission,
    delete_pending_calendar_event,
    delete_task,
    delete_memory,
    get_email_draft,
    get_email_drafts,
    get_mission,
    get_internal_event,
    get_internal_events_between,
    get_pending_calendar_event,
    get_conversation_history,
    get_due_internal_event_reminders,
    get_due_task_reminders,
    get_knowledge_backend,
    get_memories,
    get_tasks,
    get_user_settings,
    get_users_for_daily_summary,
    get_users_with_meeting_reminders,
    list_missions,
    list_internal_events,
    clear_knowledge_source,
    count_knowledge_items,
    log_conversation,
    mark_calendar_event_reminded,
    mark_internal_event_reminded,
    mark_task_reminded,
    search_knowledge,
    save_mission_report,
    update_email_draft_status,
    update_mission_status,
    update_mission_step,
    update_task,
    upsert_user_settings,
    upsert_knowledge_item,
)
from bot.rag import chunk_text
from bot.time_utils import app_timezone, app_timezone_name, local_date, local_now, parse_local_datetime
from bot.web_search import google_search
from bot.external_integration import external_client
from bot.google_services import (
    create_calendar_event,
    format_calendar_events,
    get_document_content,
    get_drive_files,
    get_events_between,
    get_email_metadata,
    get_recent_emails,
    list_recent_emails,
    list_drive_files,
    list_events_for_day,
    list_upcoming_events,
    get_document_metadata,
)

MEMORY_PREFIXES = (
    "lembre que ",
    "lembra que ",
    "lembre-se que ",
    "memorize ",
    "guarde que ",
    "guarda que ",
    "salve na memoria ",
    "salve na memória ",
)

MEMORY_LIST_REQUESTS = (
    "o que voce lembra de mim?",
    "o que você lembra de mim?",
    "o que voce lembra?",
    "o que você lembra?",
    "minhas memorias",
    "minhas memórias",
    "quais memorias voce tem?",
    "quais memórias você tem?",
)

TASK_PREFIXES = (
    "crie uma tarefa ",
    "criar tarefa ",
    "adicione uma tarefa ",
    "adicionar tarefa ",
    "nova tarefa ",
    "tarefa: ",
    "crie um lembrete para ",
    "crie um lembrete de ",
    "crie um lembrete ",
    "criar lembrete para ",
    "criar lembrete de ",
    "criar lembrete ",
    "adicione um lembrete para ",
    "adicione um lembrete de ",
    "adicione um lembrete ",
    "adicionar lembrete para ",
    "adicionar lembrete de ",
    "adicionar lembrete ",
    "novo lembrete para ",
    "novo lembrete de ",
    "novo lembrete ",
    "lembrete: ",
    "lembrete para ",
    "lembrete de ",
    "me avise para ",
    "me avise de ",
    "me avise pra ",
    "avise-me para ",
    "avise-me de ",
    "me lembre de ",
    "me lembre para ",
    "me lembre pra ",
    "me lembra de ",
    "me lembra para ",
    "me lembra pra ",
    "lembre-me de ",
    "lembre-me para ",
    "lembre-me pra ",
    "lembra-me de ",
    "lembra-me para ",
    "lembra-me pra ",
    "me lembrar de ",
    "anote uma tarefa ",
    "anotar tarefa ",
)

EVENT_PREFIXES = (
    "crie um evento ",
    "criar evento ",
    "adicione um evento ",
    "adicionar evento ",
    "evento: ",
    "crie uma reuniao ",
    "crie uma reunião ",
    "criar reuniao ",
    "criar reunião ",
    "adicione uma reuniao ",
    "adicione uma reunião ",
    "adicionar reuniao ",
    "adicionar reunião ",
    "reuniao: ",
    "reunião: ",
    "crie um compromisso ",
    "criar compromisso ",
    "adicione um compromisso ",
    "adicionar compromisso ",
    "compromisso: ",
    "agende ",
    "marque ",
    "marcar ",
    "coloque na agenda ",
)

MISSION_PREFIXES = (
    "missao: ",
    "missão: ",
    "meta: ",
    "modo agente: ",
    "crie uma missao ",
    "crie uma missão ",
    "nova missao ",
    "nova missão ",
    "planeje uma missao ",
    "planeje uma missão ",
)

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

EVENT_FILTER_ALIASES = {
    "hoje": "today",
    "today": "today",
    "semana": "week",
    "week": "week",
    "proximos": "upcoming",
    "próximos": "upcoming",
    "upcoming": "upcoming",
    "futuros": "upcoming",
    "todos": "all",
    "todas": "all",
    "all": "all",
    "cancelados": "cancelled",
    "cancelled": "cancelled",
    "passados": "past",
    "past": "past",
}

MISSION_STATUS_ALIASES = {
    "ativas": "active",
    "ativa": "active",
    "active": "active",
    "pausadas": "paused",
    "paused": "paused",
    "concluidas": "completed",
    "concluídas": "completed",
    "completed": "completed",
    "arquivadas": "archived",
    "archived": "archived",
    "todas": "all",
    "all": "all",
}

MISSION_STEP_ACTIONS = {
    "start": "in_progress",
    "iniciar": "in_progress",
    "comecar": "in_progress",
    "começar": "in_progress",
    "doing": "in_progress",
    "done": "done",
    "concluir": "done",
    "concluido": "done",
    "concluído": "done",
    "ok": "done",
    "block": "blocked",
    "bloquear": "blocked",
    "bloqueado": "blocked",
    "skip": "skipped",
    "pular": "skipped",
    "ignorar": "skipped",
    "todo": "pending",
    "pendente": "pending",
    "reabrir": "pending",
}

MISSION_SENSITIVE_TERMS = (
    "enviar email",
    "enviar e-mail",
    "mandar email",
    "mandar e-mail",
    "responder email",
    "responder e-mail",
    "criar evento",
    "marcar reuniao",
    "marcar reunião",
    "agendar",
    "apagar",
    "deletar",
    "excluir",
    "remover",
    "arquivar",
    "pagar",
    "pagamento",
    "comprar",
    "contratar",
    "cancelar",
    "transferir",
    "publicar",
    "enviar proposta",
    "assinar",
    "alterar",
)

DOC_FILES = (
    "README.md",
    "SUPER_ASSISTANT_PLAN.md",
    "GOOGLE_APIS_SETUP.md",
    "DEPLOY.md",
)

TASK_PRIORITY_LABELS = {
    "alta": "🔴 Alta",
    "media": "🟠 Média",
    "normal": "⚪ Normal",
    "baixa": "🟢 Baixa",
}

TASK_RECURRENCE_LABELS = {
    "diaria": "Diária",
    "semanal": "Semanal",
    "mensal": "Mensal",
}

DEFAULT_ASSISTANT_PERSONA = """
Persona fixa do assistente:
Voce e o Raizito, um assistente pessoal digital com postura de assistente humano
experiente. Seu trabalho e ajudar o usuario a organizar rotina, tarefas, agenda,
informacoes e decisoes praticas com naturalidade, discricao e bom senso.

Estilo de conversa:
- Responda em portugues do Brasil, com tom humano, calmo, direto e prestativo.
- Fale como alguem que acompanha o usuario no dia a dia: seja contextual,
  objetivo e cordial, sem soar robotico, promocional ou exageradamente formal.
- Comece pela resposta util; use explicacoes curtas e listas apenas quando
  ajudarem a organizar a informacao.
- Se faltar uma informacao essencial, faca uma unica pergunta objetiva. Se for
  possivel assumir algo com baixo risco, siga em frente e diga a premissa.
- Use as memorias e o contexto recuperado de forma natural, sem mencionar
  sistemas internos, RAG, embeddings ou banco de dados.
- Quando o usuario pedir algo que pode virar tarefa, lembrete, evento, memoria
  ou missao, oriente ou confirme com clareza o que foi entendido.
- Nao finja ser humano, nao invente acesso a sistemas e nao diga que executou
  acoes externas sem confirmacao real do bot.
- Se nao souber, diga isso de forma simples e proponha o proximo passo.
""".strip()

ASSISTANT_PERSONA = (os.getenv("ASSISTANT_PERSONA") or DEFAULT_ASSISTANT_PERSONA).strip()

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

WEEKDAYS = {
    "segunda": 0,
    "terca": 1,
    "terça": 1,
    "quarta": 2,
    "quinta": 3,
    "sexta": 4,
    "sabado": 5,
    "sábado": 5,
    "domingo": 6,
}

WEEKDAY_LABELS = (
    "segunda-feira",
    "terca-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sabado",
    "domingo",
)

RELATIVE_AMOUNT_PATTERN = r"\d{1,3}|um|uma|uns|umas|alguns|algumas|poucos|poucas"


def _extract_memory_text(text):
    stripped = text.strip()
    lowered = stripped.lower()
    for prefix in MEMORY_PREFIXES:
        if lowered.startswith(prefix):
            return stripped[len(prefix):].strip()
    return None


def _extract_task_text(text):
    stripped = text.strip()
    lowered = stripped.lower()
    for prefix in TASK_PREFIXES:
        if lowered.startswith(prefix):
            return stripped[len(prefix):].strip()

    polite_match = re.match(
        r"^(?:por favor,\s*)?(?:raizito,\s*)?"
        r"(?:cria|crie|criar|adiciona|adicione|adicionar|configura|configure)\s+"
        r"(?:um\s+)?lembrete\s+(?:para|de)?\s*(.+)$",
        stripped,
        flags=re.IGNORECASE,
    )
    if polite_match:
        return polite_match.group(1).strip()

    reminder_match = re.match(
        r"^(?:por favor,\s*)?(?:raizito,\s*)?"
        r"(?:me\s+lembra|me\s+lembre|lembra-me|lembre-me|me\s+avisa|me\s+avise|avisa-me|avise-me)\s+"
        r"(?:(?:de|para|pra)\s+)?(.+)$",
        stripped,
        flags=re.IGNORECASE,
    )
    if reminder_match:
        return reminder_match.group(1).strip()
    return None


def _extract_task_id_match(text):
    return re.search(r"\b(?:tarefa|tarefas|lembrete|lembretes)\s*#?(\d+)\b|#(\d+)\b", text, re.IGNORECASE)


def _extract_task_id(text):
    match = _extract_task_id_match(text)
    if not match:
        return None
    return int(match.group(1) or match.group(2))


def _parse_task_filter_and_category(text):
    lowered = text.lower()
    task_filter = "pending"
    category = None
    require_reminder = bool(re.search(r"\b(lembretes?|reminders?)\b", lowered))

    for raw in re.findall(r"#([\wÀ-ÿ-]+)|\b(?:categoria|cat)[:=]\s*([\wÀ-ÿ-]+)", text, re.IGNORECASE):
        category = (raw[0] or raw[1]).lower()

    for alias, normalized in TASK_FILTER_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            task_filter = normalized
            break

    if re.search(r"\b(pendentes?|abertas?|a fazer)\b", lowered):
        task_filter = "pending"
    if re.search(r"\b(concluidas|concluídas|finalizadas|feitas)\b", lowered):
        task_filter = "completed"

    if re.search(r"\b(tarefas?|tasks?)\s+com\s+(?:lembrete|alerta|aviso)\b", lowered):
        require_reminder = True

    return task_filter, category, require_reminder


def _is_task_list_request(text):
    lowered = text.strip().lower()
    if lowered in {"minhas tarefas", "meus lembretes", "tarefas", "lembretes"}:
        return True
    if re.search(r"\bo que (?:eu )?tenho (?:para|pra) fazer\b", lowered):
        return True
    if not re.search(r"\b(tarefas?|lembretes?)\b", lowered):
        return False
    return bool(re.match(
        r"^(?:por favor,\s*)?(?:raizito,\s*)?"
        r"(?:lista|listar|liste|mostra|mostrar|mostre|ver|veja|quais|consultar|consulta)\b",
        lowered,
    ))


def _is_task_complete_request(text):
    lowered = text.lower()
    if not _extract_task_id(lowered) or not re.search(r"\b(tarefas?|lembretes?)\b", lowered):
        return False
    return bool(re.search(
        r"\b(concluir|conclua|concluido|concluida|concluído|concluída|complete|completar|feito|feita|"
        r"finalizar|finalize|finalizada|terminar|terminei|marcar|marque|dar baixa)\b",
        lowered,
    ))


def _is_task_delete_request(text):
    lowered = text.lower()
    if not _extract_task_id(lowered) or not re.search(r"\b(tarefas?|lembretes?)\b", lowered):
        return False
    return bool(re.search(
        r"\b(excluir|exclua|apagar|apague|deletar|delete|remover|remova|cancelar|cancele)\b",
        lowered,
    ))


def _extract_task_update_request(text):
    match = _extract_task_id_match(text)
    if not match:
        return None

    lowered = text.lower()
    if not re.search(r"\b(editar|edite|alterar|altere|mudar|mude|atualizar|atualize|renomear|renomeie|modificar|modifique)\b", lowered):
        return None
    if not re.search(r"\b(tarefas?|lembretes?)\b", lowered):
        return None

    update_text = text[match.end():].strip()
    update_text = re.sub(r"^(?:para|pra|como|com|:|-|,)\s+", "", update_text, flags=re.IGNORECASE).strip()
    prefix = text[:match.start()]
    return {
        "task_id": int(match.group(1) or match.group(2)),
        "update_text": update_text,
        "prefix": prefix,
        "full_text": text,
    }


def _extract_event_text(text):
    stripped = text.strip()
    lowered = stripped.lower()
    for prefix in EVENT_PREFIXES:
        if lowered.startswith(prefix):
            content = stripped[len(prefix):].strip()
            if any(noun in prefix for noun in ("reuniao", "reunião")):
                return f"reuniao {content}".strip()
            if "compromisso" in prefix:
                return f"compromisso {content}".strip()
            if "evento" in prefix:
                return f"evento {content}".strip()
            return content

    polite_match = re.match(
        r"^(?:por favor,\s*)?(?:raizito,\s*)?"
        r"(?:cria|crie|criar|adiciona|adicione|adicionar|agenda|agende|agendar|marca|marque|marcar)\s+"
        r"(?:um|uma)?\s*(evento|reuniao|reunião|compromisso)\s*(.+)$",
        stripped,
        flags=re.IGNORECASE,
    )
    if polite_match:
        noun = polite_match.group(1).replace("ã", "a")
        return f"{noun} {polite_match.group(2).strip()}".strip()
    return None


def _extract_mission_goal(text):
    stripped = text.strip()
    lowered = stripped.lower()
    for prefix in MISSION_PREFIXES:
        if lowered.startswith(prefix):
            return stripped[len(prefix):].strip()
    return None


def _calendar_backend():
    backend = (os.getenv("CALENDAR_BACKEND") or "internal").strip().lower()
    aliases = {
        "local": "internal",
        "interno": "internal",
        "agenda_interna": "internal",
        "calendar": "google",
        "google_calendar": "google",
        "gcal": "google",
        "ambos": "both",
    }
    return aliases.get(backend, backend if backend in {"internal", "google", "both"} else "internal")


def _calendar_uses_internal():
    return _calendar_backend() in {"internal", "both"}


def _calendar_uses_google():
    return _calendar_backend() in {"google", "both"}


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
        if year < 100:
            year += 2000
        try:
            due = date(year, month, day)
        except ValueError:
            return None
        if not year_text and due < today:
            due = date(today.year + 1, month, day)
        return due

    for name, weekday in WEEKDAYS.items():
        if re.search(rf"\b{name}\b", lowered):
            return _next_weekday(weekday)

    return None


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


def _parse_priority(text):
    lowered = text.lower()
    if re.search(r"(!alta|\balta\b|\burgente\b|\bprioridade[:=]\s*alta\b|\bp1\b)", lowered):
        return "alta"
    if re.search(r"(\bmedia\b|\bmédia\b|\bprioridade[:=]\s*(media|média)\b|\bp2\b)", lowered):
        return "media"
    if re.search(r"(\bbaixa\b|\bprioridade[:=]\s*baixa\b|\bp3\b)", lowered):
        return "baixa"
    if re.search(r"\bprioridade[:=]?\s*normal\b|\bnormal\b", lowered):
        return "normal"
    return "normal"


def _mentions_priority(text):
    return bool(re.search(
        r"\b(prioridade|p1|p2|p3|urgente|alta|media|média|normal|baixa)\b",
        text.lower(),
    ))


def _parse_category(text):
    tag_match = re.search(r"(?:^|\s)#([\wÀ-ÿ-]+)", text)
    if tag_match:
        return tag_match.group(1).lower()

    category_match = re.search(r"\b(?:categoria|cat)[:=]\s*([\wÀ-ÿ-]+)", text, re.IGNORECASE)
    if category_match:
        return category_match.group(1).lower()
    return None


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
        return datetime.combine(due_date, due_time, tzinfo=app_timezone()).isoformat(timespec="minutes")

    if due_date and re.search(r"\b(lembrete|lembrar|me lembre|lembre-me)\b", lowered):
        return datetime.combine(due_date, time(9, 0), tzinfo=app_timezone()).isoformat(timespec="minutes")

    return None


def _task_title_cleanup_patterns():
    return [
        r"\b(?:prioridade|cat|categoria)[:=]\s*[\wÀ-ÿ-]+\b",
        r"(?:^|\s)#[\wÀ-ÿ-]+",
        r"\b(!alta|p1|p2|p3|urgente|prioridade alta|prioridade media|prioridade média|prioridade baixa)\b",
        r"\b(todo dia|todos os dias|diaria|diária|diariamente|toda semana|semanal|semanalmente|todo mes|todo mês|mensal|mensalmente)\b",
        r"\b(hoje|amanha|amanhã|depois de amanha|depois de amanhã)\b",
        rf"\b(?:em|daqui\s+a?)\s+(?:{RELATIVE_AMOUNT_PATTERN})\s+dias?\b",
        rf"\b(?:lembrete|lembrar|avisar|me\s+lembre|me\s+lembra|lembre-me|lembra-me)?\s*"
        rf"(?:em|daqui\s+a?)\s+(?:{RELATIVE_AMOUNT_PATTERN})\s*(?:minutos?|min|horas?|h)\b",
        rf"\b(?:{RELATIVE_AMOUNT_PATTERN})\s*(?:minutos?|min|horas?|h)\s+"
        r"(?:a partir de agora|de agora)\b",
        r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b",
        r"\b(?:segunda|terca|terça|quarta|quinta|sexta|sabado|sábado|domingo)\b",
        r"\b(?:as|às|a|@)\s*\d{1,2}(?:[:h]\d{0,2})?\b",
        r"\b\d{1,2}h\d{0,2}\b",
        r"\b\d{1,2}\s*horas?\b",
        r"\b(meio dia|meio-dia|meia noite|meia-noite)\b",
        r"\b(da tarde|tarde|da noite|noite|da madrugada|madrugada|da manha|da manhã)\b",
    ]


def _strip_task_metadata(text):
    cleaned = text.strip()
    cleaned = re.sub(r"^(?:titulo|título|nome|texto|descricao|descrição)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    for pattern in _task_title_cleanup_patterns():
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip(" -,.")


def _clean_task_title(text):
    return _strip_task_metadata(text) or text.strip()


def _parse_task_payload(text):
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
            due_time = reminder_dt.time().replace(tzinfo=None, second=0, microsecond=0)
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


def _parse_task_update_payload(update_text, full_text=None, prefix=""):
    source_text = (full_text or update_text).strip()
    lowered = source_text.lower()
    update_lowered = (update_text or "").lower()
    updates = {}
    payload = _parse_task_payload(update_text or source_text)

    if payload.get("due_date"):
        updates["due_date"] = payload["due_date"]
    if payload.get("due_time"):
        updates["due_time"] = payload["due_time"]
    if payload.get("reminder_at"):
        updates["reminder_at"] = payload["reminder_at"]
    if payload.get("category"):
        updates["category"] = payload["category"]
    if payload.get("recurrence"):
        updates["recurrence"] = payload["recurrence"]
    if _mentions_priority(source_text):
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

    prefix_has_field = bool(re.search(
        r"\b(prazo|data|vencimento|horario|horário|hora|prioridade|categoria|tag|lembrete|alerta|aviso|recorrencia|recorrência)\b",
        prefix.lower(),
    ))
    title_marker = bool(re.search(r"\b(titulo|título|nome|texto|descricao|descrição|renomear|renomeie)\b", lowered))
    title_text = _strip_task_metadata(update_text)
    title_text = re.sub(
        r"\b(?:prazo|data|vencimento|horario|horário|hora|prioridade|categoria|tag|lembrete|alerta|aviso|recorrencia|recorrência)\b",
        " ",
        title_text,
        flags=re.IGNORECASE,
    )
    title_text = re.sub(r"\s+", " ", title_text).strip(" -,.")
    title_is_only_priority = title_text.lower() in {"alta", "media", "média", "normal", "baixa", "p1", "p2", "p3"}
    title_is_clear_directive = bool(re.match(r"^(?:sem|remover|remove|tirar|tire|limpar|limpe)\b", update_lowered))
    if title_text and not title_is_only_priority and not title_is_clear_directive and (title_marker or not prefix_has_field):
        updates["title"] = title_text

    return updates


def _format_task_due(task):
    due_date = task.get("due_date")
    due_time = task.get("due_time")
    if not due_date:
        return "Sem prazo"

    try:
        formatted = date.fromisoformat(due_date).strftime("%d/%m/%Y")
    except ValueError:
        formatted = due_date

    if due_time:
        formatted += f" às {due_time}"
    return formatted


def _format_payload_due(payload):
    due_date = payload.get("due_date")
    due_time = payload.get("due_time")
    if not due_date:
        return None
    try:
        formatted = date.fromisoformat(due_date).strftime("%d/%m/%Y")
    except ValueError:
        formatted = due_date
    if due_time:
        formatted += f" às {due_time}"
    return formatted


def _format_datetime_value(value):
    parsed = parse_local_datetime(value)
    if parsed:
        return parsed.strftime("%d/%m/%Y às %H:%M")
    return value


def _format_task_reminder(task):
    reminder_at = task.get("reminder_at")
    if not reminder_at:
        return None
    return _format_datetime_value(reminder_at)


def _format_task_priority(task):
    priority = (task.get("priority") or "normal").lower()
    return TASK_PRIORITY_LABELS.get(priority, priority.capitalize())


def _format_task_status(task):
    return "✅ Concluída" if task["is_completed"] else "🟡 Pendente"


def _format_task_summary_line(task):
    parts = [
        f"#{task['id']} {task['title']}",
        f"📅 {_format_task_due(task)}",
        f"Prioridade: {_format_task_priority(task)}",
    ]
    if task.get("category"):
        parts.append(f"🏷️ {task['category']}")
    if task.get("reminder_at"):
        parts.append(f"⏰ {_format_task_reminder(task)}")
    return " · ".join(parts)


def _format_task_card(task):
    header_icon = "✅" if task["is_completed"] else ("⏰" if task.get("reminder_at") else "📝")
    lines = [
        f"{header_icon} #{task['id']} · {task['title']}",
        f"   Status: {_format_task_status(task)}",
        f"   📅 Prazo: {_format_task_due(task)}",
        f"   🚦 Prioridade: {_format_task_priority(task)}",
    ]
    if task.get("category"):
        lines.append(f"   🏷️ Categoria: {task['category']}")
    if task.get("recurrence"):
        recurrence = TASK_RECURRENCE_LABELS.get(task["recurrence"], task["recurrence"])
        lines.append(f"   🔁 Recorrência: {recurrence}")
    if task.get("reminder_at"):
        lines.append(f"   ⏰ Lembrete: {_format_task_reminder(task)}")
    return "\n".join(lines)


def _format_task_line(task):
    return _format_task_card(task)


def _format_tasks(tasks, title="Tarefas"):
    if not tasks:
        return f"📭 {title}\nNenhum item encontrado."

    lines = [f"📋 {title} · {len(tasks)} item(ns)"]
    for task in tasks:
        lines.append("")
        lines.append(_format_task_card(task))
    return "\n".join(lines)


def _task_list_title(task_filter="pending", category=None, require_reminder=False):
    title = "Lembretes" if require_reminder else "Tarefas"
    if task_filter != "pending":
        title += f" ({task_filter})"
    if category:
        title += f" #{category}"
    return title


def _task_created_message(task_id, payload):
    details = [
        f"✅ Tarefa criada",
        f"🆔 ID: #{task_id}",
        f"📝 Título: {payload['title']}",
    ]
    if payload.get("due_date"):
        details.append(f"📅 Prazo: {_format_payload_due(payload)}")
    details.append(f"🚦 Prioridade: {TASK_PRIORITY_LABELS.get(payload['priority'], payload['priority'])}")
    if payload.get("category"):
        details.append(f"🏷️ Categoria: {payload['category']}")
    if payload.get("recurrence"):
        recurrence = TASK_RECURRENCE_LABELS.get(payload["recurrence"], payload["recurrence"])
        details.append(f"🔁 Recorrência: {recurrence}")
    if payload.get("reminder_at"):
        details.append(f"⏰ Lembrete: {_format_datetime_value(payload['reminder_at'])}")
    return "\n".join(details)


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
        reminder_match = re.search(
            r"\b(\d{1,3})\s*(minutos?|min|horas?|h)\s+antes\b",
            lowered,
        )
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


def _parse_event_location(text):
    return _extract_event_field(text, ("local", "lugar", "onde"))


def _parse_event_description(text):
    description = _extract_event_field(text, ("desc", "descricao", "descrição", "nota", "obs"))
    if not description:
        return None
    return EMAIL_RE.sub(" ", description).strip(" -,.")


def _parse_event_attendees(text):
    return sorted(set(EMAIL_RE.findall(text)))


def _clean_event_title(text):
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
    return {
        "summary": _clean_event_title(text),
        "start_at": start_at,
        "end_at": end_at,
        "duration_minutes": duration_minutes,
        "description": _parse_event_description(text),
        "location": _parse_event_location(text),
        "attendees": _parse_event_attendees(text),
        "reminder_minutes": _parse_event_reminder_minutes(text),
    }


def _parse_event_datetime(value):
    return parse_local_datetime(value)


def _event_time_range(event):
    start_value = event.get("start_at") or event.get("start", {}).get("dateTime")
    end_value = event.get("end_at") or event.get("end", {}).get("dateTime")
    if not start_value or not end_value:
        return None
    start_at = _parse_event_datetime(start_value)
    end_at = _parse_event_datetime(end_value)
    if not start_at or not end_at:
        return None
    return start_at, end_at


def _find_calendar_conflicts(start_at, end_at):
    events = get_events_between(start_at - timedelta(minutes=1), end_at + timedelta(minutes=1), max_results=20)
    conflicts = []
    for event in events:
        event_range = _event_time_range(event)
        if not event_range:
            continue
        event_start, event_end = event_range
        if event_start < end_at and start_at < event_end:
            conflicts.append(event)
    return conflicts


def _find_internal_conflicts(user_id, start_at, end_at):
    return get_internal_events_between(
        user_id,
        start_at - timedelta(minutes=1),
        end_at + timedelta(minutes=1),
        limit=50,
    )


def _format_conflicts(conflicts):
    if not conflicts:
        return None
    lines = ["Conflitos encontrados:"]
    for event in conflicts[:5]:
        event_range = _event_time_range(event)
        if not event_range:
            continue
        start_at, end_at = event_range
        lines.append(
            f"- {event.get('summary', '(Sem titulo)')} | "
            f"{start_at.strftime('%d/%m %H:%M')} ate {end_at.strftime('%H:%M')}"
        )
    return "\n".join(lines)


def _suggest_event_slots(start_at, duration_minutes, conflicts, count=3):
    cursor = start_at
    sorted_conflicts = sorted(
        [event_range for event in conflicts if (event_range := _event_time_range(event))],
        key=lambda item: item[0],
    )
    suggestions = []
    while len(suggestions) < count:
        candidate_end = cursor + timedelta(minutes=duration_minutes)
        overlap = None
        for conflict_start, conflict_end in sorted_conflicts:
            if conflict_start < candidate_end and cursor < conflict_end:
                overlap = conflict_end
                break
        if overlap:
            cursor = overlap
            continue
        suggestions.append(cursor)
        cursor = cursor + timedelta(minutes=duration_minutes)
    return suggestions


def _event_knowledge_content(event):
    start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date")
    end = event.get("end", {}).get("dateTime") or event.get("end", {}).get("date")
    lines = [
        f"Evento: {event.get('summary', '(Sem titulo)')}",
        f"Inicio: {start}",
        f"Fim: {end}",
    ]
    if event.get("location"):
        lines.append(f"Local: {event['location']}")
    if event.get("description"):
        lines.append(f"Descricao: {event['description']}")
    attendees = event.get("attendees") or []
    if attendees:
        emails = [attendee.get("email") for attendee in attendees if attendee.get("email")]
        if emails:
            lines.append("Convidados: " + ", ".join(emails))
    return "\n".join(lines)


def _internal_event_knowledge_content(event):
    lines = [
        f"Evento interno: {event.get('summary', '(Sem titulo)')}",
        f"Inicio: {event.get('start_at')}",
        f"Fim: {event.get('end_at')}",
        f"Status: {event.get('status', 'scheduled')}",
    ]
    if event.get("location"):
        lines.append(f"Local: {event['location']}")
    if event.get("description"):
        lines.append(f"Descricao: {event['description']}")
    if event.get("attendees"):
        lines.append("Convidados: " + ", ".join(event["attendees"]))
    if event.get("reminder_minutes") is not None:
        lines.append(f"Alerta: {event['reminder_minutes']} minutos antes")
    return "\n".join(lines)


def _format_internal_event_line(event):
    start_at = _parse_event_datetime(event.get("start_at"))
    end_at = _parse_event_datetime(event.get("end_at"))
    if start_at and end_at:
        when = f"{start_at.strftime('%d/%m/%Y %H:%M')} ate {end_at.strftime('%H:%M')}"
    else:
        when = f"{event.get('start_at')} ate {event.get('end_at')}"
    parts = [
        f"{event['id']}. {event['summary']}",
        when,
        f"status: {event.get('status', 'scheduled')}",
    ]
    if event.get("location"):
        parts.append(f"local: {event['location']}")
    if event.get("reminder_minutes") is not None:
        parts.append(f"alerta: {event['reminder_minutes']} min antes")
    return " | ".join(parts)


def _format_internal_events(events, title="Agenda interna"):
    if not events:
        return "Nenhum evento encontrado na agenda interna."
    return "\n".join([f"{title}:"] + [_format_internal_event_line(event) for event in events])


def _format_internal_event_created(event):
    lines = [
        f"Evento interno criado. ID: {event['id']}",
        f"Titulo: {event['summary']}",
    ]
    start_at = _parse_event_datetime(event.get("start_at"))
    end_at = _parse_event_datetime(event.get("end_at"))
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


def _format_event_preview(pending_event):
    start_at = parse_local_datetime(pending_event["start_at"])
    end_at = parse_local_datetime(pending_event["end_at"])
    lines = [
        f"Evento pendente #{pending_event['id']}:",
        f"Titulo: {pending_event['summary']}",
        f"Inicio: {start_at.strftime('%d/%m/%Y %H:%M') if start_at else pending_event['start_at']}",
        f"Fim: {end_at.strftime('%d/%m/%Y %H:%M') if end_at else pending_event['end_at']}",
    ]
    if pending_event.get("location"):
        lines.append(f"Local: {pending_event['location']}")
    if pending_event.get("attendees"):
        lines.append("Convidados: " + ", ".join(pending_event["attendees"]))
    if pending_event.get("description"):
        lines.append(f"Descricao: {pending_event['description']}")
    lines.append(f"Confirme com /confirm_event {pending_event['id']} ou cancele com /cancel_event {pending_event['id']}")
    return "\n".join(lines)


def _is_sensitive_mission_action(text):
    lowered = (text or "").lower()
    return any(term in lowered for term in MISSION_SENSITIVE_TERMS)


def _fallback_mission_plan(goal):
    return (
        "Plano inicial criado localmente.",
        [
            {
                "title": "Definir resultado esperado",
                "details": f"Escrever o que precisa estar pronto para considerar a meta concluida: {goal}",
                "requires_confirmation": False,
            },
            {
                "title": "Levantar contexto e restricoes",
                "details": "Reunir informacoes, prazos, dependencias e riscos antes de agir.",
                "requires_confirmation": False,
            },
            {
                "title": "Executar a primeira acao concreta",
                "details": "Transformar o plano em uma entrega pequena e verificavel.",
                "requires_confirmation": _is_sensitive_mission_action(goal),
            },
            {
                "title": "Validar resultado",
                "details": "Conferir se a entrega atende a meta e registrar ajustes necessarios.",
                "requires_confirmation": False,
            },
            {
                "title": "Reportar progresso",
                "details": "Atualizar a missao com o que foi feito, bloqueios e proximo passo.",
                "requires_confirmation": False,
            },
        ],
    )


def _strip_json_fence(text):
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text or "", flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    return (text or "").strip()


def _boolish(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "sim", "on"}
    return bool(value)


def _parse_mission_plan_response(text, goal):
    candidates = [_strip_json_fence(text)]
    object_match = re.search(r"\{.*\}", text or "", flags=re.DOTALL)
    if object_match:
        candidates.append(object_match.group(0))
    array_match = re.search(r"\[.*\]", text or "", flags=re.DOTALL)
    if array_match:
        candidates.append(array_match.group(0))

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (TypeError, ValueError):
            continue

        summary = None
        raw_steps = parsed
        if isinstance(parsed, dict):
            summary = parsed.get("summary") or parsed.get("resumo")
            raw_steps = parsed.get("steps") or parsed.get("passos") or []
        if not isinstance(raw_steps, list):
            continue

        steps = []
        for item in raw_steps[:8]:
            if isinstance(item, dict):
                title = str(item.get("title") or item.get("titulo") or item.get("step") or "").strip()
                details = str(item.get("details") or item.get("detalhes") or item.get("description") or "").strip()
                requires_confirmation = _boolish(
                    item.get("requires_confirmation")
                    if "requires_confirmation" in item
                    else item.get("requer_confirmacao", item.get("confirmacao"))
                )
            else:
                title = str(item).strip()
                details = ""
                requires_confirmation = False

            combined = f"{title} {details}"
            if not title:
                continue
            steps.append({
                "title": title[:180],
                "details": details[:500] or None,
                "requires_confirmation": requires_confirmation or _is_sensitive_mission_action(combined),
            })

        if steps:
            return summary or "Plano criado pelo Gemini.", steps

    return _fallback_mission_plan(goal)


def _generate_mission_plan(user_id, goal):
    context = _build_assistant_context(user_id, goal)
    prompt_parts = [
        "Voce e um assistente pessoal em modo agente.",
        "Quebre a meta do usuario em 3 a 8 passos concretos, verificaveis e ordenados.",
        "Nao execute nenhuma acao externa. Apenas planeje.",
        "Marque requires_confirmation como true quando o passo envolver enviar mensagens/e-mails, criar eventos, apagar dados, pagar, comprar, publicar, alterar sistemas externos ou qualquer acao sensivel.",
        "Responda somente JSON valido neste formato:",
        '{"summary":"resumo curto","steps":[{"title":"passo","details":"detalhes","requires_confirmation":false}]}',
    ]
    if context:
        prompt_parts.append(f"Contexto auxiliar:\n{context}")
    prompt_parts.append(f"Meta do usuario:\n{goal}")

    response = get_gemini_response("\n\n".join(prompt_parts))
    if response.startswith("Error") or response.startswith("⚠️"):
        return _fallback_mission_plan(goal)
    return _parse_mission_plan_response(response, goal)


def _mission_progress_counts(mission):
    steps = mission.get("steps", [])
    done = len([step for step in steps if step["status"] == "done"])
    skipped = len([step for step in steps if step["status"] == "skipped"])
    blocked = len([step for step in steps if step["status"] == "blocked"])
    total = len(steps)
    return done, skipped, blocked, total


def _format_mission_step(step):
    status = step["status"]
    marker = ""
    if step["requires_confirmation"] and not step.get("confirmed_at"):
        marker = " | requer confirmacao"
    elif step.get("confirmed_at"):
        marker = " | confirmado"

    details = f"\n   {step['details']}" if step.get("details") else ""
    checkpoint = f"\n   Checkpoint: {step['checkpoint_note']}" if step.get("checkpoint_note") else ""
    return f"{step['step_number']}. [{status}] {step['title']}{marker}{details}{checkpoint}"


def _format_mission_full(mission):
    done, skipped, blocked, total = _mission_progress_counts(mission)
    lines = [
        f"Missao #{mission['id']} [{mission['status']}]",
        f"Meta: {mission['goal']}",
    ]
    if mission.get("summary"):
        lines.append(f"Resumo: {mission['summary']}")
    lines.append(f"Progresso: {done}/{total} concluido(s), {skipped} pulado(s), {blocked} bloqueado(s).")
    lines.append(f"Passo atual: {mission.get('current_step') or '-'}")
    lines.append("")
    lines.append("Plano:")
    lines.extend(_format_mission_step(step) for step in mission.get("steps", []))

    checkpoints = mission.get("checkpoints") or []
    if checkpoints:
        lines.append("")
        lines.append("Ultimos checkpoints:")
        for checkpoint in checkpoints[:5]:
            step = f" passo {checkpoint['step_number']}" if checkpoint.get("step_number") else ""
            note = f": {checkpoint['note']}" if checkpoint.get("note") else ""
            lines.append(f"- {checkpoint['event_type']}{step}{note}")

    lines.append("")
    lines.append("Use /mission_step <missao> <passo> <start|done|block|skip> [nota].")
    lines.append("Passos sensiveis precisam de /mission_confirm <missao> <passo> antes de iniciar ou concluir.")
    return "\n".join(lines)


def _format_mission_list(missions):
    if not missions:
        return "Nenhuma missao encontrada."

    lines = ["Missoes:"]
    for mission in missions:
        lines.append(
            f"{mission['id']}. [{mission['status']}] {mission['goal']} "
            f"({mission.get('done_steps', 0)}/{mission.get('total_steps', 0)})"
        )
    return "\n".join(lines)


def _current_or_next_step(mission):
    steps = mission.get("steps", [])
    current_number = mission.get("current_step")
    for step in steps:
        if step["step_number"] == current_number and step["status"] not in {"done", "skipped"}:
            return step
    for step in steps:
        if step["status"] not in {"done", "skipped"}:
            return step
    return None


def _compact_mission_state(mission):
    lines = [
        f"Missao #{mission['id']}: {mission['goal']}",
        f"Status: {mission['status']}",
    ]
    if mission.get("summary"):
        lines.append(f"Resumo: {mission['summary']}")
    lines.append("Passos:")
    lines.extend(_format_mission_step(step) for step in mission.get("steps", []))
    return "\n".join(lines)


def _build_mission_report(mission):
    done, skipped, blocked, total = _mission_progress_counts(mission)
    next_step = _current_or_next_step(mission)
    fallback_lines = [
        f"Relatorio da missao #{mission['id']}",
        f"Progresso: {done}/{total} concluido(s), {skipped} pulado(s), {blocked} bloqueado(s).",
    ]
    if next_step:
        fallback_lines.append(f"Proximo passo: {next_step['step_number']}. {next_step['title']}")
        if next_step["requires_confirmation"] and not next_step.get("confirmed_at"):
            fallback_lines.append("Este proximo passo exige confirmacao antes de execucao.")
    else:
        fallback_lines.append("Nao ha proximos passos pendentes.")
    fallback = "\n".join(fallback_lines)

    prompt = (
        "Gere um relatorio curto em portugues do Brasil sobre esta missao.\n"
        "Inclua progresso, bloqueios, riscos e proximo passo. Nao invente acoes executadas.\n\n"
        f"{_compact_mission_state(mission)}"
    )
    response = get_gemini_response(prompt)
    if response.startswith("Error") or response.startswith("⚠️"):
        return fallback
    return response


async def _create_mission_from_goal(update, user_id, goal):
    if not goal:
        await update.message.reply_text("Uso: /mission <meta>")
        return

    summary, steps = _generate_mission_plan(user_id, goal)
    mission_id = create_mission(user_id, goal, steps, summary=summary)
    mission = get_mission(user_id, mission_id)
    await update.message.reply_text(_format_mission_full(mission))


async def _create_task_from_text(update, user_id, text):
    payload = _parse_task_payload(text)
    task_id = add_task(
        user_id,
        payload["title"],
        due_date=payload["due_date"],
        priority=payload["priority"],
        category=payload["category"],
        reminder_at=payload["reminder_at"],
        recurrence=payload["recurrence"],
        due_time=payload["due_time"],
    )
    await update.message.reply_text(_task_created_message(task_id, payload))


async def _reply_with_tasks(update, user_id, task_filter="pending", category=None, require_reminder=False):
    tasks = get_tasks(
        user_id,
        task_filter=task_filter,
        category=category,
        require_reminder=require_reminder,
    )
    await update.message.reply_text(_format_tasks(tasks, _task_list_title(task_filter, category, require_reminder)))


async def _edit_task_from_text(update, user_id, task_id, update_text, full_text=None, prefix=""):
    if not update_text and not full_text:
        await update.message.reply_text(
            "Uso: /task_edit <id> <alteracoes>. Ex: /task_edit 12 revisar proposta amanha as 9 prioridade:alta"
        )
        return

    updates = _parse_task_update_payload(update_text, full_text=full_text, prefix=prefix)
    if not updates:
        await update.message.reply_text(
            "Nao entendi o que alterar. Ex: /task_edit 12 prazo amanha as 9, prioridade:alta ou titulo: revisar proposta"
        )
        return

    task = update_task(task_id, user_id, **updates)
    if not task:
        await update.message.reply_text(f"⚠️ Tarefa #{task_id} nao encontrada.")
        return

    await update.message.reply_text("✅ Tarefa atualizada\n\n" + _format_task_card(task))


async def _delete_task_by_id(update, user_id, task_id):
    task = delete_task(task_id, user_id)
    if not task:
        await update.message.reply_text(f"⚠️ Tarefa #{task_id} nao encontrada.")
        return

    await update.message.reply_text(f"🗑️ Tarefa excluida\n🆔 ID: #{task_id}\n📝 {task['title']}")


async def _complete_task_by_id(update, user_id, task_id):
    result = complete_task_with_recurrence(task_id, user_id)
    if result["completed"]:
        if result["next_task_id"]:
            await update.message.reply_text(
                f"✅ Tarefa #{task_id} concluida.\n🔁 Proxima recorrencia criada: #{result['next_task_id']}."
            )
        else:
            await update.message.reply_text(f"✅ Tarefa #{task_id} concluida.")
    else:
        await update.message.reply_text(f"⚠️ Tarefa #{task_id} nao encontrada.")


async def _create_pending_event_from_text(update, user_id, chat_id, text):
    payload = _parse_event_payload(text)
    if not payload:
        await update.message.reply_text(
            "Nao consegui entender data e horario. Ex: /event reuniao com Ana amanha as 10 por 45min"
        )
        return

    warnings = []
    conflicts = []
    backend = _calendar_backend()

    if _calendar_uses_internal():
        conflicts.extend(_find_internal_conflicts(user_id, payload["start_at"], payload["end_at"]))

    if _calendar_uses_google():
        try:
            conflicts.extend(_find_calendar_conflicts(payload["start_at"], payload["end_at"]))
        except Exception as e:
            warnings.append(f"Nao consegui checar conflitos no Google Calendar: {e}")

    if conflicts:
        conflict_text = _format_conflicts(conflicts)
        suggestions = _suggest_event_slots(payload["start_at"], payload["duration_minutes"], conflicts)
        suggestion_lines = [f"- {slot.strftime('%d/%m/%Y %H:%M')}" for slot in suggestions]
        warnings.append(f"{conflict_text}\nAlternativas proximas:\n" + "\n".join(suggestion_lines))

    message_parts = []
    if warnings:
        message_parts.append("\n\n".join(warnings))

    created_internal_event = None
    if _calendar_uses_internal():
        settings = get_user_settings(user_id) or {}
        reminder_minutes = payload["reminder_minutes"]
        if reminder_minutes is None:
            reminder_minutes = settings.get("meeting_reminder_minutes", 15)
        internal_id = add_internal_event(
            user_id,
            chat_id,
            payload["summary"],
            payload["start_at"].isoformat(timespec="minutes"),
            payload["end_at"].isoformat(timespec="minutes"),
            description=payload["description"],
            location=payload["location"],
            attendees=payload["attendees"],
            reminder_minutes=reminder_minutes,
        )
        created_internal_event = get_internal_event(internal_id, user_id)
        message_parts.append(_format_internal_event_created(created_internal_event))

    if _calendar_uses_google():
        pending_id = add_pending_calendar_event(
            user_id,
            chat_id,
            payload["summary"],
            payload["start_at"].isoformat(timespec="minutes"),
            payload["end_at"].isoformat(timespec="minutes"),
            description=payload["description"],
            location=payload["location"],
            attendees=payload["attendees"],
        )
        pending = get_pending_calendar_event(pending_id, user_id)
        message_parts.append(_format_event_preview(pending))

    if not message_parts:
        await update.message.reply_text(f"Backend de agenda invalido: {backend}. Use internal, google ou both.")
        return

    await update.message.reply_text("\n\n".join(message_parts))


async def _handle_structured_instruction(update, user_id, chat_id, text):
    memory_text = _extract_memory_text(text)
    if memory_text:
        memory_id = add_memory(user_id, memory_text)
        await update.message.reply_text(f"Memoria salva. ID: {memory_id}")
        return True

    if text.strip().lower() in MEMORY_LIST_REQUESTS:
        await update.message.reply_text(_format_memories(get_memories(user_id)))
        return True

    if _is_task_list_request(text):
        task_filter, category, require_reminder = _parse_task_filter_and_category(text)
        await _reply_with_tasks(update, user_id, task_filter, category, require_reminder)
        return True

    task_update = _extract_task_update_request(text)
    if task_update:
        await _edit_task_from_text(
            update,
            user_id,
            task_update["task_id"],
            task_update["update_text"],
            full_text=task_update["full_text"],
            prefix=task_update["prefix"],
        )
        return True

    if _is_task_complete_request(text):
        await _complete_task_by_id(update, user_id, _extract_task_id(text))
        return True

    if _is_task_delete_request(text):
        await _delete_task_by_id(update, user_id, _extract_task_id(text))
        return True

    task_text = _extract_task_text(text)
    if task_text:
        await _create_task_from_text(update, user_id, task_text)
        return True

    event_text = _extract_event_text(text)
    if event_text:
        await _create_pending_event_from_text(update, user_id, chat_id, event_text)
        return True

    mission_goal = _extract_mission_goal(text)
    if mission_goal:
        await _create_mission_from_goal(update, user_id, mission_goal)
        return True

    return False


def _format_memories(memories):
    if not memories:
        return "Ainda nao tenho memorias salvas sobre voce."

    lines = ["Memorias salvas:"]
    lines.extend(f"{memory['id']}. {memory['content']}" for memory in memories)
    return "\n".join(lines)


def _build_memory_context(user_id):
    memories = get_memories(user_id)
    if not memories:
        return None

    memory_lines = [f"- {memory['content']}" for memory in reversed(memories)]
    return (
        "Contexto persistente sobre o usuario. Use essas memorias apenas quando "
        "forem relevantes para responder melhor. Nao diga que esta lendo uma "
        "base de memorias, a menos que o usuario pergunte.\n"
        + "\n".join(memory_lines)
    )


def _format_knowledge_results(results):
    if not results:
        return "Nada relevante encontrado na base semantica."

    lines = ["Resultados da busca semantica:"]
    for item in results:
        excerpt = item["content"].replace("\n", " ")
        if len(excerpt) > 240:
            excerpt = excerpt[:237].rstrip() + "..."
        score = f"{item['score']:.2f}"
        lines.append(
            f"{item['source_type']}:{item['source_id']} ({score}) - {item['title']}\n{excerpt}"
        )
    return "\n\n".join(lines)


def _email_knowledge_content(email):
    lines = [
        f"E-mail: {email.get('subject', 'Sem assunto')}",
        f"De: {email.get('from', 'Desconhecido')}",
        f"Data: {email.get('date', 'Sem data')}",
    ]
    if email.get("snippet"):
        lines.append(f"Trecho: {email['snippet']}")
    return "\n".join(lines)


def _email_priority(email):
    text = " ".join([
        email.get("subject", ""),
        email.get("from", ""),
        email.get("snippet", ""),
    ]).lower()
    urgent_terms = (
        "urgente", "urgent", "asap", "imediato", "imediata", "prazo",
        "vencimento", "atrasado", "bloqueado", "problema", "erro",
        "contrato", "proposta", "pagamento", "invoice", "fatura",
    )
    if any(term in text for term in urgent_terms):
        return "alta"
    if "re:" in email.get("subject", "").lower() or "res:" in email.get("subject", "").lower():
        return "media"
    return "normal"


def _format_email_line(email):
    priority = _email_priority(email)
    snippet = email.get("snippet", "").replace("\n", " ")
    if len(snippet) > 180:
        snippet = snippet[:177].rstrip() + "..."
    parts = [
        f"ID: {email.get('id')}",
        f"Prioridade: {priority}",
        f"De: {email.get('from', 'Desconhecido')}",
        f"Assunto: {email.get('subject', 'Sem assunto')}",
        f"Data: {email.get('date', 'Sem data')}",
    ]
    if snippet:
        parts.append(f"Trecho: {snippet}")
    return "\n".join(parts)


def _format_emails(emails, title="E-mails"):
    if not emails:
        return "Nenhum e-mail encontrado."
    lines = [f"{title}:"]
    for index, email in enumerate(emails, start=1):
        lines.append(f"{index}. {_format_email_line(email)}")
    return "\n\n".join(lines)


def _index_emails(user_id, emails):
    for email in emails:
        upsert_knowledge_item(
            user_id,
            "gmail",
            email["id"],
            email.get("subject", "Sem assunto"),
            _email_knowledge_content(email),
            metadata={
                "gmail_id": email["id"],
                "thread_id": email.get("thread_id"),
                "from": email.get("from"),
                "date": email.get("date"),
            },
        )
    return len(emails)


def _summarize_emails(emails):
    if not emails:
        return "Nenhum e-mail encontrado para resumir."

    email_lines = []
    for index, email in enumerate(emails, start=1):
        email_lines.append(
            f"{index}. ID: {email.get('id')}\n"
            f"De: {email.get('from')}\n"
            f"Assunto: {email.get('subject')}\n"
            f"Data: {email.get('date')}\n"
            f"Trecho: {email.get('snippet')}\n"
            f"Prioridade heuristica: {_email_priority(email)}"
        )

    prompt = (
        "Resuma estes e-mails em portugues do Brasil. Seja objetivo.\n"
        "Agrupe por prioridade, destaque possiveis acoes e cite os IDs relevantes.\n\n"
        + "\n\n".join(email_lines)
    )
    return get_gemini_response(prompt)


def _extract_email_address(value):
    match = EMAIL_RE.search(value or "")
    return match.group(0) if match else (value or "")


def _parse_email_draft_response(text, original_subject):
    subject = None
    body_lines = []
    in_body = False

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        lowered = line.lower()
        if lowered.startswith("assunto:") or lowered.startswith("subject:"):
            subject = line.split(":", 1)[1].strip()
            continue
        if lowered.startswith("corpo:") or lowered.startswith("body:"):
            in_body = True
            remainder = line.split(":", 1)[1].strip()
            if remainder:
                body_lines.append(remainder)
            continue
        if in_body or line:
            body_lines.append(raw_line.rstrip())

    if not subject:
        subject = original_subject or "Resposta"
        if not subject.lower().startswith(("re:", "res:")):
            subject = f"Re: {subject}"

    body = "\n".join(body_lines).strip() or (text or "").strip()
    return subject, body


def _generate_email_draft(email, instruction):
    prompt = (
        "Crie um rascunho de resposta em portugues do Brasil para o e-mail abaixo.\n"
        "Nao diga que enviou nada. Gere apenas um rascunho revisavel.\n"
        "Formato obrigatorio:\n"
        "Assunto: <assunto sugerido>\n"
        "Corpo:\n"
        "<corpo do e-mail>\n\n"
        f"Instrucao do usuario: {instruction}\n\n"
        f"E-mail original:\n"
        f"De: {email.get('from')}\n"
        f"Para: {email.get('to')}\n"
        f"Assunto: {email.get('subject')}\n"
        f"Data: {email.get('date')}\n"
        f"Trecho: {email.get('snippet')}\n"
    )
    response = get_gemini_response(prompt)
    subject, body = _parse_email_draft_response(response, email.get("subject"))
    return subject, body


def _format_draft_summary(draft):
    return (
        f"{draft['id']}. [{draft['status']}] {draft['subject']}\n"
        f"Para: {draft.get('to_email') or draft.get('original_from')}\n"
        f"E-mail original: {draft['email_id']}"
    )


def _format_draft_full(draft):
    return (
        f"Rascunho #{draft['id']} [{draft['status']}]\n"
        f"E-mail original: {draft['email_id']}\n"
        f"De original: {draft.get('original_from')}\n"
        f"Para: {draft.get('to_email')}\n"
        f"Assunto original: {draft.get('original_subject')}\n"
        f"Assunto sugerido: {draft['subject']}\n"
        f"Instrucao: {draft.get('instruction') or '-'}\n\n"
        f"{draft['body']}\n\n"
        "Este rascunho esta salvo localmente e nao foi enviado."
    )


def _drive_file_knowledge_content(file_item):
    lines = [
        f"Arquivo do Drive: {file_item.get('name')}",
        f"ID: {file_item.get('id')}",
        f"Tipo: {file_item.get('mimeType')}",
        f"Modificado em: {file_item.get('modifiedTime')}",
    ]
    if file_item.get("webViewLink"):
        lines.append(f"Link: {file_item['webViewLink']}")
    if file_item.get("size"):
        lines.append(f"Tamanho: {file_item['size']} bytes")
    return "\n".join(lines)


def _format_drive_file(file_item):
    lines = [
        f"ID: {file_item.get('id')}",
        f"Nome: {file_item.get('name')}",
        f"Tipo: {file_item.get('mimeType')}",
        f"Modificado: {file_item.get('modifiedTime', 'desconhecido')}",
    ]
    if file_item.get("webViewLink"):
        lines.append(f"Link: {file_item['webViewLink']}")
    return "\n".join(lines)


def _format_drive_files(files):
    if not files:
        return "Nenhum arquivo encontrado no Drive."
    lines = ["Arquivos do Drive:"]
    for index, file_item in enumerate(files, start=1):
        lines.append(f"{index}. {_format_drive_file(file_item)}")
    return "\n\n".join(lines)


def _index_drive_files(user_id, files):
    for file_item in files:
        upsert_knowledge_item(
            user_id,
            "drive_file",
            file_item["id"],
            file_item.get("name", "Arquivo sem nome"),
            _drive_file_knowledge_content(file_item),
            metadata={
                "drive_file_id": file_item["id"],
                "mime_type": file_item.get("mimeType"),
                "modified_time": file_item.get("modifiedTime"),
                "link": file_item.get("webViewLink"),
            },
        )
    return len(files)


def _doc_knowledge_title(doc, chunk_index=None):
    suffix = f" parte {chunk_index}" if chunk_index else ""
    return f"{doc.get('title', 'Documento')}{suffix}"


def _index_document(user_id, doc):
    chunks = chunk_text(doc.get("text", ""), max_chars=1200)
    if not chunks and doc.get("title"):
        chunks = [doc["title"]]

    for index, chunk in enumerate(chunks, start=1):
        upsert_knowledge_item(
            user_id,
            "google_doc",
            f"{doc['id']}:{index}",
            _doc_knowledge_title(doc, index),
            f"Documento: {doc.get('title')}\n\n{chunk}",
            metadata={"document_id": doc["id"], "chunk": index},
        )
    return len(chunks)


def _summarize_document(doc):
    text = doc.get("text", "")
    if not text.strip():
        return "Documento sem texto suficiente para resumir."
    prompt = (
        "Resuma este Google Docs em portugues do Brasil.\n"
        "Inclua: assunto principal, pontos importantes e possiveis proximas acoes.\n\n"
        f"Titulo: {doc.get('title')}\n\n"
        f"Conteudo:\n{text[:12000]}"
    )
    return get_gemini_response(prompt)


def _build_rag_context(user_id, query):
    results = search_knowledge(user_id, query, limit=5)
    if not results:
        return None

    lines = [
        "Contexto recuperado por busca semantica. Use apenas se for relevante "
        "para responder melhor; se nao tiver certeza, trate como contexto auxiliar."
    ]
    for index, item in enumerate(results, start=1):
        lines.append(
            f"[{index}] Fonte: {item['source_type']}:{item['source_id']} - {item['title']}\n"
            f"{item['content']}"
        )
    return "\n\n".join(lines)


def _build_time_context():
    now = local_now()
    weekday = WEEKDAY_LABELS[now.weekday()]
    return (
        "Data e hora atuais para interpretar pedidos do usuario:\n"
        f"- Hoje: {weekday}, {now.strftime('%d/%m/%Y')}\n"
        f"- Hora local: {now.strftime('%H:%M')}\n"
        f"- Fuso horario: {app_timezone_name()}"
    )


def _build_assistant_context(user_id, query):
    sections = [ASSISTANT_PERSONA, _build_time_context()]
    memory_context = _build_memory_context(user_id)
    rag_context = _build_rag_context(user_id, query)
    if memory_context:
        sections.append(memory_context)
    if rag_context:
        sections.append(rag_context)
    return "\n\n".join(sections)


def _task_digest(tasks, title):
    if not tasks:
        return f"{title}: nenhuma."
    lines = [f"{title}:"]
    lines.extend(f"- {_format_task_summary_line(task)}" for task in tasks[:10])
    return "\n".join(lines)


def _day_load_suggestion(today_tasks, overdue_tasks, events):
    high_priority = [task for task in today_tasks if task.get("priority") == "alta"]
    total_commitments = len(today_tasks) + len(events)
    if overdue_tasks:
        return "Sugestao: comece pelas tarefas atrasadas antes de aceitar novos compromissos."
    if total_commitments >= 8 or len(events) >= 5:
        return "Sugestao: o dia parece cheio; proteja blocos de foco e adie tarefas de baixa prioridade."
    if len(high_priority) >= 3:
        return "Sugestao: ha varias prioridades altas; escolha as 2 mais importantes para garantir entrega."
    return "Sugestao: dia administravel; mantenha as prioridades altas no topo."


def build_today_briefing(user_id):
    today_tasks = get_tasks(user_id, task_filter="today")
    overdue_tasks = get_tasks(user_id, task_filter="overdue")
    week_tasks = get_tasks(user_id, task_filter="week")

    events = []
    agenda_parts = []
    if _calendar_uses_internal():
        internal_events = list_internal_events(user_id, event_filter="today", limit=20)
        events.extend(internal_events)
        agenda_parts.append(_format_internal_events(internal_events, "Agenda interna de hoje"))

    if _calendar_uses_google():
        try:
            google_events = list_events_for_day()
            events.extend(google_events)
            agenda_parts.append("Google Calendar:\n" + format_calendar_events(google_events, "Nenhum evento hoje."))
        except Exception as e:
            agenda_parts.append(f"Google Calendar: nao consegui acessar: {e}")

    agenda = "\n\n".join(agenda_parts) if agenda_parts else "Nenhum backend de agenda ativo."

    memory_results = search_knowledge(user_id, "prioridades preferencias contexto importante hoje", limit=3)
    memory_lines = []
    for item in memory_results:
        excerpt = item["content"].replace("\n", " ")
        if len(excerpt) > 160:
            excerpt = excerpt[:157].rstrip() + "..."
        memory_lines.append(f"- {item['title']}: {excerpt}")

    sections = [
        f"Briefing de hoje - {local_date().strftime('%d/%m/%Y')}",
        "",
        "Agenda:",
        agenda,
        "",
        _task_digest(overdue_tasks, "Tarefas atrasadas"),
        "",
        _task_digest(today_tasks, "Tarefas de hoje"),
        "",
        _task_digest(week_tasks[:5], "Proximas da semana"),
        "",
        "Contexto relevante:",
        "\n".join(memory_lines) if memory_lines else "- nenhum contexto semantico forte encontrado.",
        "",
        _day_load_suggestion(today_tasks, overdue_tasks, events),
    ]
    return "\n".join(sections)


def _project_root():
    return Path(__file__).resolve().parent.parent


def _index_project_docs():
    root = _project_root()
    clear_knowledge_source(0, "doc")
    indexed = 0

    for filename in DOC_FILES:
        path = root / filename
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        for chunk_index, chunk in enumerate(chunk_text(content), start=1):
            upsert_knowledge_item(
                0,
                "doc",
                f"{filename}:{chunk_index}",
                f"{filename} parte {chunk_index}",
                chunk,
                metadata={"file": filename, "chunk": chunk_index},
            )
            indexed += 1
    return indexed


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Opa! Eu sou seu assistente pessoal com IA.\n"
        "Posso conversar, guardar memorias, organizar tarefas, buscar informacoes e acessar Google Workspace.\n"
        "Tente: lembre que meu cliente principal e a Loja X"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
*Commands:*
/start - Start the bot
/help - Show this help
/task <text> - Add a task. Ex: /task pagar boleto amanha as 9 #casa prioridade:alta
/remind <text> - Add a reminder. Ex: /remind tomar remedio em 30 minutos
/list [hoje|semana|atrasadas|concluidas|todas] [#categoria] - List tasks
/reminders [hoje|semana|atrasadas|concluidas|todas] [#categoria] - List task reminders
/done <id> - Mark a task as completed
/task_edit <id> <alteracoes> - Edit title, due date, time, priority, category, recurrence or reminder
/task_delete <id> - Delete a task/reminder
/today - Daily briefing with agenda, tasks and context
/daily [on HH:MM|off|status] - Configure automatic daily briefing
/meeting_reminders [on|off|minutes <n>|status] - Configure meeting reminders
/event <text> - Create an internal agenda event, or Google event when enabled
/events [hoje|semana|proximos|todas|cancelados] - List internal agenda events
/agenda [hoje|semana|proximos|todas|cancelados] - Alias for /events
/confirm_event <id> - Create a pending Google Calendar event when Google backend is enabled
/cancel_event <id> - Cancel an internal or pending event
/remember <text> - Save a persistent memory
/memory - List saved memories
/memory add <text> - Save a persistent memory
/memory delete <id> - Delete one memory
/memory clear - Delete all your memories
/forget <id> - Delete one memory
/knowledge search <query> - Search semantic memory/RAG base
/knowledge index_docs - Index project docs into the vector DB
/mission <goal> - Create an agent mission with planned steps
/missions [ativas|concluidas|todas] - List missions
/mission_status <id> - Show mission state and checkpoints
/mission_step <id> <step> <start|done|block|skip> [note] - Update a mission checkpoint
/mission_confirm <id> <step> - Confirm a sensitive mission step
/mission_report <id> - Generate a progress report
/emails [list|summary|index|search] - Smart Gmail summaries and RAG search
/email_draft <email_id> <instruction> - Create a local draft, without sending
/drafts - List local pending email drafts
/draft_view <id> - Show one local draft
/draft_delete <id> - Archive one local draft
/search <query> - Search the web
/gmail [query] - List recent emails filtered by query (optional)
/drive [list|index|search] - Drive file listing and RAG search
/calendar - List upcoming agenda events
/docs <document_id|summary|index> - Preview, summarize or index Google Docs
/app_status - Check external app status

*Features:*
- Conversas com memória: mantenho o contexto das últimas mensagens.
- Memoria pessoal persistente: diga "lembre que..." para eu guardar fatos importantes.
- Tarefas e lembretes inteligentes: entendo prazo, prioridade, categoria, recorrencia e alertas como "em 30 minutos".
- Gestao de tarefas por texto: liste, edite, conclua ou exclua tarefas pelo ID.
- Agenda interna: crio eventos, reunioes e compromissos no banco do bot e envio alertas pelo Telegram.
- E-mails inteligentes: resumo, prioridade heuristica e busca semantica via RAG.
- Drive/Docs inteligentes: indexo arquivos e resumo documentos Google Docs.
- Modo agente: transformo metas em missoes com passos, checkpoints e relatorios.
- RAG: uso a base vetorial configurada para recuperar memorias, tarefas e docs relevantes.
- Send me any text to chat with AI.
- Send me a photo to analyze it.
- Send me a voice note to transcribe and handle commands like reminders and events.
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    upsert_user_settings(user_id, chat_id=chat_id)

    if await _handle_structured_instruction(update, user_id, chat_id, user_text):
        return

    history = get_conversation_history(user_id)
    response = get_gemini_response(
        user_text,
        history=history,
        system_context=_build_assistant_context(user_id, user_text),
    )

    log_conversation(user_id, "user", user_text)
    log_conversation(user_id, "assistant", response)

    await update.message.reply_text(response)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    from io import BytesIO
    bio = BytesIO()
    await photo_file.download_to_memory(bio)
    bio.seek(0)
    image_data = bio.read()

    caption = update.message.caption or "Describe this image"
    await update.message.reply_text("👀 Analyzing image...")

    import PIL.Image
    img = PIL.Image.open(BytesIO(image_data))

    response = analyze_image(img, caption)
    await update.message.reply_text(response)

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("🎤 Ouvindo...")

    voice = update.message.voice or update.message.audio
    file_id = voice.file_id
    new_file = await context.bot.get_file(file_id)

    file_path = os.path.join(tempfile.gettempdir(), f"voice_{file_id}.ogg")
    await new_file.download_to_drive(file_path)

    try:
        text = transcribe_audio(file_path)

        if text.startswith("Error"):
            await status_msg.edit_text(f"❌ {text}")
            return

        await status_msg.edit_text(f"🗣️ *Você disse:* \"{text}\"\n\n🤔 *Pensando...*", parse_mode='Markdown')

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        upsert_user_settings(user_id, chat_id=chat_id)
        if await _handle_structured_instruction(update, user_id, chat_id, text):
            return

        history = get_conversation_history(user_id)
        response = get_gemini_response(
            text,
            history=history,
            system_context=_build_assistant_context(user_id, text),
        )

        log_conversation(user_id, "user", text)
        log_conversation(user_id, "assistant", response)

        await update.message.reply_text(response)

    except Exception as e:
        await status_msg.edit_text(f"Error processing audio: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

async def add_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    upsert_user_settings(user_id, chat_id=update.effective_chat.id)
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text(
            "Uso: /task <tarefa> [hoje|amanha|dd/mm] [as HH:MM] [#categoria] [prioridade:alta|media|baixa]"
        )
        return

    await _create_task_from_text(update, user_id, text)

async def list_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    upsert_user_settings(user_id, chat_id=update.effective_chat.id)
    task_filter = "pending"
    category = None

    for arg in context.args:
        lowered = arg.lower()
        if lowered in TASK_FILTER_ALIASES:
            task_filter = TASK_FILTER_ALIASES[lowered]
        elif lowered.startswith("#"):
            category = lowered[1:]
        elif lowered.startswith("categoria:"):
            category = lowered.split(":", 1)[1]

    await _reply_with_tasks(update, user_id, task_filter, category)


async def list_task_reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    upsert_user_settings(user_id, chat_id=update.effective_chat.id)
    task_filter = "pending"
    category = None

    if context.args and context.args[0].lower() in {"on", "off", "minutes", "minutos", "status"}:
        await update.message.reply_text(
            "Para avisos de reuniao use /meeting_reminders. Para lembretes internos, use /reminders ou edite por ID."
        )
        return

    for arg in context.args:
        lowered = arg.lower()
        if lowered in TASK_FILTER_ALIASES:
            task_filter = TASK_FILTER_ALIASES[lowered]
        elif lowered.startswith("#"):
            category = lowered[1:]
        elif lowered.startswith("categoria:"):
            category = lowered.split(":", 1)[1]

    await _reply_with_tasks(update, user_id, task_filter, category, require_reminder=True)


async def complete_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    upsert_user_settings(user_id, chat_id=update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("Usage: /done <task_id>")
        return
    try:
        task_id = int(context.args[0])
        await _complete_task_by_id(update, user_id, task_id)
    except ValueError:
        await update.message.reply_text("ID de tarefa invalido.")


async def edit_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    upsert_user_settings(user_id, chat_id=update.effective_chat.id)
    if len(context.args) < 2:
        await update.message.reply_text(
            "Uso: /task_edit <id> <alteracoes>. Ex: /task_edit 12 revisar proposta amanha as 9 prioridade:alta"
        )
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID de tarefa invalido.")
        return

    update_text = " ".join(context.args[1:]).strip()
    await _edit_task_from_text(update, user_id, task_id, update_text)


async def delete_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    upsert_user_settings(user_id, chat_id=update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("Uso: /task_delete <id>")
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID de tarefa invalido.")
        return

    await _delete_task_by_id(update, user_id, task_id)


async def send_due_task_reminders(context: ContextTypes.DEFAULT_TYPE):
    for task in get_due_task_reminders():
        message = "⏰ Lembrete de tarefa\n\n" + _format_task_card(task)
        try:
            await context.bot.send_message(chat_id=task["user_id"], text=message)
            mark_task_reminded(task["id"])
        except Exception:
            continue


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    upsert_user_settings(user_id, chat_id=update.effective_chat.id)
    await update.message.reply_text(build_today_briefing(user_id))


async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    upsert_user_settings(user_id, chat_id=chat_id)

    if not context.args or context.args[0].lower() == "status":
        settings = get_user_settings(user_id)
        if not settings:
            await update.message.reply_text("Resumo diario ainda nao configurado.")
            return
        status = "ativo" if settings["daily_summary_enabled"] else "desativado"
        await update.message.reply_text(
            f"Resumo diario: {status}\nHorario: {settings['daily_summary_time']}"
        )
        return

    action = context.args[0].lower()
    if action in {"off", "desativar", "parar"}:
        upsert_user_settings(user_id, chat_id=chat_id, daily_summary_enabled=False)
        await update.message.reply_text("Resumo diario desativado.")
        return

    if action in {"on", "ativar", "ligar"}:
        summary_time = context.args[1] if len(context.args) > 1 else "08:00"
        if not re.match(r"^\d{2}:\d{2}$", summary_time):
            await update.message.reply_text("Uso: /daily on HH:MM")
            return
        hour, minute = [int(part) for part in summary_time.split(":")]
        if hour > 23 or minute > 59:
            await update.message.reply_text("Horario invalido. Use HH:MM.")
            return
        upsert_user_settings(
            user_id,
            chat_id=chat_id,
            daily_summary_enabled=True,
            daily_summary_time=summary_time,
            meeting_reminders_enabled=True,
        )
        await update.message.reply_text(f"Resumo diario ativado para {summary_time}.")
        return

    await update.message.reply_text("Uso: /daily on HH:MM, /daily off ou /daily status")


async def meeting_reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    upsert_user_settings(user_id, chat_id=chat_id)

    if not context.args or context.args[0].lower() == "status":
        settings = get_user_settings(user_id)
        status = "ativos" if settings and settings["meeting_reminders_enabled"] else "desativados"
        minutes = settings["meeting_reminder_minutes"] if settings else 15
        await update.message.reply_text(
            f"Avisos de reuniao: {status}\nAntecedencia: {minutes} minuto(s)"
        )
        return

    action = context.args[0].lower()
    if action in {"on", "ativar", "ligar"}:
        upsert_user_settings(user_id, chat_id=chat_id, meeting_reminders_enabled=True)
        await update.message.reply_text("Avisos de reuniao ativados.")
        return

    if action in {"off", "desativar", "parar"}:
        upsert_user_settings(user_id, chat_id=chat_id, meeting_reminders_enabled=False)
        await update.message.reply_text("Avisos de reuniao desativados.")
        return

    if action in {"minutes", "minutos", "antecedencia", "antecedência"}:
        if len(context.args) < 2:
            await update.message.reply_text("Uso: /meeting_reminders minutes <5-120>")
            return
        try:
            minutes = int(context.args[1])
        except ValueError:
            await update.message.reply_text("Informe um numero de minutos.")
            return
        if minutes < 1 or minutes > 120:
            await update.message.reply_text("Use uma antecedencia entre 1 e 120 minutos.")
            return
        upsert_user_settings(
            user_id,
            chat_id=chat_id,
            meeting_reminders_enabled=True,
            meeting_reminder_minutes=minutes,
        )
        await update.message.reply_text(f"Avisos configurados para {minutes} minuto(s) antes.")
        return

    await update.message.reply_text("Uso: /meeting_reminders on, /meeting_reminders off, /meeting_reminders minutes <n> ou /meeting_reminders status")


async def events_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    upsert_user_settings(user_id, chat_id=update.effective_chat.id)
    event_filter = "upcoming"
    if context.args:
        event_filter = EVENT_FILTER_ALIASES.get(context.args[0].lower(), context.args[0].lower())
    events = list_internal_events(user_id, event_filter=event_filter, limit=30)
    await update.message.reply_text(_format_internal_events(events, f"Agenda interna ({event_filter})"))


async def event_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    upsert_user_settings(user_id, chat_id=chat_id)
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("Uso: /event <titulo> <data> as <hora> [por 60min]")
        return
    await _create_pending_event_from_text(update, user_id, chat_id, text)


async def confirm_event_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    upsert_user_settings(user_id, chat_id=update.effective_chat.id)
    if not _calendar_uses_google():
        await update.message.reply_text(
            "Google Calendar esta desativado. Com CALENDAR_BACKEND=internal, eventos ja sao criados direto na agenda interna."
        )
        return
    if not context.args:
        await update.message.reply_text("Uso: /confirm_event <id>")
        return
    try:
        pending_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID de evento invalido.")
        return

    pending = get_pending_calendar_event(pending_id, user_id)
    if not pending:
        await update.message.reply_text("Evento pendente nao encontrado.")
        return

    try:
        event = create_calendar_event(
            pending["summary"],
            parse_local_datetime(pending["start_at"]),
            parse_local_datetime(pending["end_at"]),
            pending.get("description"),
            location=pending.get("location"),
            attendees=pending.get("attendees"),
        )
        delete_pending_calendar_event(pending_id, user_id)
        event_id = event.get("id") or pending_id
        upsert_knowledge_item(
            user_id,
            "calendar_event",
            event_id,
            event.get("summary", pending["summary"]),
            _event_knowledge_content(event),
            metadata={"calendar_event_id": event_id},
        )
        link = event.get("htmlLink")
        message = f"Evento criado: {event.get('summary', pending['summary'])}"
        if link:
            message += f"\n{link}"
        await update.message.reply_text(message)
    except Exception as e:
        await update.message.reply_text(f"Erro ao criar evento no Calendar: {e}")


async def cancel_event_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Uso: /cancel_event <id>")
        return
    try:
        pending_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID de evento invalido.")
        return

    if cancel_internal_event(pending_id, user_id):
        await update.message.reply_text(f"Evento interno {pending_id} cancelado.")
    elif delete_pending_calendar_event(pending_id, user_id):
        await update.message.reply_text(f"Evento pendente do Google Calendar {pending_id} cancelado.")
    else:
        await update.message.reply_text("Evento nao encontrado.")


async def send_daily_summaries(context: ContextTypes.DEFAULT_TYPE):
    current_time = local_now().strftime("%H:%M")
    for user in get_users_for_daily_summary(current_time):
        try:
            await context.bot.send_message(
                chat_id=user["chat_id"],
                text=build_today_briefing(user["user_id"]),
            )
            upsert_user_settings(
                user["user_id"],
                chat_id=user["chat_id"],
                last_daily_summary_date=local_date().isoformat(),
            )
        except Exception:
            continue


async def send_meeting_reminders(context: ContextTypes.DEFAULT_TYPE):
    if _calendar_uses_internal():
        for event in get_due_internal_event_reminders():
            start_at = _parse_event_datetime(event.get("start_at"))
            if not start_at:
                continue
            try:
                await context.bot.send_message(
                    chat_id=event["chat_id"],
                    text=(
                        f"Alerta da agenda: {event['summary']}\n"
                        f"Comeca em {event.get('reminder_minutes', 15)} minuto(s): "
                        f"{start_at.strftime('%d/%m/%Y %H:%M')}"
                    ),
                )
                mark_internal_event_reminded(event["id"])
            except Exception:
                continue

    if not _calendar_uses_google():
        return

    start_window = local_now()
    for user in get_users_with_meeting_reminders():
        reminder_minutes = user.get("meeting_reminder_minutes") or 15
        end_window = start_window + timedelta(minutes=reminder_minutes)
        try:
            events = get_events_between(start_window, end_window, max_results=10)
        except Exception:
            continue
        for event in events:
            event_key = event.get("id") or f"{event.get('summary')}:{event.get('start')}"
            if not mark_calendar_event_reminded(user["user_id"], event_key):
                continue
            start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date")
            summary = event.get("summary", "(Sem titulo)")
            try:
                await context.bot.send_message(
                    chat_id=user["chat_id"],
                    text=f"Aviso do Google Calendar: {summary}\nComeca em ate {reminder_minutes} minuto(s): {start}",
                )
            except Exception:
                continue

async def remember_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("Uso: /remember <informacao para lembrar>")
        return

    memory_id = add_memory(user_id, text)
    await update.message.reply_text(f"Memoria salva. ID: {memory_id}")

async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not context.args or context.args[0].lower() in {"list", "listar", "ver"}:
        await update.message.reply_text(_format_memories(get_memories(user_id)))
        return

    action = context.args[0].lower()
    if action in {"add", "save", "salvar", "lembrar"}:
        text = " ".join(context.args[1:]).strip()
        if not text:
            await update.message.reply_text("Uso: /memory add <informacao para lembrar>")
            return
        memory_id = add_memory(user_id, text)
        await update.message.reply_text(f"Memoria salva. ID: {memory_id}")
        return

    if action in {"delete", "del", "remove", "apagar", "forget", "esquecer"}:
        if len(context.args) < 2:
            await update.message.reply_text("Uso: /memory delete <id>")
            return
        try:
            memory_id = int(context.args[1])
        except ValueError:
            await update.message.reply_text("ID de memoria invalido.")
            return
        if delete_memory(memory_id, user_id):
            await update.message.reply_text(f"Memoria {memory_id} apagada.")
        else:
            await update.message.reply_text(f"Memoria {memory_id} nao encontrada.")
        return

    if action in {"clear", "limpar", "apagar_tudo"}:
        total = clear_memories(user_id)
        await update.message.reply_text(f"{total} memoria(s) apagada(s).")
        return

    await update.message.reply_text(
        "Uso:\n"
        "/memory\n"
        "/memory add <informacao>\n"
        "/memory delete <id>\n"
        "/memory clear"
    )

async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Uso: /forget <id>")
        return
    try:
        memory_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID de memoria invalido.")
        return

    if delete_memory(memory_id, user_id):
        await update.message.reply_text(f"Memoria {memory_id} apagada.")
    else:
        await update.message.reply_text(f"Memoria {memory_id} nao encontrada.")


async def knowledge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        total = count_knowledge_items(user_id)
        backend = get_knowledge_backend()
        await update.message.reply_text(
            "Base semantica ativa.\n"
            f"Backend vetorial: {backend}\n"
            f"Itens disponiveis para voce: {total}\n"
            "Uso:\n"
            "/knowledge search <consulta>\n"
            "/knowledge add <texto>\n"
            "/knowledge index_docs"
        )
        return

    action = context.args[0].lower()
    if action in {"search", "buscar", "busca"}:
        query = " ".join(context.args[1:]).strip()
        if not query:
            await update.message.reply_text("Uso: /knowledge search <consulta>")
            return
        results = search_knowledge(user_id, query, limit=5, min_score=0.02)
        await update.message.reply_text(_format_knowledge_results(results))
        return

    if action in {"add", "salvar", "save"}:
        content = " ".join(context.args[1:]).strip()
        if not content:
            await update.message.reply_text("Uso: /knowledge add <texto>")
            return
        source_id = f"note-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        upsert_knowledge_item(
            user_id,
            "note",
            source_id,
            "Nota semantica",
            content,
            metadata={"created_by": "telegram"},
        )
        await update.message.reply_text(f"Nota adicionada a base semantica: {source_id}")
        return

    if action in {"index_docs", "indexar_docs", "docs"}:
        indexed = _index_project_docs()
        await update.message.reply_text(f"Docs do projeto indexados: {indexed} trecho(s).")
        return

    await update.message.reply_text(
        "Uso:\n"
        "/knowledge search <consulta>\n"
        "/knowledge add <texto>\n"
        "/knowledge index_docs"
    )


async def emails_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    upsert_user_settings(user_id, chat_id=update.effective_chat.id)

    if not context.args:
        await update.message.reply_text(
            "Uso:\n"
            "/emails list [query]\n"
            "/emails summary [query]\n"
            "/emails index [query]\n"
            "/emails search <consulta>"
        )
        return

    action = context.args[0].lower()
    query = " ".join(context.args[1:]).strip() or None

    if action in {"list", "listar", "recentes"}:
        try:
            emails = get_recent_emails(query=query, max_results=10)
        except Exception as e:
            await update.message.reply_text(f"Erro ao acessar Gmail: {e}")
            return
        await update.message.reply_text(_format_emails(emails, "E-mails recentes"))
        return

    if action in {"summary", "resumo", "summarize", "resumir"}:
        try:
            emails = get_recent_emails(query=query, max_results=10)
        except Exception as e:
            await update.message.reply_text(f"Erro ao acessar Gmail: {e}")
            return
        indexed = _index_emails(user_id, emails)
        summary = _summarize_emails(emails)
        await update.message.reply_text(f"{summary}\n\nIndexados no RAG: {indexed}")
        return

    if action in {"index", "indexar"}:
        try:
            emails = get_recent_emails(query=query, max_results=25)
        except Exception as e:
            await update.message.reply_text(f"Erro ao acessar Gmail: {e}")
            return
        indexed = _index_emails(user_id, emails)
        await update.message.reply_text(f"E-mails indexados no RAG: {indexed}")
        return

    if action in {"search", "buscar", "busca"}:
        if not query:
            await update.message.reply_text("Uso: /emails search <consulta>")
            return
        results = search_knowledge(user_id, query, limit=5, source_type="gmail", min_score=0.02)
        await update.message.reply_text(_format_knowledge_results(results))
        return

    await update.message.reply_text(
        "Uso:\n"
        "/emails list [query]\n"
        "/emails summary [query]\n"
        "/emails index [query]\n"
        "/emails search <consulta>"
    )


async def email_draft_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    upsert_user_settings(user_id, chat_id=update.effective_chat.id)
    if len(context.args) < 2:
        await update.message.reply_text("Uso: /email_draft <email_id> <instrucao>")
        return

    email_id = context.args[0]
    instruction = " ".join(context.args[1:]).strip()
    try:
        email = get_email_metadata(email_id)
    except Exception as e:
        await update.message.reply_text(f"Erro ao buscar e-mail no Gmail: {e}")
        return

    subject, body = _generate_email_draft(email, instruction)
    to_email = _extract_email_address(email.get("from"))
    draft_id = add_email_draft(
        user_id,
        email.get("id", email_id),
        email.get("thread_id"),
        to_email,
        email.get("from"),
        email.get("subject"),
        subject,
        body,
        instruction,
    )
    draft = get_email_draft(draft_id, user_id)
    await update.message.reply_text(
        _format_draft_full(draft)
        + f"\n\nPara revisar depois: /draft_view {draft_id}\nPara arquivar: /draft_delete {draft_id}"
    )


async def drafts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    status = context.args[0].lower() if context.args else "pending"
    if status not in {"pending", "archived", "all"}:
        await update.message.reply_text("Uso: /drafts [pending|archived|all]")
        return

    drafts = get_email_drafts(user_id, status=status, limit=10)
    if not drafts:
        await update.message.reply_text("Nenhum rascunho encontrado.")
        return
    lines = [f"Rascunhos ({status}):"]
    lines.extend(_format_draft_summary(draft) for draft in drafts)
    await update.message.reply_text("\n\n".join(lines))


async def draft_view_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Uso: /draft_view <id>")
        return
    try:
        draft_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID de rascunho invalido.")
        return

    draft = get_email_draft(draft_id, user_id)
    if not draft:
        await update.message.reply_text("Rascunho nao encontrado.")
        return
    await update.message.reply_text(_format_draft_full(draft))


async def draft_delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Uso: /draft_delete <id>")
        return
    try:
        draft_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID de rascunho invalido.")
        return

    if update_email_draft_status(draft_id, user_id, "archived"):
        await update.message.reply_text(f"Rascunho {draft_id} arquivado.")
    else:
        await update.message.reply_text("Rascunho nao encontrado.")


async def mission_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    upsert_user_settings(user_id, chat_id=update.effective_chat.id)

    if not context.args:
        await update.message.reply_text(
            "Uso:\n"
            "/mission <meta>\n"
            "/mission status <id>\n"
            "/mission next <id>\n"
            "/mission pause|resume|complete|archive <id>\n"
            "/mission report <id>"
        )
        return

    action = context.args[0].lower()
    if action in {"status", "ver", "show"}:
        if len(context.args) < 2:
            await update.message.reply_text("Uso: /mission status <id>")
            return
        try:
            mission_id = int(context.args[1])
        except ValueError:
            await update.message.reply_text("ID de missao invalido.")
            return
        mission = get_mission(user_id, mission_id)
        await update.message.reply_text(_format_mission_full(mission) if mission else "Missao nao encontrada.")
        return

    if action in {"next", "proximo", "próximo"}:
        if len(context.args) < 2:
            await update.message.reply_text("Uso: /mission next <id>")
            return
        try:
            mission_id = int(context.args[1])
        except ValueError:
            await update.message.reply_text("ID de missao invalido.")
            return
        mission = get_mission(user_id, mission_id)
        if not mission:
            await update.message.reply_text("Missao nao encontrada.")
            return
        step = _current_or_next_step(mission)
        if not step:
            await update.message.reply_text("Nao ha passos pendentes nessa missao.")
            return
        await update.message.reply_text("Proximo passo:\n" + _format_mission_step(step))
        return

    if action in {"report", "relatorio", "relatório"}:
        if len(context.args) < 2:
            await update.message.reply_text("Uso: /mission report <id>")
            return
        try:
            mission_id = int(context.args[1])
        except ValueError:
            await update.message.reply_text("ID de missao invalido.")
            return
        await _send_mission_report(update, user_id, mission_id)
        return

    status_actions = {
        "pause": "paused",
        "pausar": "paused",
        "resume": "active",
        "retomar": "active",
        "complete": "completed",
        "concluir": "completed",
        "archive": "archived",
        "arquivar": "archived",
    }
    if action in status_actions:
        if len(context.args) < 2:
            await update.message.reply_text(f"Uso: /mission {action} <id>")
            return
        try:
            mission_id = int(context.args[1])
        except ValueError:
            await update.message.reply_text("ID de missao invalido.")
            return
        note = " ".join(context.args[2:]).strip() or None
        if update_mission_status(user_id, mission_id, status_actions[action], note=note):
            await update.message.reply_text(f"Missao {mission_id} atualizada para {status_actions[action]}.")
        else:
            await update.message.reply_text("Missao nao encontrada.")
        return

    goal = " ".join(context.args).strip()
    await _create_mission_from_goal(update, user_id, goal)


async def missions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    status = "active"
    if context.args:
        status = MISSION_STATUS_ALIASES.get(context.args[0].lower(), context.args[0].lower())
    missions = list_missions(user_id, status=status)
    await update.message.reply_text(_format_mission_list(missions))


async def mission_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Uso: /mission_status <id>")
        return
    try:
        mission_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID de missao invalido.")
        return
    mission = get_mission(user_id, mission_id)
    await update.message.reply_text(_format_mission_full(mission) if mission else "Missao nao encontrada.")


async def mission_step_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) < 3:
        await update.message.reply_text("Uso: /mission_step <missao> <passo> <start|done|block|skip> [nota]")
        return

    try:
        mission_id = int(context.args[0])
        step_number = int(context.args[1])
    except ValueError:
        await update.message.reply_text("ID de missao ou passo invalido.")
        return

    action = context.args[2].lower()
    status = MISSION_STEP_ACTIONS.get(action)
    if not status:
        await update.message.reply_text("Acao invalida. Use start, done, block, skip ou todo.")
        return

    note = " ".join(context.args[3:]).strip() or None
    result = update_mission_step(user_id, mission_id, step_number, status, note=note)
    if result.get("not_found"):
        await update.message.reply_text("Missao ou passo nao encontrado.")
        return
    if result.get("needs_confirmation"):
        step = result["step"]
        await update.message.reply_text(
            "Este passo exige confirmacao antes de iniciar ou concluir:\n"
            f"{step['step_number']}. {step['title']}\n"
            f"Confirme com /mission_confirm {mission_id} {step_number}"
        )
        return

    mission = get_mission(user_id, mission_id)
    if not mission:
        await update.message.reply_text("Missao atualizada, mas nao consegui recarregar o status.")
        return
    updated_step = next((step for step in mission["steps"] if step["step_number"] == step_number), None)
    message = "Checkpoint registrado."
    if updated_step:
        message += "\n" + _format_mission_step(updated_step)
    if mission["status"] == "completed":
        message += "\n\nMissao concluida."
    await update.message.reply_text(message)


async def mission_confirm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) < 2:
        await update.message.reply_text("Uso: /mission_confirm <missao> <passo> [nota]")
        return
    try:
        mission_id = int(context.args[0])
        step_number = int(context.args[1])
    except ValueError:
        await update.message.reply_text("ID de missao ou passo invalido.")
        return

    note = " ".join(context.args[2:]).strip() or None
    result = confirm_mission_step(user_id, mission_id, step_number, note=note)
    if result.get("not_found"):
        await update.message.reply_text("Missao ou passo nao encontrado.")
        return
    await update.message.reply_text(
        f"Passo {step_number} confirmado. Agora voce pode usar /mission_step {mission_id} {step_number} start ou done."
    )


async def _send_mission_report(update, user_id, mission_id):
    mission = get_mission(user_id, mission_id)
    if not mission:
        await update.message.reply_text("Missao nao encontrada.")
        return
    report = _build_mission_report(mission)
    save_mission_report(user_id, mission_id, report)
    await update.message.reply_text(report)


async def mission_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Uso: /mission_report <id>")
        return
    try:
        mission_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID de missao invalido.")
        return
    await _send_mission_report(update, user_id, mission_id)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Usage: /search <query>")
        return
    await update.message.reply_text(f"🔍 Searching for '{query}'...")
    result = google_search(query)
    await update.message.reply_text(result, parse_mode='Markdown')

async def gmail_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else None
    try:
        result = list_recent_emails(query=query)
    except Exception as e:
        result = f"Erro ao acessar o Gmail: {e}"
    await update.message.reply_text(result, parse_mode='Markdown')

async def drive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    upsert_user_settings(user_id, chat_id=update.effective_chat.id)

    if not context.args:
        try:
            result = list_drive_files()
        except Exception as e:
            result = f"Erro ao acessar o Drive: {e}"
        await update.message.reply_text(result, parse_mode='Markdown')
        return

    action = context.args[0].lower()
    query = " ".join(context.args[1:]).strip() or None

    if action in {"list", "listar", "recentes"}:
        try:
            files = get_drive_files(query=query, page_size=10)
        except Exception as e:
            await update.message.reply_text(f"Erro ao acessar Drive: {e}")
            return
        await update.message.reply_text(_format_drive_files(files))
        return

    if action in {"index", "indexar"}:
        try:
            files = get_drive_files(query=query, page_size=25)
        except Exception as e:
            await update.message.reply_text(f"Erro ao acessar Drive: {e}")
            return
        indexed = _index_drive_files(user_id, files)
        await update.message.reply_text(f"Arquivos do Drive indexados no RAG: {indexed}")
        return

    if action in {"search", "buscar", "busca"}:
        if not query:
            await update.message.reply_text("Uso: /drive search <consulta>")
            return
        results = search_knowledge(user_id, query, limit=5, source_type="drive_file", min_score=0.02)
        await update.message.reply_text(_format_knowledge_results(results))
        return

    await update.message.reply_text(
        "Uso:\n"
        "/drive\n"
        "/drive list [nome]\n"
        "/drive index [nome]\n"
        "/drive search <consulta>"
    )

async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    upsert_user_settings(user_id, chat_id=update.effective_chat.id)

    parts = [f"Backend de agenda: {_calendar_backend()}"]
    if _calendar_uses_internal():
        parts.append(_format_internal_events(list_internal_events(user_id, "upcoming", limit=10), "Agenda interna"))

    if _calendar_uses_google():
        try:
            parts.append("Google Calendar:\n" + list_upcoming_events())
        except Exception as e:
            parts.append(f"Google Calendar: erro ao acessar: {e}")

    await update.message.reply_text("\n\n".join(parts))

async def docs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Uso:\n"
            "/docs <document_id>\n"
            "/docs summary <document_id>\n"
            "/docs index <document_id>"
        )
        return

    user_id = update.effective_user.id
    upsert_user_settings(user_id, chat_id=update.effective_chat.id)
    action = context.args[0].lower()
    if action in {"summary", "resumo", "summarize", "resumir", "index", "indexar"}:
        if len(context.args) < 2:
            await update.message.reply_text(f"Uso: /docs {context.args[0]} <document_id>")
            return
        document_id = context.args[1]
        try:
            doc = get_document_content(document_id)
        except Exception as e:
            await update.message.reply_text(f"Erro ao acessar Docs: {e}")
            return

        if action in {"summary", "resumo", "summarize", "resumir"}:
            indexed = _index_document(user_id, doc)
            summary = _summarize_document(doc)
            await update.message.reply_text(f"{summary}\n\nTrechos indexados no RAG: {indexed}")
            return

        indexed = _index_document(user_id, doc)
        await update.message.reply_text(f"Documento indexado no RAG: {indexed} trecho(s).")
        return

    document_id = context.args[0]
    try:
        result = get_document_metadata(document_id)
    except Exception as e:
        result = f"Erro ao acessar o Docs: {e}"
    await update.message.reply_text(result, parse_mode='Markdown')

async def app_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Connecting to external app...")
    data = external_client.get_dashboard_data()
    if isinstance(data, dict):
        msg = f"*App Status:*\nStatus: {data.get('status')}\nPending Orders: {data.get('pending_orders')}"
    else:
        msg = f"Error: {data}"

    await update.message.reply_text(msg, parse_mode='Markdown')
