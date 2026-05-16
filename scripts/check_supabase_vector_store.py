import os
import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from bot.vector_store import (
    active_vector_backend,
    supabase_delete_knowledge_item,
    supabase_search_knowledge,
    supabase_upsert_knowledge_item,
    supabase_vector_store_configured,
)


def main():
    load_dotenv()

    required = {
        "RAG_VECTOR_BACKEND": os.getenv("RAG_VECTOR_BACKEND"),
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_SERVICE_ROLE_KEY": os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        print("Missing required Supabase vector env vars:")
        for name in missing:
            print(f"- {name}")
        return 1

    backend = (required["RAG_VECTOR_BACKEND"] or "").strip().lower()
    if backend not in {"supabase", "pgvector", "auto"}:
        print("RAG_VECTOR_BACKEND must be supabase, pgvector, or auto to use Supabase.")
        print(f"Current value: {required['RAG_VECTOR_BACKEND']}")
        return 1

    if not supabase_vector_store_configured():
        print("Supabase vector store is not configured.")
        return 1

    source_id = f"supabase-smoke-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    content = "Smoke test do banco vetorial Supabase do RaizitoBot."

    print(f"Active vector backend: {active_vector_backend()}")
    print(f"Writing test item: {source_id}")
    supabase_upsert_knowledge_item(
        user_id=0,
        source_type="smoke_test",
        source_id=source_id,
        title="Supabase vector smoke test",
        content=content,
        metadata={"script": "check_supabase_vector_store.py"},
    )

    print("Searching test item...")
    results = supabase_search_knowledge(
        user_id=0,
        query="smoke test banco vetorial Supabase",
        limit=3,
        source_type="smoke_test",
        min_score=0.0,
    )
    found = any(item.get("source_id") == source_id for item in results)
    if not found:
        print("Test item was written, but search did not return it.")
        return 1

    print("Cleaning test item...")
    supabase_delete_knowledge_item(0, "smoke_test", source_id)
    print("Supabase vector store OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
