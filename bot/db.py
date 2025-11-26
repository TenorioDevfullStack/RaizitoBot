import sqlite3
import os
from datetime import datetime

DB_PATH = "bot_data.db"

def init_db():
    """Initialize the database with necessary tables."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Tasks/Reminders table
    c.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT,
            is_completed BOOLEAN DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

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

    conn.commit()
    conn.close()

def add_task(user_id, title, description=None, due_date=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO tasks (user_id, title, description, due_date) VALUES (?, ?, ?, ?)",
              (user_id, title, description, due_date))
    conn.commit()
    task_id = c.lastrowid
    conn.close()
    return task_id

def get_tasks(user_id, pending_only=True):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    query = "SELECT id, title, description, due_date, is_completed FROM tasks WHERE user_id = ?"
    if pending_only:
        query += " AND is_completed = 0"

    c.execute(query, (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def complete_task(task_id, user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE tasks SET is_completed = 1 WHERE id = ? AND user_id = ?", (task_id, user_id))
    rows_affected = c.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0

def log_conversation(user_id: int, role: str, content: str):
    """Persist a conversation message for contextual memory."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO conversations (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (user_id, role, content, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()

def get_conversation_history(user_id: int, limit: int = 10):
    """Return the most recent conversation messages in chronological order."""
    conn = sqlite3.connect(DB_PATH)
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
