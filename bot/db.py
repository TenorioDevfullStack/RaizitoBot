import json
import logging
import os
import shutil
import sqlite3
from pathlib import Path
from datetime import date, datetime, time, timedelta

from dotenv import load_dotenv
from bot.rag import cosine_similarity, embed_text
from bot.time_utils import local_date, local_now, parse_local_datetime
from bot.vector_store import (
    active_vector_backend,
    supabase_clear_knowledge_source,
    supabase_count_knowledge_items,
    supabase_delete_knowledge_item,
    supabase_fallback_to_sqlite,
    supabase_search_knowledge,
    supabase_upsert_knowledge_item,
    use_supabase_vector_store,
)

load_dotenv()

logger = logging.getLogger(__name__)


def _default_db_path():
    if os.getenv("VERCEL"):
        return "/tmp/bot_data.db"

    if os.name == "nt":
        base_dir = os.getenv("LOCALAPPDATA") or os.getenv("TEMP") or "."
        try:
            if shutil.disk_usage(base_dir).free > 10 * 1024 * 1024:
                return str(Path(base_dir) / "RaizitoBot" / "bot_data.db")
        except OSError:
            pass
        return "data/bot_data.db"

    return "data/bot_data.db"


def _db_path():
    return os.getenv("DB_PATH") or _default_db_path()


def _connect():
    db_path = Path(_db_path())
    if db_path.parent != Path("."):
        db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def get_database_path():
    return _db_path()


def _add_column_if_missing(cursor, table_name, column_name, column_sql):
    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_columns = {row[1] for row in cursor.fetchall()}
    if column_name not in existing_columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")


def _row_to_task(row):
    return {
        "id": row[0],
        "user_id": row[1],
        "title": row[2],
        "description": row[3],
        "due_date": row[4],
        "is_completed": bool(row[5]),
        "created_at": row[6],
        "priority": row[7],
        "category": row[8],
        "reminder_at": row[9],
        "recurrence": row[10],
        "completed_at": row[11],
        "updated_at": row[12],
        "last_reminded_at": row[13],
        "due_time": row[14],
    }


def _task_knowledge_content(task):
    details = [
        f"Tarefa: {task.get('title')}",
        f"Status: {'concluida' if task.get('is_completed') else 'pendente'}",
    ]
    if task.get("description"):
        details.append(f"Descricao: {task['description']}")
    if task.get("due_date"):
        due = task["due_date"]
        if task.get("due_time"):
            due += f" {task['due_time']}"
        details.append(f"Prazo: {due}")
    if task.get("priority"):
        details.append(f"Prioridade: {task['priority']}")
    if task.get("category"):
        details.append(f"Categoria: {task['category']}")
    if task.get("recurrence"):
        details.append(f"Recorrencia: {task['recurrence']}")
    return "\n".join(details)


def _email_draft_knowledge_content(draft):
    lines = [
        f"Rascunho de e-mail: {draft.get('subject')}",
        f"Status: {draft.get('status')}",
        f"Para: {draft.get('to_email')}",
        f"E-mail original: {draft.get('email_id')}",
    ]
    if draft.get("instruction"):
        lines.append(f"Instrucao: {draft['instruction']}")
    if draft.get("body"):
        lines.append(f"Corpo:\n{draft['body']}")
    return "\n".join(lines)


def _mission_step_knowledge_line(step):
    marker = "confirmacao necessaria" if step.get("requires_confirmation") else "sem confirmacao"
    details = step.get("details")
    line = (
        f"{step.get('step_number')}. [{step.get('status')}] {step.get('title')} "
        f"({marker})"
    )
    if details:
        line += f" - {details}"
    if step.get("checkpoint_note"):
        line += f" Ultimo checkpoint: {step['checkpoint_note']}"
    return line


def _mission_knowledge_content(mission, steps=None):
    lines = [
        f"Missao: {mission.get('goal')}",
        f"Status: {mission.get('status')}",
    ]
    if mission.get("summary"):
        lines.append(f"Resumo: {mission['summary']}")
    if mission.get("current_step"):
        lines.append(f"Passo atual: {mission['current_step']}")
    if steps:
        lines.append("Plano:")
        lines.extend(_mission_step_knowledge_line(step) for step in steps)
    if mission.get("last_report"):
        lines.append(f"Ultimo relatorio: {mission['last_report']}")
    return "\n".join(lines)


