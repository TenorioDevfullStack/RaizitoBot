import logging
import os
import re
from datetime import UTC, datetime
from typing import Any

import requests

from bot.rag import embed_text


logger = logging.getLogger(__name__)


class VectorStoreError(RuntimeError):
    """Raised when the configured vector store rejects an operation."""


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "sim"}


def _supabase_url() -> str:
    return (os.getenv("SUPABASE_URL") or "").rstrip("/")


def _supabase_key() -> str:
    return os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""


def _supabase_schema() -> str:
    return os.getenv("SUPABASE_SCHEMA", "public").strip() or "public"


def _supabase_table() -> str:
    return os.getenv("SUPABASE_KNOWLEDGE_TABLE", "knowledge_items").strip() or "knowledge_items"


def _supabase_match_function() -> str:
    return os.getenv("SUPABASE_MATCH_FUNCTION", "match_knowledge_items").strip() or "match_knowledge_items"


def _request_timeout() -> float:
    try:
        return float(os.getenv("SUPABASE_REQUEST_TIMEOUT", "10"))
    except ValueError:
        return 10.0


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.9g}" for value in vector) + "]"


def supabase_vector_store_configured() -> bool:
    return bool(_supabase_url() and _supabase_key())


def use_supabase_vector_store() -> bool:
    backend = os.getenv("RAG_VECTOR_BACKEND", "sqlite").strip().lower()
    if backend in {"supabase", "pgvector"}:
        return supabase_vector_store_configured()
    if backend == "auto":
        return supabase_vector_store_configured()
    return False


def active_vector_backend() -> str:
    return "supabase" if use_supabase_vector_store() else "sqlite"


def supabase_fallback_to_sqlite() -> bool:
    return _env_flag("RAG_SUPABASE_FALLBACK_TO_SQLITE", True)


def _headers(prefer: str | None = None) -> dict[str, str]:
    key = _supabase_key()
    if not _supabase_url() or not key:
        raise VectorStoreError("Supabase vector store is not configured.")

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    schema = _supabase_schema()
    if schema != "public":
        headers["Accept-Profile"] = schema
        headers["Content-Profile"] = schema
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _send(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_data: Any | None = None,
    prefer: str | None = None,
) -> requests.Response:
    url = f"{_supabase_url()}/rest/v1/{path.lstrip('/')}"
    try:
        response = requests.request(
            method,
            url,
            params=params,
            json=json_data,
            headers=_headers(prefer=prefer),
            timeout=_request_timeout(),
        )
    except requests.RequestException as exc:
        raise VectorStoreError(f"Supabase request failed: {exc}") from exc

    if response.status_code >= 400:
        body = response.text[:500]
        raise VectorStoreError(f"Supabase returned HTTP {response.status_code}: {body}")
    return response


def _request_json(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_data: Any | None = None,
    prefer: str | None = None,
) -> Any:
    response = _send(method, path, params=params, json_data=json_data, prefer=prefer)
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def supabase_upsert_knowledge_item(
    user_id: int,
    source_type: str,
    source_id: str | int,
    title: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    now = datetime.now(UTC).isoformat()
    payload = {
        "user_id": int(user_id),
        "source_type": str(source_type),
        "source_id": str(source_id),
        "title": title,
        "content": content,
        "embedding": _vector_literal(embed_text(content)),
        "metadata": metadata or {},
        "updated_at": now,
    }
    _request_json(
        "POST",
        _supabase_table(),
        params={"on_conflict": "user_id,source_type,source_id"},
        json_data=payload,
        prefer="resolution=merge-duplicates,return=minimal",
    )


def supabase_delete_knowledge_item(user_id: int, source_type: str, source_id: str | int) -> None:
    _request_json(
        "DELETE",
        _supabase_table(),
        params={
            "user_id": f"eq.{int(user_id)}",
            "source_type": f"eq.{source_type}",
            "source_id": f"eq.{source_id}",
        },
        prefer="return=minimal",
    )


def supabase_clear_knowledge_source(user_id: int, source_type: str) -> None:
    _request_json(
        "DELETE",
        _supabase_table(),
        params={
            "user_id": f"eq.{int(user_id)}",
            "source_type": f"eq.{source_type}",
        },
        prefer="return=minimal",
    )


def supabase_search_knowledge(
    user_id: int,
    query: str,
    limit: int = 5,
    source_type: str | None = None,
    min_score: float = 0.05,
) -> list[dict[str, Any]]:
    payload = {
        "query_embedding": _vector_literal(embed_text(query)),
        "target_user_id": int(user_id),
        "match_count": max(1, int(limit)),
        "match_threshold": float(min_score),
        "filter_source_type": source_type,
    }
    rows = _request_json("POST", f"rpc/{_supabase_match_function()}", json_data=payload) or []
    if not isinstance(rows, list):
        raise VectorStoreError("Supabase match function returned an unexpected response.")

    results = []
    for row in rows:
        metadata = row.get("metadata") or {}
        if isinstance(metadata, str):
            metadata = {"raw": metadata}
        results.append(
            {
                "id": row.get("id"),
                "user_id": row.get("user_id"),
                "source_type": row.get("source_type"),
                "source_id": row.get("source_id"),
                "title": row.get("title"),
                "content": row.get("content"),
                "score": float(row.get("similarity") or row.get("score") or 0.0),
                "metadata": metadata,
            }
        )
    return results


def supabase_count_knowledge_items(user_id: int | None = None) -> int:
    params = {"select": "id", "limit": "1"}
    if user_id is not None:
        params["user_id"] = f"in.(0,{int(user_id)})"

    response = _send(
        "GET",
        _supabase_table(),
        params=params,
        prefer="count=exact",
    )
    content_range = response.headers.get("content-range") or response.headers.get("Content-Range") or ""
    match = re.search(r"/(\d+|\*)$", content_range)
    if match and match.group(1).isdigit():
        return int(match.group(1))

    data = response.json() if response.content else []
    return len(data) if isinstance(data, list) else 0
