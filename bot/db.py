import json
import os
import shutil
import sqlite3
from pathlib import Path
from datetime import date, datetime, time, timedelta

from dotenv import load_dotenv
from bot.rag import cosine_similarity, embed_text

load_dotenv()


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


def _delete_knowledge_item(cursor, user_id, source_type, source_id):
    cursor.execute(
        """
        DELETE FROM knowledge_items
        WHERE user_id = ? AND source_type = ? AND source_id = ?
        """,
        (user_id, source_type, str(source_id)),
    )


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
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


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

def get_tasks(user_id, pending_only=True, task_filter="pending", category=None):
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

    today = date.today()
    now_time = datetime.now().time()
    normalized_filter = (task_filter or "pending").lower()

    if category:
        tasks = [
            task for task in tasks
            if (task.get("category") or "").lower() == category.lower()
        ]

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

def complete_task(task_id, user_id):
    conn = _connect()
    c = conn.cursor()
    completed_at = datetime.utcnow().isoformat()
    c.execute(
        """
        UPDATE tasks
        SET is_completed = 1, completed_at = ?, updated_at = ?
        WHERE id = ? AND user_id = ?
        """,
        (completed_at, completed_at, task_id, user_id),
    )
    rows_affected = c.rowcount
    if rows_affected:
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
    return rows_affected > 0


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
    now = datetime.now().isoformat(timespec="minutes")
    c.execute(
        """
        SELECT
            id, user_id, title, description, due_date, is_completed, created_at,
            priority, category, reminder_at, recurrence, completed_at, updated_at,
            last_reminded_at, due_time
        FROM tasks
        WHERE is_completed = 0
            AND reminder_at IS NOT NULL
            AND reminder_at <= ?
            AND (last_reminded_at IS NULL OR last_reminded_at < reminder_at)
        ORDER BY reminder_at ASC
        LIMIT ?
        """,
        (now, limit),
    )
    tasks = [_row_to_task(row) for row in c.fetchall()]
    conn.close()
    return tasks


def mark_task_reminded(task_id):
    conn = _connect()
    c = conn.cursor()
    reminded_at = datetime.now().isoformat(timespec="minutes")
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
    conn.commit()
    conn.close()
    return rows_affected


def search_knowledge(user_id, query, limit=5, source_type=None, min_score=0.05):
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


def get_users_for_daily_summary(current_time):
    conn = _connect()
    c = conn.cursor()
    today = date.today().isoformat()
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