def _internal_event_knowledge_content(event):
    lines = [
        f"Evento interno: {event.get('summary')}",
        f"Status: {event.get('status')}",
        f"Inicio: {event.get('start_at')}",
        f"Fim: {event.get('end_at')}",
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


def _upsert_knowledge_item(
    cursor,
    user_id,
    source_type,
    source_id,
    title,
    content,
    metadata=None,
):
    now = datetime.utcnow().isoformat()
    vector = json.dumps(embed_text(content))
    cursor.execute(
        """
        INSERT INTO knowledge_items (
            user_id, source_type, source_id, title, content, embedding,
            metadata, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, source_type, source_id)
        DO UPDATE SET
            title = excluded.title,
            content = excluded.content,
            embedding = excluded.embedding,
            metadata = excluded.metadata,
            updated_at = excluded.updated_at
        """,
        (
            user_id,
            source_type,
            str(source_id),
            title,
            content,
            vector,
            json.dumps(metadata or {}),
            now,
            now,
        ),
    )
    if use_supabase_vector_store():
        try:
            supabase_upsert_knowledge_item(
                user_id,
                source_type,
                source_id,
                title,
                content,
                metadata=metadata,
            )
        except Exception as exc:
            if not supabase_fallback_to_sqlite():
                raise
            logger.warning("Supabase vector upsert failed; keeping SQLite fallback: %s", exc)


def _delete_knowledge_item(cursor, user_id, source_type, source_id):
    cursor.execute(
        """
        DELETE FROM knowledge_items
        WHERE user_id = ? AND source_type = ? AND source_id = ?
        """,
        (user_id, source_type, str(source_id)),
    )
    if use_supabase_vector_store():
        try:
            supabase_delete_knowledge_item(user_id, source_type, source_id)
        except Exception as exc:
            if not supabase_fallback_to_sqlite():
                raise
            logger.warning("Supabase vector delete failed; keeping SQLite fallback: %s", exc)


def _normalize_attendees(attendees):
    if not attendees:
        return []
    if isinstance(attendees, str):
        try:
            parsed = json.loads(attendees)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except ValueError:
            return [item.strip() for item in attendees.split(",") if item.strip()]
    return [str(item).strip() for item in attendees if str(item).strip()]


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_time(value):
    if not value:
        return None
    try:
        return time.fromisoformat(value)
    except ValueError:
        return None


def _parse_datetime(value):
    return parse_local_datetime(value)


def _row_to_internal_event(row):
    if not row:
        return None
    return {
        "id": row[0],
        "user_id": row[1],
        "chat_id": row[2],
        "summary": row[3],
        "start_at": row[4],
        "end_at": row[5],
        "description": row[6],
        "location": row[7],
        "attendees": _normalize_attendees(row[8]),
        "status": row[9],
        "reminder_minutes": row[10],
        "last_reminded_at": row[11],
        "created_at": row[12],
        "updated_at": row[13],
    }


def _task_sort_key(task):
    due_date = _parse_date(task.get("due_date")) or date.max
    due_time = _parse_time(task.get("due_time")) or time.max
    priority_rank = {"alta": 0, "media": 1, "normal": 2, "baixa": 3}
    priority = priority_rank.get(task.get("priority") or "normal", 2)
    return (task["is_completed"], due_date, due_time, priority, task["id"])


def _next_recurrence_date(due_date, recurrence):
    current = _parse_date(due_date)
    if not current or not recurrence:
        return None

    if recurrence == "diaria":
        return current + timedelta(days=1)
    if recurrence == "semanal":
        return current + timedelta(days=7)
    if recurrence == "mensal":
        month = current.month + 1
        year = current.year
        if month == 13:
            month = 1
            year += 1

        month_lengths = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                         31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        day = min(current.day, month_lengths[month - 1])
        return date(year, month, day)
    return None

def init_db():
    """Initialize the database with necessary tables."""
    conn = _connect()
    c = conn.cursor()

    # Tasks/Reminders table
    c.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT,
            priority TEXT DEFAULT 'normal',
            category TEXT,
            reminder_at TEXT,
            recurrence TEXT,
            completed_at TEXT,
            updated_at TEXT,
            last_reminded_at TEXT,
            due_time TEXT,
            is_completed BOOLEAN DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    _add_column_if_missing(c, "tasks", "priority", "priority TEXT DEFAULT 'normal'")
    _add_column_if_missing(c, "tasks", "category", "category TEXT")
    _add_column_if_missing(c, "tasks", "reminder_at", "reminder_at TEXT")
    _add_column_if_missing(c, "tasks", "recurrence", "recurrence TEXT")
    _add_column_if_missing(c, "tasks", "completed_at", "completed_at TEXT")
    _add_column_if_missing(c, "tasks", "updated_at", "updated_at TEXT")
    _add_column_if_missing(c, "tasks", "last_reminded_at", "last_reminded_at TEXT")
    _add_column_if_missing(c, "tasks", "due_time", "due_time TEXT")

    # Conversation history table for contextual memory
    c.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS knowledge_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding TEXT NOT NULL,
            metadata TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT
        )
    ''')

    c.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_source
        ON knowledge_items (user_id, source_type, source_id)
    ''')

    c.execute('''
        CREATE INDEX IF NOT EXISTS idx_knowledge_user
        ON knowledge_items (user_id, source_type)
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            chat_id INTEGER,
            daily_summary_enabled BOOLEAN DEFAULT 0,
            daily_summary_time TEXT DEFAULT '08:00',
            meeting_reminders_enabled BOOLEAN DEFAULT 1,
            meeting_reminder_minutes INTEGER DEFAULT 15,
            last_daily_summary_date TEXT,
            updated_at TEXT
        )
    ''')
    _add_column_if_missing(c, "user_settings", "meeting_reminder_minutes", "meeting_reminder_minutes INTEGER DEFAULT 15")

    c.execute('''
        CREATE TABLE IF NOT EXISTS authorized_users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            note TEXT,
            is_active BOOLEAN DEFAULT 1,
            source TEXT DEFAULT 'admin',
            last_seen_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT
        )
    ''')
    _add_column_if_missing(c, "authorized_users", "username", "username TEXT")
    _add_column_if_missing(c, "authorized_users", "full_name", "full_name TEXT")
    _add_column_if_missing(c, "authorized_users", "note", "note TEXT")
    _add_column_if_missing(c, "authorized_users", "is_active", "is_active BOOLEAN DEFAULT 1")
    _add_column_if_missing(c, "authorized_users", "source", "source TEXT DEFAULT 'admin'")
    _add_column_if_missing(c, "authorized_users", "last_seen_at", "last_seen_at TEXT")
    _add_column_if_missing(c, "authorized_users", "updated_at", "updated_at TEXT")

    c.execute('''
        CREATE TABLE IF NOT EXISTS pending_calendar_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            summary TEXT NOT NULL,
            start_at TEXT NOT NULL,
            end_at TEXT NOT NULL,
            description TEXT,
            location TEXT,
            attendees TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    _add_column_if_missing(c, "pending_calendar_events", "location", "location TEXT")
    _add_column_if_missing(c, "pending_calendar_events", "attendees", "attendees TEXT")

    c.execute('''
        CREATE TABLE IF NOT EXISTS calendar_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event_key TEXT NOT NULL,
            reminded_at TEXT NOT NULL,
            UNIQUE(user_id, event_key)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS internal_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            summary TEXT NOT NULL,
            start_at TEXT NOT NULL,
            end_at TEXT NOT NULL,
            description TEXT,
            location TEXT,
            attendees TEXT,
            status TEXT DEFAULT 'scheduled',
            reminder_minutes INTEGER DEFAULT 15,
            last_reminded_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT
        )
    ''')
    _add_column_if_missing(c, "internal_events", "description", "description TEXT")
    _add_column_if_missing(c, "internal_events", "location", "location TEXT")
    _add_column_if_missing(c, "internal_events", "attendees", "attendees TEXT")
    _add_column_if_missing(c, "internal_events", "status", "status TEXT DEFAULT 'scheduled'")
    _add_column_if_missing(c, "internal_events", "reminder_minutes", "reminder_minutes INTEGER DEFAULT 15")
    _add_column_if_missing(c, "internal_events", "last_reminded_at", "last_reminded_at TEXT")
    _add_column_if_missing(c, "internal_events", "updated_at", "updated_at TEXT")

    c.execute('''
        CREATE INDEX IF NOT EXISTS idx_internal_events_user_time
        ON internal_events (user_id, status, start_at)
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS email_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            email_id TEXT NOT NULL,
            thread_id TEXT,
            to_email TEXT,
            original_from TEXT,
            original_subject TEXT,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            instruction TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS missions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            goal TEXT NOT NULL,
            summary TEXT,
            status TEXT DEFAULT 'active',
            current_step INTEGER DEFAULT 1,
            last_report TEXT,
            completed_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT
        )
    ''')
    _add_column_if_missing(c, "missions", "summary", "summary TEXT")
    _add_column_if_missing(c, "missions", "current_step", "current_step INTEGER DEFAULT 1")
    _add_column_if_missing(c, "missions", "last_report", "last_report TEXT")
    _add_column_if_missing(c, "missions", "completed_at", "completed_at TEXT")
    _add_column_if_missing(c, "missions", "updated_at", "updated_at TEXT")

    c.execute('''
        CREATE INDEX IF NOT EXISTS idx_missions_user_status
        ON missions (user_id, status)
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS mission_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            step_number INTEGER NOT NULL,
            title TEXT NOT NULL,
            details TEXT,
            status TEXT DEFAULT 'pending',
            requires_confirmation BOOLEAN DEFAULT 0,
            confirmed_at TEXT,
            checkpoint_note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT,
            UNIQUE(mission_id, step_number)
        )
    ''')
    _add_column_if_missing(c, "mission_steps", "details", "details TEXT")
    _add_column_if_missing(c, "mission_steps", "status", "status TEXT DEFAULT 'pending'")
    _add_column_if_missing(c, "mission_steps", "requires_confirmation", "requires_confirmation BOOLEAN DEFAULT 0")
    _add_column_if_missing(c, "mission_steps", "confirmed_at", "confirmed_at TEXT")
    _add_column_if_missing(c, "mission_steps", "checkpoint_note", "checkpoint_note TEXT")
    _add_column_if_missing(c, "mission_steps", "updated_at", "updated_at TEXT")

    c.execute('''
        CREATE INDEX IF NOT EXISTS idx_mission_steps_mission
        ON mission_steps (mission_id, step_number)
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS mission_checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            step_number INTEGER,
            event_type TEXT NOT NULL,
            note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE INDEX IF NOT EXISTS idx_mission_checkpoints_mission
        ON mission_checkpoints (mission_id, created_at)
    ''')

    conn.commit()
    conn.close()

def add_task(
    user_id,
    title,
    description=None,
    due_date=None,
    priority="normal",
    category=None,
    reminder_at=None,
    recurrence=None,
    due_time=None,
):
    conn = _connect()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute(
        """
        INSERT INTO tasks (
            user_id, title, description, due_date, priority, category,
            reminder_at, recurrence, due_time, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            title,
            description,
            due_date,
            priority or "normal",
            category,
            reminder_at,
            recurrence,
            due_time,
            now,
        ),
    )
    conn.commit()
    task_id = c.lastrowid
    task = {
        "id": task_id,
        "title": title,
        "description": description,
        "due_date": due_date,
        "due_time": due_time,
        "priority": priority or "normal",
        "category": category,
        "reminder_at": reminder_at,
        "recurrence": recurrence,
        "is_completed": False,
    }
    _upsert_knowledge_item(
        c,
        user_id,
        "task",
        task_id,
        title,
        _task_knowledge_content(task),
        metadata={"task_id": task_id},
    )
    conn.commit()
    conn.close()
    return task_id

def get_tasks(user_id, pending_only=True, task_filter="pending", category=None, require_reminder=False):
    conn = _connect()
    c = conn.cursor()
    query = """
        SELECT
            id, user_id, title, description, due_date, is_completed, created_at,
            priority, category, reminder_at, recurrence, completed_at, updated_at,
            last_reminded_at, due_time
        FROM tasks
        WHERE user_id = ?
    """
    params = [user_id]

    if pending_only and task_filter not in {"completed", "concluidas", "all", "todas"}:
        query += " AND is_completed = 0"

    c.execute(query, params)
    tasks = [_row_to_task(row) for row in c.fetchall()]
    conn.close()

    today = local_date()
    now_time = local_now().time()
    normalized_filter = (task_filter or "pending").lower()

    if category:
        tasks = [
            task for task in tasks
            if (task.get("category") or "").lower() == category.lower()
        ]

    if require_reminder:
        tasks = [task for task in tasks if task.get("reminder_at")]

    if normalized_filter in {"today", "hoje"}:
        tasks = [
            task for task in tasks
            if _parse_date(task.get("due_date")) == today and not task["is_completed"]
        ]
    elif normalized_filter in {"week", "semana"}:
        week_end = today + timedelta(days=7)
        tasks = [
            task for task in tasks
            if not task["is_completed"]
            and (due := _parse_date(task.get("due_date"))) is not None
            and today <= due <= week_end
        ]
    elif normalized_filter in {"overdue", "atrasadas"}:
        tasks = [
            task for task in tasks
            if not task["is_completed"]
            and (
                (_parse_date(task.get("due_date")) is not None and _parse_date(task.get("due_date")) < today)
                or (
                    _parse_date(task.get("due_date")) == today
                    and _parse_time(task.get("due_time")) is not None
                    and _parse_time(task.get("due_time")) < now_time
                )
            )
        ]
    elif normalized_filter in {"completed", "concluidas"}:
        tasks = [task for task in tasks if task["is_completed"]]
    elif normalized_filter in {"all", "todas"}:
        pass

    tasks.sort(key=_task_sort_key)
    return tasks


def update_task(task_id, user_id, **updates):
    allowed_fields = {
        "title",
        "description",
        "due_date",
        "due_time",
        "priority",
        "category",
        "reminder_at",
        "recurrence",
    }
    filtered = {key: value for key, value in updates.items() if key in allowed_fields}
    if not filtered:
        return None

    conn = _connect()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    assignments = [f"{key} = ?" for key in filtered]
    params = list(filtered.values())
    if "reminder_at" in filtered:
        assignments.append("last_reminded_at = NULL")
    assignments.append("updated_at = ?")
    params.extend([now, task_id, user_id])
    c.execute(
        f"""
        UPDATE tasks
        SET {", ".join(assignments)}
        WHERE id = ? AND user_id = ?
        """,
        params,
    )
    if c.rowcount == 0:
        conn.commit()
        conn.close()
        return None

    c.execute(
        """
        SELECT
            id, user_id, title, description, due_date, is_completed, created_at,
            priority, category, reminder_at, recurrence, completed_at, updated_at,
            last_reminded_at, due_time
        FROM tasks
        WHERE id = ? AND user_id = ?
        """,
        (task_id, user_id),
    )
    task = _row_to_task(c.fetchone())
    _upsert_knowledge_item(
        c,
        user_id,
        "task",
        task_id,
        task["title"],
        _task_knowledge_content(task),
        metadata={"task_id": task_id},
    )
    conn.commit()
    conn.close()
    return task


def delete_task(task_id, user_id):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """
        SELECT
            id, user_id, title, description, due_date, is_completed, created_at,
            priority, category, reminder_at, recurrence, completed_at, updated_at,
            last_reminded_at, due_time
        FROM tasks
        WHERE id = ? AND user_id = ?
        """,
        (task_id, user_id),
    )
    row = c.fetchone()
    if not row:
        conn.close()
        return None

    task = _row_to_task(row)
    c.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
    _delete_knowledge_item(c, user_id, "task", task_id)
    conn.commit()
    conn.close()
    return task


def complete_task_with_recurrence(task_id, user_id):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """
        SELECT
            id, user_id, title, description, due_date, is_completed, created_at,
            priority, category, reminder_at, recurrence, completed_at, updated_at,
            last_reminded_at, due_time
        FROM tasks
        WHERE id = ? AND user_id = ?
        """,
        (task_id, user_id),
    )
    row = c.fetchone()
    if not row:
        conn.close()
        return {"completed": False, "next_task_id": None}

    task = _row_to_task(row)
    completed_at = datetime.utcnow().isoformat()
    c.execute(
        """
        UPDATE tasks
        SET is_completed = 1, completed_at = ?, updated_at = ?
        WHERE id = ? AND user_id = ?
        """,
        (completed_at, completed_at, task_id, user_id),
    )
    completed_task = dict(task)
    completed_task["is_completed"] = True
    _upsert_knowledge_item(
        c,
        user_id,
        "task",
        task_id,
        task["title"],
        _task_knowledge_content(completed_task),
        metadata={"task_id": task_id},
    )

    next_task_id = None
    next_due = _next_recurrence_date(task.get("due_date"), task.get("recurrence"))
    if next_due:
        reminder_at = None
        if task.get("reminder_at"):
            reminder_time = _parse_datetime(task["reminder_at"])
            if reminder_time:
                reminder_at = datetime.combine(next_due, reminder_time.time()).isoformat(timespec="minutes")

        c.execute(
            """
            INSERT INTO tasks (
                user_id, title, description, due_date, priority, category,
                reminder_at, recurrence, due_time, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                task["title"],
                task["description"],
                next_due.isoformat(),
                task["priority"],
                task["category"],
                reminder_at,
                task["recurrence"],
                task["due_time"],
                completed_at,
            ),
        )
        next_task_id = c.lastrowid
        next_task = {
            "id": next_task_id,
            "title": task["title"],
            "description": task["description"],
            "due_date": next_due.isoformat(),
            "due_time": task["due_time"],
            "priority": task["priority"],
            "category": task["category"],
            "recurrence": task["recurrence"],
            "is_completed": False,
        }
        _upsert_knowledge_item(
            c,
            user_id,
            "task",
            next_task_id,
            task["title"],
            _task_knowledge_content(next_task),
            metadata={"task_id": next_task_id},
        )

    conn.commit()
    conn.close()
    return {"completed": True, "next_task_id": next_task_id}


def get_due_task_reminders(limit=50):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """
        SELECT
            id, user_id, title, description, due_date, is_completed, created_at,
            priority, category, reminder_at, recurrence, completed_at, updated_at,
            last_reminded_at, due_time
        FROM tasks
        WHERE is_completed = 0
            AND reminder_at IS NOT NULL
        ORDER BY reminder_at ASC
        LIMIT ?
        """,
        (max(limit * 20, 1000),),
    )
    rows = c.fetchall()
    conn.close()
    now = local_now()
    due = []
    for row in rows:
        task = _row_to_task(row)
        reminder_at = parse_local_datetime(task.get("reminder_at"))
        last_reminded_at = parse_local_datetime(task.get("last_reminded_at"))
        if not reminder_at:
            continue
        if reminder_at <= now and (last_reminded_at is None or last_reminded_at < reminder_at):
            due.append(task)
        if len(due) >= limit:
            break
    return due


def mark_task_reminded(task_id):
    conn = _connect()
    c = conn.cursor()
    reminded_at = local_now().isoformat(timespec="minutes")
    c.execute(
        "UPDATE tasks SET last_reminded_at = ?, updated_at = ? WHERE id = ?",
        (reminded_at, reminded_at, task_id),
    )
    conn.commit()
    conn.close()

def log_conversation(user_id: int, role: str, content: str):
    """Persist a conversation message for contextual memory."""
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO conversations (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (user_id, role, content, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()

def get_conversation_history(user_id: int, limit: int = 10):
    """Return the most recent conversation messages in chronological order."""
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """
        SELECT role, content
        FROM conversations
        WHERE user_id = ?
        ORDER BY datetime(created_at) DESC, id DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    rows = c.fetchall()
    conn.close()

    # Reverse to chronological order (oldest first)
    rows.reverse()
    return [
        {"role": role, "content": content}
        for role, content in rows
    ]

def add_memory(user_id: int, content: str):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO memories (user_id, content, created_at) VALUES (?, ?, ?)",
        (user_id, content, datetime.utcnow().isoformat()),
    )
    memory_id = c.lastrowid
    _upsert_knowledge_item(
        c,
        user_id,
        "memory",
        memory_id,
        f"Memoria {memory_id}",
        content,
        metadata={"memory_id": memory_id},
    )
    conn.commit()
    conn.close()
    return memory_id

def get_memories(user_id: int, limit: int = 20):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """
        SELECT id, content, created_at
        FROM memories
        WHERE user_id = ?
        ORDER BY datetime(created_at) DESC, id DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {"id": memory_id, "content": content, "created_at": created_at}
        for memory_id, content, created_at in rows
    ]

def delete_memory(memory_id: int, user_id: int):
    conn = _connect()
    c = conn.cursor()
    c.execute("DELETE FROM memories WHERE id = ? AND user_id = ?", (memory_id, user_id))
    rows_affected = c.rowcount
    if rows_affected:
        _delete_knowledge_item(c, user_id, "memory", memory_id)
    conn.commit()
    conn.close()
    return rows_affected > 0

def clear_memories(user_id: int):
    conn = _connect()
    c = conn.cursor()
    c.execute("DELETE FROM memories WHERE user_id = ?", (user_id,))
    rows_affected = c.rowcount
    c.execute(
        "DELETE FROM knowledge_items WHERE user_id = ? AND source_type = ?",
        (user_id, "memory"),
    )
    if use_supabase_vector_store():
        try:
            supabase_clear_knowledge_source(user_id, "memory")
        except Exception as exc:
            if not supabase_fallback_to_sqlite():
                raise
            logger.warning("Supabase vector clear failed; keeping SQLite fallback: %s", exc)
    conn.commit()
    conn.close()
    return rows_affected


def upsert_knowledge_item(
    user_id,
    source_type,
    source_id,
    title,
    content,
    metadata=None,
):
    conn = _connect()
    c = conn.cursor()
    _upsert_knowledge_item(c, user_id, source_type, source_id, title, content, metadata)
    conn.commit()
    conn.close()


def clear_knowledge_source(user_id, source_type):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "DELETE FROM knowledge_items WHERE user_id = ? AND source_type = ?",
        (user_id, source_type),
    )
    rows_affected = c.rowcount
    if use_supabase_vector_store():
        try:
            supabase_clear_knowledge_source(user_id, source_type)
        except Exception as exc:
            if not supabase_fallback_to_sqlite():
                raise
            logger.warning("Supabase vector clear failed; keeping SQLite fallback: %s", exc)
    conn.commit()
    conn.close()
    return rows_affected


def search_knowledge(user_id, query, limit=5, source_type=None, min_score=0.05):
    if use_supabase_vector_store():
        try:
            return supabase_search_knowledge(user_id, query, limit, source_type, min_score)
        except Exception as exc:
            if not supabase_fallback_to_sqlite():
                raise
            logger.warning("Supabase vector search failed; using SQLite fallback: %s", exc)

    conn = _connect()
    c = conn.cursor()
    sql = """
        SELECT id, user_id, source_type, source_id, title, content, embedding, metadata
        FROM knowledge_items
        WHERE user_id IN (?, ?)
    """
    params = [0, user_id]
    if source_type:
        sql += " AND source_type = ?"
        params.append(source_type)

    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()

    query_vector = embed_text(query)
    results = []
    for row in rows:
        try:
            vector = json.loads(row[6])
        except (TypeError, ValueError):
            continue
        score = cosine_similarity(query_vector, vector)
        if score < min_score:
            continue
        try:
            metadata = json.loads(row[7] or "{}")
        except ValueError:
            metadata = {}
        results.append({
            "id": row[0],
            "user_id": row[1],
            "source_type": row[2],
            "source_id": row[3],
            "title": row[4],
            "content": row[5],
            "score": score,
            "metadata": metadata,
        })

    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:limit]


def count_knowledge_items(user_id=None):
    if use_supabase_vector_store():
        try:
            return supabase_count_knowledge_items(user_id)
        except Exception as exc:
            if not supabase_fallback_to_sqlite():
                raise
            logger.warning("Supabase vector count failed; using SQLite fallback: %s", exc)

    conn = _connect()
    c = conn.cursor()
    if user_id is None:
        c.execute("SELECT COUNT(*) FROM knowledge_items")
    else:
        c.execute(
            "SELECT COUNT(*) FROM knowledge_items WHERE user_id IN (?, ?)",
            (0, user_id),
        )
    count = c.fetchone()[0]
    conn.close()
    return count


def get_knowledge_backend():
    return active_vector_backend()


def upsert_user_settings(
    user_id,
    chat_id=None,
    daily_summary_enabled=None,
    daily_summary_time=None,
    meeting_reminders_enabled=None,
    meeting_reminder_minutes=None,
    last_daily_summary_date=None,
):
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT user_id FROM user_settings WHERE user_id = ?", (user_id,))
    exists = c.fetchone() is not None
    now = datetime.utcnow().isoformat()

    if not exists:
        c.execute(
            """
            INSERT INTO user_settings (
                user_id, chat_id, daily_summary_enabled, daily_summary_time,
                meeting_reminders_enabled, meeting_reminder_minutes,
                last_daily_summary_date, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                chat_id,
                int(bool(daily_summary_enabled)) if daily_summary_enabled is not None else 0,
                daily_summary_time or "08:00",
                int(bool(meeting_reminders_enabled)) if meeting_reminders_enabled is not None else 1,
                meeting_reminder_minutes or 15,
                last_daily_summary_date,
                now,
            ),
        )
    else:
        updates = []
        params = []
        values = {
            "chat_id": chat_id,
            "daily_summary_enabled": int(bool(daily_summary_enabled)) if daily_summary_enabled is not None else None,
            "daily_summary_time": daily_summary_time,
            "meeting_reminders_enabled": (
                int(bool(meeting_reminders_enabled)) if meeting_reminders_enabled is not None else None
            ),
            "meeting_reminder_minutes": meeting_reminder_minutes,
            "last_daily_summary_date": last_daily_summary_date,
        }
        for column, value in values.items():
            if value is not None:
                updates.append(f"{column} = ?")
                params.append(value)
        updates.append("updated_at = ?")
        params.append(now)
        params.append(user_id)
        c.execute(
            f"UPDATE user_settings SET {', '.join(updates)} WHERE user_id = ?",
            params,
        )

    conn.commit()
    conn.close()


def get_user_settings(user_id):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """
        SELECT user_id, chat_id, daily_summary_enabled, daily_summary_time,
               meeting_reminders_enabled, meeting_reminder_minutes, last_daily_summary_date
        FROM user_settings
        WHERE user_id = ?
        """,
        (user_id,),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "user_id": row[0],
        "chat_id": row[1],
        "daily_summary_enabled": bool(row[2]),
        "daily_summary_time": row[3],
        "meeting_reminders_enabled": bool(row[4]),
        "meeting_reminder_minutes": row[5] or 15,
        "last_daily_summary_date": row[6],
    }


def list_user_settings(limit=100):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """
        SELECT user_id, chat_id, daily_summary_enabled, daily_summary_time,
               meeting_reminders_enabled, meeting_reminder_minutes,
               last_daily_summary_date
        FROM user_settings
        ORDER BY user_id ASC
        LIMIT ?
        """,
        (limit,),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {
            "user_id": row[0],
            "chat_id": row[1],
            "daily_summary_enabled": bool(row[2]),
            "daily_summary_time": row[3],
            "meeting_reminders_enabled": bool(row[4]),
            "meeting_reminder_minutes": row[5] or 15,
            "last_daily_summary_date": row[6],
        }
        for row in rows
    ]


def get_users_for_daily_summary(current_time):
    conn = _connect()
    c = conn.cursor()
    today = local_date().isoformat()
    c.execute(
        """
        SELECT user_id, chat_id, daily_summary_time
        FROM user_settings
        WHERE daily_summary_enabled = 1
            AND chat_id IS NOT NULL
            AND daily_summary_time <= ?
            AND (last_daily_summary_date IS NULL OR last_daily_summary_date < ?)
        """,
        (current_time, today),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {"user_id": row[0], "chat_id": row[1], "daily_summary_time": row[2]}
        for row in rows
    ]


def get_users_with_meeting_reminders():
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """
        SELECT user_id, chat_id, meeting_reminder_minutes
        FROM user_settings
        WHERE meeting_reminders_enabled = 1 AND chat_id IS NOT NULL
        """
    )
    rows = c.fetchall()
    conn.close()
    return [
        {"user_id": row[0], "chat_id": row[1], "meeting_reminder_minutes": row[2] or 15}
        for row in rows
    ]


def upsert_authorized_user(
    user_id,
    username=None,
    full_name=None,
    note=None,
    is_active=True,
    source="admin",
    mark_seen=False,
):
    conn = _connect()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute("SELECT user_id FROM authorized_users WHERE user_id = ?", (user_id,))
    exists = c.fetchone() is not None
    if exists:
        updates = []
        params = []
        values = {
            "username": username,
            "full_name": full_name,
            "note": note,
            "is_active": int(bool(is_active)) if is_active is not None else None,
            "source": source,
            "last_seen_at": now if mark_seen else None,
        }
        for column, value in values.items():
            if value is not None:
                updates.append(f"{column} = ?")
                params.append(value)
        updates.append("updated_at = ?")
        params.append(now)
        params.append(user_id)
        c.execute(
            f"UPDATE authorized_users SET {', '.join(updates)} WHERE user_id = ?",
            params,
        )
    else:
        c.execute(
            """
            INSERT INTO authorized_users (
                user_id, username, full_name, note, is_active, source,
                last_seen_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                username,
                full_name,
                note,
                int(bool(is_active)),
                source,
                now if mark_seen else None,
                now,
                now,
            ),
        )
    conn.commit()
    conn.close()


def observe_authorized_user(user_id, username=None, full_name=None):
    conn = _connect()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute("SELECT user_id FROM authorized_users WHERE user_id = ?", (user_id,))
    if c.fetchone():
        c.execute(
            """
            UPDATE authorized_users
            SET username = COALESCE(?, username),
                full_name = COALESCE(?, full_name),
                last_seen_at = ?,
                updated_at = ?
            WHERE user_id = ?
            """,
            (username, full_name, now, now, user_id),
        )
    else:
        c.execute(
            """
            INSERT INTO authorized_users (
                user_id, username, full_name, is_active, source,
                last_seen_at, created_at, updated_at
            )
            VALUES (?, ?, ?, 0, 'observed', ?, ?, ?)
            """,
            (user_id, username, full_name, now, now, now),
        )
    conn.commit()
    conn.close()


def get_authorized_user(user_id):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """
        SELECT user_id, username, full_name, note, is_active, source,
               last_seen_at, created_at, updated_at
        FROM authorized_users
        WHERE user_id = ?
        """,
        (user_id,),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "user_id": row[0],
        "username": row[1],
        "full_name": row[2],
        "note": row[3],
        "is_active": bool(row[4]),
        "source": row[5],
        "last_seen_at": row[6],
        "created_at": row[7],
        "updated_at": row[8],
    }


def list_authorized_users(limit=100):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """
        SELECT user_id, username, full_name, note, is_active, source,
               last_seen_at, created_at, updated_at
        FROM authorized_users
        ORDER BY is_active DESC, datetime(COALESCE(last_seen_at, updated_at, created_at)) DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {
            "user_id": row[0],
            "username": row[1],
            "full_name": row[2],
            "note": row[3],
            "is_active": bool(row[4]),
            "source": row[5],
            "last_seen_at": row[6],
            "created_at": row[7],
            "updated_at": row[8],
        }
        for row in rows
    ]


def is_authorized_user_active(user_id):
    user = get_authorized_user(user_id)
    return bool(user and user["is_active"])


def add_pending_calendar_event(
    user_id,
    chat_id,
    summary,
    start_at,
    end_at,
    description=None,
    location=None,
    attendees=None,
):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO pending_calendar_events (
            user_id, chat_id, summary, start_at, end_at, description, location, attendees
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            chat_id,
            summary,
            start_at,
            end_at,
            description,
            location,
            json.dumps(_normalize_attendees(attendees)),
        ),
    )
    conn.commit()
    event_id = c.lastrowid
    conn.close()
    return event_id


def get_pending_calendar_event(event_id, user_id):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """
        SELECT id, user_id, chat_id, summary, start_at, end_at, description, location, attendees
        FROM pending_calendar_events
        WHERE id = ? AND user_id = ?
        """,
        (event_id, user_id),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "user_id": row[1],
        "chat_id": row[2],
        "summary": row[3],
        "start_at": row[4],
        "end_at": row[5],
        "description": row[6],
        "location": row[7],
        "attendees": _normalize_attendees(row[8]),
    }


def delete_pending_calendar_event(event_id, user_id):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "DELETE FROM pending_calendar_events WHERE id = ? AND user_id = ?",
        (event_id, user_id),
    )
    rows_affected = c.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0


def add_internal_event(
    user_id,
    chat_id,
    summary,
    start_at,
    end_at,
    description=None,
    location=None,
    attendees=None,
    reminder_minutes=15,
):
    conn = _connect()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    normalized_attendees = _normalize_attendees(attendees)
    c.execute(
        """
        INSERT INTO internal_events (
            user_id, chat_id, summary, start_at, end_at, description, location,
            attendees, status, reminder_minutes, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'scheduled', ?, ?)
        """,
        (
            user_id,
            chat_id,
            summary,
            start_at,
            end_at,
            description,
            location,
            json.dumps(normalized_attendees),
            reminder_minutes,
            now,
        ),
    )
    event_id = c.lastrowid
    event = {
        "id": event_id,
        "user_id": user_id,
        "chat_id": chat_id,
        "summary": summary,
        "start_at": start_at,
        "end_at": end_at,
        "description": description,
        "location": location,
        "attendees": normalized_attendees,
        "status": "scheduled",
        "reminder_minutes": reminder_minutes,
    }
    _upsert_knowledge_item(
        c,
        user_id,
        "internal_event",
        event_id,
        summary,
        _internal_event_knowledge_content(event),
        metadata={"internal_event_id": event_id, "status": "scheduled"},
    )
    conn.commit()
    conn.close()
    return event_id


def get_internal_event(event_id, user_id):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """
        SELECT id, user_id, chat_id, summary, start_at, end_at, description,
               location, attendees, status, reminder_minutes, last_reminded_at,
               created_at, updated_at
        FROM internal_events
        WHERE id = ? AND user_id = ?
        """,
        (event_id, user_id),
    )
    event = _row_to_internal_event(c.fetchone())
    conn.close()
    return event


def list_internal_events(user_id, event_filter="upcoming", limit=20):
    conn = _connect()
    c = conn.cursor()
    query = """
        SELECT id, user_id, chat_id, summary, start_at, end_at, description,
               location, attendees, status, reminder_minutes, last_reminded_at,
               created_at, updated_at
        FROM internal_events
        WHERE user_id = ?
    """
    params = [user_id]
    normalized_filter = (event_filter or "upcoming").lower()

    if normalized_filter not in {"all", "todas", "cancelled", "cancelados"}:
        query += " AND status = 'scheduled'"
    elif normalized_filter in {"cancelled", "cancelados"}:
        query += " AND status = 'cancelled'"

    query += " ORDER BY datetime(start_at) ASC, id ASC LIMIT ?"
    params.append(max(limit * 20, 1000))
    c.execute(query, params)
    events = [_row_to_internal_event(row) for row in c.fetchall()]
    conn.close()

    now = local_now()
    today = local_date()
    week_end = today + timedelta(days=7)

    if normalized_filter in {"today", "hoje"}:
        events = [
            event for event in events
            if (_parse_datetime(event["start_at"]) or datetime.min).date() == today
        ]
    elif normalized_filter in {"week", "semana"}:
        events = [
            event for event in events
            if today <= (_parse_datetime(event["start_at"]) or datetime.max).date() <= week_end
        ]
    elif normalized_filter in {"past", "passados"}:
        events = [
            event for event in events
            if (_parse_datetime(event["end_at"]) or datetime.max.replace(tzinfo=now.tzinfo)) < now
        ]
    elif normalized_filter in {"upcoming", "proximos", "próximos"}:
        events = [
            event for event in events
            if (_parse_datetime(event["end_at"]) or datetime.max.replace(tzinfo=now.tzinfo)) >= now
        ]

    return events[:limit]


def get_internal_events_between(user_id, start_dt, end_dt, limit=50):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """
        SELECT id, user_id, chat_id, summary, start_at, end_at, description,
               location, attendees, status, reminder_minutes, last_reminded_at,
               created_at, updated_at
        FROM internal_events
        WHERE user_id = ? AND status = 'scheduled'
        ORDER BY datetime(start_at) ASC, id ASC
        LIMIT ?
        """,
        (user_id, max(limit * 20, 1000)),
    )
    rows = c.fetchall()
    conn.close()
    events = [_row_to_internal_event(row) for row in rows]
    conflicts = []
    for event in events:
        event_start = _parse_datetime(event["start_at"])
        event_end = _parse_datetime(event["end_at"])
        if event_start and event_end and event_start < end_dt and start_dt < event_end:
            conflicts.append(event)
    return conflicts


def cancel_internal_event(event_id, user_id):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """
        SELECT id, user_id, chat_id, summary, start_at, end_at, description,
               location, attendees, status, reminder_minutes, last_reminded_at,
               created_at, updated_at
        FROM internal_events
        WHERE id = ? AND user_id = ?
        """,
        (event_id, user_id),
    )
    event = _row_to_internal_event(c.fetchone())
    if not event:
        conn.close()
        return False

    now = datetime.utcnow().isoformat()
    c.execute(
        """
        UPDATE internal_events
        SET status = 'cancelled', updated_at = ?
        WHERE id = ? AND user_id = ?
        """,
        (now, event_id, user_id),
    )
    event["status"] = "cancelled"
    event["updated_at"] = now
    _upsert_knowledge_item(
        c,
        user_id,
        "internal_event",
        event_id,
        event["summary"],
        _internal_event_knowledge_content(event),
        metadata={"internal_event_id": event_id, "status": "cancelled"},
    )
    conn.commit()
    conn.close()
    return True


def get_due_internal_event_reminders(limit=50):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """
        SELECT e.id, e.user_id, e.chat_id, e.summary, e.start_at, e.end_at,
               e.description, e.location, e.attendees, e.status,
               e.reminder_minutes, e.last_reminded_at, e.created_at, e.updated_at
        FROM internal_events AS e
        LEFT JOIN user_settings AS s ON s.user_id = e.user_id
        WHERE e.status = 'scheduled'
            AND e.chat_id IS NOT NULL
            AND e.last_reminded_at IS NULL
            AND COALESCE(s.meeting_reminders_enabled, 1) = 1
        ORDER BY datetime(e.start_at) ASC, e.id ASC
        LIMIT ?
        """,
        (limit * 4,),
    )
    events = [_row_to_internal_event(row) for row in c.fetchall()]
    conn.close()

    now = local_now()
    due = []
    for event in events:
        start_at = _parse_datetime(event["start_at"])
        if not start_at:
            continue
        reminder_minutes = event.get("reminder_minutes")
        if reminder_minutes is None:
            reminder_minutes = 15
        remind_at = start_at - timedelta(minutes=reminder_minutes)
        if remind_at <= now <= start_at + timedelta(minutes=1):
            due.append(event)
        if len(due) >= limit:
            break
    return due


def mark_internal_event_reminded(event_id):
    conn = _connect()
    c = conn.cursor()
    reminded_at = local_now().isoformat(timespec="minutes")
    c.execute(
        "UPDATE internal_events SET last_reminded_at = ?, updated_at = ? WHERE id = ?",
        (reminded_at, reminded_at, event_id),
    )
    conn.commit()
    conn.close()


def mark_calendar_event_reminded(user_id, event_key):
    conn = _connect()
    c = conn.cursor()
    try:
        c.execute(
            """
            INSERT INTO calendar_reminders (user_id, event_key, reminded_at)
            VALUES (?, ?, ?)
            """,
            (user_id, event_key, datetime.utcnow().isoformat()),
        )
        conn.commit()
        inserted = True
    except sqlite3.IntegrityError:
        inserted = False
    conn.close()
    return inserted


def add_email_draft(
    user_id,
    email_id,
    thread_id,
    to_email,
    original_from,
    original_subject,
    subject,
    body,
    instruction=None,
):
    conn = _connect()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute(
        """
        INSERT INTO email_drafts (
            user_id, email_id, thread_id, to_email, original_from, original_subject,
            subject, body, instruction, status, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """,
        (
            user_id,
            email_id,
            thread_id,
            to_email,
            original_from,
            original_subject,
            subject,
            body,
            instruction,
            now,
        ),
    )
    draft_id = c.lastrowid
    draft = {
        "id": draft_id,
        "user_id": user_id,
        "email_id": email_id,
        "thread_id": thread_id,
        "to_email": to_email,
        "original_from": original_from,
        "original_subject": original_subject,
        "subject": subject,
        "body": body,
        "instruction": instruction,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
    }
    _upsert_knowledge_item(
        c,
        user_id,
        "email_draft",
        draft_id,
        subject,
        _email_draft_knowledge_content(draft),
        metadata={"draft_id": draft_id, "email_id": email_id, "status": "pending"},
    )
    conn.commit()
    conn.close()
    return draft_id


def _row_to_email_draft(row):
    return {
        "id": row[0],
        "user_id": row[1],
        "email_id": row[2],
        "thread_id": row[3],
        "to_email": row[4],
        "original_from": row[5],
        "original_subject": row[6],
        "subject": row[7],
        "body": row[8],
        "instruction": row[9],
        "status": row[10],
        "created_at": row[11],
        "updated_at": row[12],
    }


def get_email_draft(draft_id, user_id):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """
        SELECT id, user_id, email_id, thread_id, to_email, original_from,
               original_subject, subject, body, instruction, status, created_at, updated_at
        FROM email_drafts
        WHERE id = ? AND user_id = ?
        """,
        (draft_id, user_id),
    )
    row = c.fetchone()
    conn.close()
    return _row_to_email_draft(row) if row else None


def get_email_drafts(user_id, status="pending", limit=10):
    conn = _connect()
    c = conn.cursor()
    query = """
        SELECT id, user_id, email_id, thread_id, to_email, original_from,
               original_subject, subject, body, instruction, status, created_at, updated_at
        FROM email_drafts
        WHERE user_id = ?
    """
    params = [user_id]
    if status and status != "all":
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY datetime(created_at) DESC, id DESC LIMIT ?"
    params.append(limit)
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return [_row_to_email_draft(row) for row in rows]


def update_email_draft_status(draft_id, user_id, status):
    conn = _connect()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute(
        """
        UPDATE email_drafts
        SET status = ?, updated_at = ?
        WHERE id = ? AND user_id = ?
        """,
        (status, now, draft_id, user_id),
    )
    rows_affected = c.rowcount
    if rows_affected:
        c.execute(
            """
            SELECT id, user_id, email_id, thread_id, to_email, original_from,
                   original_subject, subject, body, instruction, status, created_at, updated_at
            FROM email_drafts
            WHERE id = ? AND user_id = ?
            """,
            (draft_id, user_id),
        )
        draft = _row_to_email_draft(c.fetchone())
        _upsert_knowledge_item(
            c,
            user_id,
            "email_draft",
            draft_id,
            draft["subject"],
            _email_draft_knowledge_content(draft),
            metadata={"draft_id": draft_id, "email_id": draft["email_id"], "status": status},
        )
    conn.commit()
    conn.close()
    return rows_affected > 0


def _row_to_mission(row):
    if not row:
        return None
    return {
        "id": row[0],
        "user_id": row[1],
        "goal": row[2],
        "summary": row[3],
        "status": row[4],
        "current_step": row[5],
        "last_report": row[6],
        "completed_at": row[7],
        "created_at": row[8],
        "updated_at": row[9],
    }


def _row_to_mission_step(row):
    if not row:
        return None
    return {
        "id": row[0],
        "mission_id": row[1],
        "user_id": row[2],
        "step_number": row[3],
        "title": row[4],
        "details": row[5],
        "status": row[6],
        "requires_confirmation": bool(row[7]),
        "confirmed_at": row[8],
        "checkpoint_note": row[9],
        "created_at": row[10],
        "updated_at": row[11],
    }


def _row_to_mission_checkpoint(row):
    if not row:
        return None
    return {
        "id": row[0],
        "mission_id": row[1],
        "user_id": row[2],
        "step_number": row[3],
        "event_type": row[4],
        "note": row[5],
        "created_at": row[6],
    }


def _get_mission_for_cursor(cursor, user_id, mission_id):
    cursor.execute(
        """
        SELECT id, user_id, goal, summary, status, current_step,
               last_report, completed_at, created_at, updated_at
        FROM missions
        WHERE id = ? AND user_id = ?
        """,
        (mission_id, user_id),
    )
    return _row_to_mission(cursor.fetchone())


def _get_mission_steps_for_cursor(cursor, user_id, mission_id):
    cursor.execute(
        """
        SELECT id, mission_id, user_id, step_number, title, details, status,
               requires_confirmation, confirmed_at, checkpoint_note, created_at, updated_at
        FROM mission_steps
        WHERE mission_id = ? AND user_id = ?
        ORDER BY step_number ASC
        """,
        (mission_id, user_id),
    )
    return [_row_to_mission_step(row) for row in cursor.fetchall()]


def _get_mission_step_for_cursor(cursor, user_id, mission_id, step_number):
    cursor.execute(
        """
        SELECT id, mission_id, user_id, step_number, title, details, status,
               requires_confirmation, confirmed_at, checkpoint_note, created_at, updated_at
        FROM mission_steps
        WHERE mission_id = ? AND user_id = ? AND step_number = ?
        """,
        (mission_id, user_id, step_number),
    )
    return _row_to_mission_step(cursor.fetchone())


def _add_mission_checkpoint(cursor, user_id, mission_id, step_number, event_type, note=None):
    cursor.execute(
        """
        INSERT INTO mission_checkpoints (
            mission_id, user_id, step_number, event_type, note, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (mission_id, user_id, step_number, event_type, note, datetime.utcnow().isoformat()),
    )


def _refresh_mission_knowledge(cursor, user_id, mission_id):
    mission = _get_mission_for_cursor(cursor, user_id, mission_id)
    if not mission:
        return
    steps = _get_mission_steps_for_cursor(cursor, user_id, mission_id)
    _upsert_knowledge_item(
        cursor,
        user_id,
        "mission",
        mission_id,
        f"Missao {mission_id}: {mission['goal'][:80]}",
        _mission_knowledge_content(mission, steps),
        metadata={
            "mission_id": mission_id,
            "status": mission["status"],
            "current_step": mission.get("current_step"),
        },
    )


def create_mission(user_id, goal, steps, summary=None):
    conn = _connect()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute(
        """
        INSERT INTO missions (
            user_id, goal, summary, status, current_step, updated_at
        )
        VALUES (?, ?, ?, 'active', 1, ?)
        """,
        (user_id, goal, summary, now),
    )
    mission_id = c.lastrowid

    normalized_steps = steps or []
    if not normalized_steps:
        normalized_steps = [{"title": "Definir o proximo passo", "details": goal}]

    for index, step in enumerate(normalized_steps, start=1):
        if isinstance(step, dict):
            title = str(step.get("title") or step.get("step") or "").strip()
            details = str(step.get("details") or step.get("description") or "").strip() or None
            requires_confirmation = bool(step.get("requires_confirmation"))
        else:
            title = str(step).strip()
            details = None
            requires_confirmation = False

        c.execute(
            """
            INSERT INTO mission_steps (
                mission_id, user_id, step_number, title, details,
                status, requires_confirmation, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                mission_id,
                user_id,
                index,
                title or f"Passo {index}",
                details,
                int(requires_confirmation),
                now,
            ),
        )

    _add_mission_checkpoint(c, user_id, mission_id, None, "created", "Missao criada.")
    _refresh_mission_knowledge(c, user_id, mission_id)
    conn.commit()
    conn.close()
    return mission_id


def get_mission(user_id, mission_id, include_checkpoints=True):
    conn = _connect()
    c = conn.cursor()
    mission = _get_mission_for_cursor(c, user_id, mission_id)
    if not mission:
        conn.close()
        return None

    mission["steps"] = _get_mission_steps_for_cursor(c, user_id, mission_id)
    if include_checkpoints:
        c.execute(
            """
            SELECT id, mission_id, user_id, step_number, event_type, note, created_at
            FROM mission_checkpoints
            WHERE mission_id = ? AND user_id = ?
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT 10
            """,
            (mission_id, user_id),
        )
        rows = c.fetchall()
        mission["checkpoints"] = [_row_to_mission_checkpoint(row) for row in rows]
    conn.close()
    return mission


def list_missions(user_id, status="active", limit=10):
    conn = _connect()
    c = conn.cursor()
    query = """
        SELECT
            m.id, m.user_id, m.goal, m.summary, m.status, m.current_step,
            m.last_report, m.completed_at, m.created_at, m.updated_at,
            COUNT(s.id) AS total_steps,
            COALESCE(SUM(CASE WHEN s.status = 'done' THEN 1 ELSE 0 END), 0) AS done_steps
        FROM missions AS m
        LEFT JOIN mission_steps AS s ON s.mission_id = m.id AND s.user_id = m.user_id
        WHERE m.user_id = ?
    """
    params = [user_id]
    if status and status != "all":
        query += " AND m.status = ?"
        params.append(status)
    query += """
        GROUP BY m.id
        ORDER BY datetime(m.updated_at) DESC, m.id DESC
        LIMIT ?
    """
    params.append(limit)
    c.execute(query, params)
    missions = []
    for row in c.fetchall():
        mission = _row_to_mission(row[:10])
        mission["total_steps"] = row[10]
        mission["done_steps"] = row[11]
        missions.append(mission)
    conn.close()
    return missions


def update_mission_status(user_id, mission_id, status, note=None):
    conn = _connect()
    c = conn.cursor()
    mission = _get_mission_for_cursor(c, user_id, mission_id)
    if not mission:
        conn.close()
        return False

    now = datetime.utcnow().isoformat()
    completed_at = now if status == "completed" else None
    if status == "completed":
        c.execute(
            """
            UPDATE missions
            SET status = ?, completed_at = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (status, completed_at, now, mission_id, user_id),
        )
    else:
        c.execute(
            """
            UPDATE missions
            SET status = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (status, now, mission_id, user_id),
        )
    _add_mission_checkpoint(c, user_id, mission_id, None, f"mission_{status}", note)
    _refresh_mission_knowledge(c, user_id, mission_id)
    conn.commit()
    conn.close()
    return True


def confirm_mission_step(user_id, mission_id, step_number, note=None):
    conn = _connect()
    c = conn.cursor()
    step = _get_mission_step_for_cursor(c, user_id, mission_id, step_number)
    if not step:
        conn.close()
        return {"confirmed": False, "not_found": True}

    now = datetime.utcnow().isoformat()
    c.execute(
        """
        UPDATE mission_steps
        SET confirmed_at = ?, updated_at = ?
        WHERE mission_id = ? AND user_id = ? AND step_number = ?
        """,
        (now, now, mission_id, user_id, step_number),
    )
    _add_mission_checkpoint(
        c,
        user_id,
        mission_id,
        step_number,
        "confirmed",
        note or "Passo sensivel confirmado pelo usuario.",
    )
    _refresh_mission_knowledge(c, user_id, mission_id)
    conn.commit()
    conn.close()
    return {"confirmed": True}


def update_mission_step(user_id, mission_id, step_number, status, note=None):
    conn = _connect()
    c = conn.cursor()
    step = _get_mission_step_for_cursor(c, user_id, mission_id, step_number)
    if not step:
        conn.close()
        return {"updated": False, "not_found": True}

    if (
        status in {"in_progress", "done"}
        and step["requires_confirmation"]
        and not step.get("confirmed_at")
    ):
        conn.close()
        return {"updated": False, "needs_confirmation": True, "step": step}

    now = datetime.utcnow().isoformat()
    c.execute(
        """
        UPDATE mission_steps
        SET status = ?, checkpoint_note = COALESCE(?, checkpoint_note), updated_at = ?
        WHERE mission_id = ? AND user_id = ? AND step_number = ?
        """,
        (status, note, now, mission_id, user_id, step_number),
    )
    _add_mission_checkpoint(c, user_id, mission_id, step_number, f"step_{status}", note)

    if status in {"in_progress", "blocked"}:
        c.execute(
            """
            UPDATE missions
            SET current_step = ?, status = 'active', updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (step_number, now, mission_id, user_id),
        )
    elif status in {"done", "skipped"}:
        c.execute(
            """
            SELECT step_number
            FROM mission_steps
            WHERE mission_id = ? AND user_id = ?
              AND status NOT IN ('done', 'skipped')
            ORDER BY step_number ASC
            LIMIT 1
            """,
            (mission_id, user_id),
        )
        next_row = c.fetchone()
        if next_row:
            c.execute(
                """
                UPDATE missions
                SET current_step = ?, status = 'active', updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (next_row[0], now, mission_id, user_id),
            )
        else:
            c.execute(
                """
                UPDATE missions
                SET status = 'completed', completed_at = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (now, now, mission_id, user_id),
            )

    _refresh_mission_knowledge(c, user_id, mission_id)
    conn.commit()
    conn.close()
    return {"updated": True}


def save_mission_report(user_id, mission_id, report):
    conn = _connect()
    c = conn.cursor()
    mission = _get_mission_for_cursor(c, user_id, mission_id)
    if not mission:
        conn.close()
        return False

    now = datetime.utcnow().isoformat()
    c.execute(
        """
        UPDATE missions
        SET last_report = ?, updated_at = ?
        WHERE id = ? AND user_id = ?
        """,
        (report, now, mission_id, user_id),
    )
    _add_mission_checkpoint(c, user_id, mission_id, None, "report", report[:500])
    _refresh_mission_knowledge(c, user_id, mission_id)
    conn.commit()
    conn.close()
    return True


def get_operational_counts():
    conn = _connect()
    c = conn.cursor()
    tables = [
        "tasks",
        "internal_events",
        "memories",
        "knowledge_items",
        "missions",
        "mission_steps",
        "email_drafts",
        "user_settings",
        "authorized_users",
    ]
    counts = {}
    for table in tables:
        try:
            c.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = c.fetchone()[0]
        except sqlite3.Error:
            counts[table] = None
    conn.close()
    return counts


def create_database_backup(backup_dir=None):
    source_path = Path(_db_path())
    selected_backup_dir = Path(backup_dir or os.getenv("ADMIN_PANEL_BACKUP_DIR", "data/backups"))
    selected_backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    backup_path = selected_backup_dir / f"bot_data-{timestamp}.db"

    source_conn = _connect()
    try:
        dest_conn = sqlite3.connect(backup_path)
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        source_conn.close()

    return {
        "path": str(backup_path),
        "source_path": str(source_path),
        "size_bytes": backup_path.stat().st_size,
        "created_at": timestamp,
    }


def list_database_backups(backup_dir=None, limit=20):
    selected_backup_dir = Path(backup_dir or os.getenv("ADMIN_PANEL_BACKUP_DIR", "data/backups"))
    if not selected_backup_dir.exists():
        return []
    backups = []
    for path in selected_backup_dir.glob("*.db"):
        try:
            stat = path.stat()
        except OSError:
            continue
        backups.append({
            "name": path.name,
            "path": str(path),
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        })
    backups.sort(key=lambda item: item["modified_at"], reverse=True)
    return backups[:limit]
