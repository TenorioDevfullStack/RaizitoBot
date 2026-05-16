import argparse
import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from bot.db import _connect
from bot.vector_store import supabase_upsert_knowledge_item, supabase_vector_store_configured


def _metadata(value):
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {"raw": parsed}
    except ValueError:
        return {"raw": value}


def main():
    parser = argparse.ArgumentParser(
        description="Sync local SQLite knowledge_items rows to Supabase pgvector."
    )
    parser.add_argument("--user-id", type=int, help="Sync only one Telegram user id.")
    parser.add_argument("--source-type", help="Sync only one source type.")
    args = parser.parse_args()

    load_dotenv()
    if not supabase_vector_store_configured():
        print("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        return 1

    query = """
        SELECT user_id, source_type, source_id, title, content, metadata
        FROM knowledge_items
        WHERE 1 = 1
    """
    params = []
    if args.user_id is not None:
        query += " AND user_id = ?"
        params.append(args.user_id)
    if args.source_type:
        query += " AND source_type = ?"
        params.append(args.source_type)
    query += " ORDER BY id ASC"

    try:
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
    except sqlite3.Error as exc:
        print(f"Could not read local knowledge_items table: {exc}")
        return 1

    synced = 0
    failed = 0
    for user_id, source_type, source_id, title, content, metadata in rows:
        try:
            supabase_upsert_knowledge_item(
                user_id,
                source_type,
                source_id,
                title,
                content,
                metadata=_metadata(metadata),
            )
            synced += 1
        except Exception as exc:
            failed += 1
            print(f"Failed to sync {source_type}:{source_id}: {exc}")

    print(f"Synced {synced} knowledge item(s) to Supabase. Failed: {failed}.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
