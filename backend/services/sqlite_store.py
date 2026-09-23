"""Local SQLite storage for the demo.

Mirrors migrations/0001_initial_schema.sql closely enough that swapping in
Supabase later is a store swap, not a rewrite. Vectors are stored as JSON and
cosine similarity is computed in Python — at demo scale (tens of documents) that
is fast enough, and it removes the pgvector dependency from the local path.
"""

from __future__ import annotations

import json
import math
import sqlite3
import uuid
from pathlib import Path

from backend.ingestion.models import Chunk, Document
from .store import SearchResult

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "studentos.db"

SCHEMA = """
create table if not exists documents (
    id                  text primary key,
    title               text not null,
    original_filename   text not null,
    file_hash           text not null,
    status              text not null default 'uploaded',
    page_count          integer not null default 0,
    injection_risk_flag integer not null default 0,
    error_message       text,
    approved_at         text,
    created_at          text not null default current_timestamp
);

create table if not exists chunks (
    id            text primary key,
    document_id   text not null references documents (id) on delete cascade,
    content       text not null,
    page_start    integer,
    page_end      integer,
    chunk_index   integer not null,
    char_start    integer not null,
    char_end      integer not null,
    section_label text,
    token_count   integer not null
);

create table if not exists chunk_embeddings (
    chunk_id      text primary key references chunks (id) on delete cascade,
    embedding     text not null,
    model_version text not null
);

create index if not exists chunks_document_id_idx on chunks (document_id);
create index if not exists documents_status_idx on documents (status);
"""

VALID_STATUSES = ("uploaded", "processing", "ready", "approved", "failed")


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class SqliteStore:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("pragma foreign_keys = on")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------- ingestion

    def create_document(self, document: Document) -> str:
        document_id = uuid.uuid4().hex
        self._conn.execute(
            "insert into documents (id, title, original_filename, file_hash, status, "
            "page_count, injection_risk_flag) values (?, ?, ?, ?, 'processing', ?, ?)",
            (
                document_id,
                document.title,
                document.original_filename,
                document.file_hash,
                document.page_count,
                int(document.injection_risk_flag),
            ),
        )
        self._conn.commit()
        return document_id

    def store_chunks(self, document_id: str, chunks: list[Chunk]) -> None:
        self._conn.executemany(
            "insert into chunks (id, document_id, content, page_start, page_end, "
            "chunk_index, char_start, char_end, section_label, token_count) "
            "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    c.id,
                    document_id,
                    c.content,
                    c.page_start,
                    c.page_end,
                    c.chunk_index,
                    c.char_start,
                    c.char_end,
                    c.section_label,
                    c.token_count,
                )
                for c in chunks
            ],
        )
        self._conn.commit()

    def store_embeddings(
        self, chunks: list[Chunk], vectors: list[list[float]], model_version: str
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("embedding count does not match chunk count")
        self._conn.executemany(
            "insert into chunk_embeddings (chunk_id, embedding, model_version) values (?, ?, ?)",
            [(c.id, json.dumps(v), model_version) for c, v in zip(chunks, vectors)],
        )
        self._conn.commit()

    def mark_ready(self, document_id: str) -> None:
        self._set_status(document_id, "ready", None)

    def mark_failed(self, document_id: str, error_message: str) -> None:
        self._set_status(document_id, "failed", error_message[:2000])

    def delete_chunks(self, document_id: str) -> None:
        self._conn.execute("delete from chunks where document_id = ?", (document_id,))
        self._conn.commit()

    def _set_status(self, document_id: str, status: str, error_message: str | None) -> None:
        self._conn.execute(
            "update documents set status = ?, error_message = ? where id = ?",
            (status, error_message, document_id),
        )
        self._conn.commit()

    # ----------------------------------------------------------------- admin

    def approve_document(self, document_id: str) -> bool:
        """ready → approved. Only now does the document become retrievable."""
        row = self._conn.execute(
            "select status from documents where id = ?", (document_id,)
        ).fetchone()
        if row is None or row["status"] not in ("ready", "approved"):
            return False
        self._conn.execute(
            "update documents set status = 'approved', approved_at = current_timestamp "
            "where id = ?",
            (document_id,),
        )
        self._conn.commit()
        return True

    def revoke_document(self, document_id: str) -> bool:
        """approved → ready. Takes effect immediately; no re-indexing."""
        row = self._conn.execute(
            "select status from documents where id = ?", (document_id,)
        ).fetchone()
        if row is None or row["status"] != "approved":
            return False
        self._conn.execute("update documents set status = 'ready' where id = ?", (document_id,))
        self._conn.commit()
        return True

    def get_document(self, document_id: str) -> dict | None:
        row = self._conn.execute(
            "select id, title, original_filename, status, page_count, error_message "
            "from documents where id = ?",
            (document_id,),
        ).fetchone()
        return dict(row) if row else None

    def delete_document(self, document_id: str) -> bool:
        """Remove one document and everything belonging to it.

        chunks and chunk_embeddings both declare `on delete cascade`, and this
        connection enables `pragma foreign_keys`, so a single delete removes the
        chunks and their embeddings too. Deleting them by hand as well would
        duplicate logic the schema already owns.
        """
        cursor = self._conn.execute("delete from documents where id = ?", (document_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def count_chunks(self, document_id: str) -> int:
        """Used by tests to prove the cascade actually fired."""
        return self._conn.execute(
            "select count(*) from chunks where document_id = ?", (document_id,)
        ).fetchone()[0]

    def count_embeddings(self, document_id: str) -> int:
        return self._conn.execute(
            "select count(*) from chunk_embeddings e "
            "join chunks c on c.id = e.chunk_id where c.document_id = ?",
            (document_id,),
        ).fetchone()[0]

    def list_documents(self) -> list[dict]:
        rows = self._conn.execute(
            "select d.id, d.title, d.original_filename, d.status, d.page_count, "
            "d.error_message, d.created_at, "
            "(select count(*) from chunks c where c.document_id = d.id) as chunk_count "
            "from documents d order by d.created_at desc, d.rowid desc"
        ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------- retrieval

    def search(self, query_vector: list[float], top_k: int) -> list[SearchResult]:
        """Cosine similarity over chunks of APPROVED documents only."""
        rows = self._conn.execute(
            "select c.id, c.content, c.document_id, c.page_start, c.page_end, "
            "d.title as document_title, e.embedding "
            "from chunk_embeddings e "
            "join chunks c on c.id = e.chunk_id "
            "join documents d on d.id = c.document_id "
            "where d.status = 'approved'"
        ).fetchall()

        scored = [
            SearchResult(
                chunk_id=row["id"],
                content=row["content"],
                document_id=row["document_id"],
                document_title=row["document_title"],
                page_start=row["page_start"],
                page_end=row["page_end"],
                score=cosine_similarity(query_vector, json.loads(row["embedding"])),
            )
            for row in rows
        ]
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    def is_chunk_approved(self, chunk_id: str) -> bool:
        """Gate 3 re-checks approval at validation time, so revocation is instant."""
        row = self._conn.execute(
            "select 1 from chunks c join documents d on d.id = c.document_id "
            "where c.id = ? and d.status = 'approved'",
            (chunk_id,),
        ).fetchone()
        return row is not None

    def close(self) -> None:
        self._conn.close()
