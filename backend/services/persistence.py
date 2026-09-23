"""Supabase persistence for ingested documents.

The backend connects with the service role key, which bypasses RLS. RLS exists
to protect the student-facing path (migrations/0001_initial_schema.sql); writes
are never client-side.

Failure rule (FR-2.10): a document row is created as `processing` and only
becomes `ready` once every chunk and every embedding is stored. Any failure
deletes the partial chunks and marks the document `failed` with a readable
reason. Nothing half-written is ever left looking healthy.
"""

from __future__ import annotations

import logging

from backend.config import Settings, get_settings
from backend.ingestion.models import Chunk, Document

logger = logging.getLogger(__name__)

# Chunks are inserted in batches; Supabase/PostgREST handles these comfortably
# and a smaller batch makes a partial failure cheaper to unwind.
INSERT_BATCH_SIZE = 100

# Hostnames used by .env.example and the test fixtures. Treating these as
# "not provisioned" keeps the CLI from producing a confusing network error when
# the real cause is that nobody has created a Supabase project yet.
_PLACEHOLDER_MARKERS = ("<your-", ".invalid", "example-project", "localhost")


class PersistenceError(RuntimeError):
    """Raised when persistence fails. Never carries keys or tokens."""


class SupabaseNotConfigured(PersistenceError):
    """Raised when Supabase has not been provisioned yet."""


def is_supabase_configured(settings: Settings | None = None) -> bool:
    """True when SUPABASE_URL looks like a real project rather than a placeholder."""
    settings = settings or get_settings()
    url = (settings.supabase_url or "").strip().lower()
    if not url.startswith("https://"):
        return False
    return not any(marker in url for marker in _PLACEHOLDER_MARKERS)


def _vector_literal(vector: list[float]) -> str:
    """Render a vector for pgvector.

    PostgREST sends JSON, and Postgres casts a text literal of the form
    '[0.1,0.2,...]' to `vector`. Sending a bare JSON array is not reliably cast.
    """
    return "[" + ",".join(repr(float(value)) for value in vector) + "]"


class DocumentRepository:
    """Stores documents, chunks and embeddings."""

    def __init__(self, client=None, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = client

    @property
    def client(self):
        if self._client is None:
            if not is_supabase_configured(self._settings):
                raise SupabaseNotConfigured(
                    "Supabase is not provisioned. SUPABASE_URL is unset or still a "
                    "placeholder. Create a project, apply migrations/0001_initial_schema.sql, "
                    "then set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env."
                )
            from supabase import create_client

            self._client = create_client(
                self._settings.supabase_url,
                self._settings.supabase_service_role_key.get_secret_value(),
            )
        return self._client

    # ---------------------------------------------------------------- writes

    def create_document(self, document: Document) -> str:
        """Insert the document row as `processing` and return its id."""
        payload = {
            "title": document.title,
            "original_filename": document.original_filename,
            "file_hash": document.file_hash,
            "page_count": document.page_count,
            "injection_risk_flag": document.injection_risk_flag,
            "status": "processing",
        }
        rows = self._execute(
            lambda: self.client.table("documents").insert(payload).execute(),
            "create document row",
        )
        if not rows:
            raise PersistenceError("Document insert returned no row")
        return rows[0]["id"]

    def store_chunks(self, document_id: str, chunks: list[Chunk]) -> None:
        for start in range(0, len(chunks), INSERT_BATCH_SIZE):
            batch = chunks[start : start + INSERT_BATCH_SIZE]
            payload = [
                {
                    "id": chunk.id,
                    "document_id": document_id,
                    "content": chunk.content,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "chunk_index": chunk.chunk_index,
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                    "section_label": chunk.section_label,
                    "token_count": chunk.token_count,
                }
                for chunk in batch
            ]
            self._execute(
                lambda p=payload: self.client.table("chunks").insert(p).execute(),
                f"store chunks {start}-{start + len(batch)}",
            )

    def store_embeddings(
        self,
        chunks: list[Chunk],
        vectors: list[list[float]],
        model_version: str,
    ) -> None:
        if len(chunks) != len(vectors):
            raise PersistenceError(
                f"Embedding count ({len(vectors)}) does not match chunk count ({len(chunks)})"
            )

        rows = [
            {
                "chunk_id": chunk.id,
                "embedding": _vector_literal(vector),
                "model_version": model_version,
            }
            for chunk, vector in zip(chunks, vectors)
        ]
        for start in range(0, len(rows), INSERT_BATCH_SIZE):
            batch = rows[start : start + INSERT_BATCH_SIZE]
            self._execute(
                lambda p=batch: self.client.table("chunk_embeddings").insert(p).execute(),
                f"store embeddings {start}-{start + len(batch)}",
            )

    # --------------------------------------------------------------- status

    def mark_ready(self, document_id: str) -> None:
        """processing → ready. Called only after everything is stored."""
        self._execute(
            lambda: self.client.table("documents")
            .update({"status": "ready", "error_message": None})
            .eq("id", document_id)
            .execute(),
            "mark document ready",
        )

    def mark_failed(self, document_id: str, error_message: str) -> None:
        """processing → failed, with a reason an admin can read (FR-2.10)."""
        self._execute(
            lambda: self.client.table("documents")
            .update({"status": "failed", "error_message": error_message[:2000]})
            .eq("id", document_id)
            .execute(),
            "mark document failed",
        )

    def delete_chunks(self, document_id: str) -> None:
        """Remove partially written chunks. Embeddings cascade with them."""
        self._execute(
            lambda: self.client.table("chunks").delete().eq("document_id", document_id).execute(),
            "delete partial chunks",
        )

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _execute(operation, description: str):
        try:
            response = operation()
        except Exception as exc:
            # Supabase errors can quote the request; they never contain the key,
            # which travels in a header. Truncate anyway.
            raise PersistenceError(f"Failed to {description}: {str(exc)[:300]}") from exc
        return getattr(response, "data", None) or []
