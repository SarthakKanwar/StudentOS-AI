"""Storage interface and factory.

Two implementations share this shape:
  * SqliteStore     — local demo storage, works on this machine with no cloud
  * DocumentRepository (persistence.py) — Supabase + pgvector

get_store() picks Supabase when it is configured and falls back to SQLite so the
prototype always runs. Retrieval always filters on status = 'approved'.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SearchResult:
    """One retrieved chunk, carrying everything a citation needs."""

    chunk_id: str
    content: str
    document_id: str
    document_title: str
    page_start: int | None
    page_end: int | None
    score: float


def get_store():
    """Return the active store: Supabase when configured, else local SQLite."""
    from .persistence import is_supabase_configured

    if is_supabase_configured():
        from .persistence import DocumentRepository

        return DocumentRepository()

    from .sqlite_store import SqliteStore

    return SqliteStore()


def store_backend_name() -> str:
    from .persistence import is_supabase_configured

    return "supabase" if is_supabase_configured() else "sqlite (local demo)"
