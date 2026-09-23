"""Local SQLite storage for the demo.

Mirrors migrations/0001_initial_schema.sql closely enough that swapping in
Supabase later is a store swap, not a rewrite. Vectors are stored as JSON and
cosine similarity is computed in Python — at demo scale (tens of documents) that
is fast enough, and it removes the pgvector dependency from the local path.
"""

from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
import uuid
from pathlib import Path

from backend.config import get_pipeline_config
from backend.ingestion.models import Chunk, Document
from .store import SearchResult

logger = logging.getLogger(__name__)

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

# Keyword index for hybrid retrieval. Kept in a separate script because FTS5 is
# a compile-time option: if this build lacks it, retrieval falls back to
# dense-only rather than the store failing to open.
#
# Triggers keep the index in step with `chunks`, including on the cascade from
# deleting a document — SQLite fires delete triggers for cascaded rows, so
# deletion needs no extra bookkeeping.
FTS_SCHEMA = """
create virtual table if not exists chunks_fts using fts5(chunk_id unindexed, content);

create trigger if not exists chunks_fts_after_insert after insert on chunks begin
    insert into chunks_fts (chunk_id, content) values (new.id, new.content);
end;

create trigger if not exists chunks_fts_after_delete after delete on chunks begin
    delete from chunks_fts where chunk_id = old.id;
end;

create trigger if not exists chunks_fts_after_update after update on chunks begin
    delete from chunks_fts where chunk_id = old.id;
    insert into chunks_fts (chunk_id, content) values (new.id, new.content);
end;
"""

VALID_STATUSES = ("uploaded", "processing", "ready", "approved", "failed")


def build_fts_query(text: str) -> str | None:
    """Turn a natural-language question into a safe FTS5 MATCH expression.

    Only alphanumeric runs survive, and each is wrapped in double quotes so it
    is matched as a literal. FTS5 operators (`OR`, `NEAR`, `*`, `-`, `^`, `:`)
    and quotes therefore cannot reach the parser from user input, which is what
    keeps a question like `what is 24CAI0201's "duration"?` from being read as
    syntax. Returns None when nothing usable remains.
    """
    tokens = re.findall(r"[A-Za-z0-9]+", text or "")
    # Single letters carry no signal and match almost everything.
    tokens = [t for t in tokens if len(t) > 1]
    if not tokens:
        return None
    return " OR ".join(f'"{token}"' for token in tokens)


def reciprocal_rank_fusion(rankings: list[list[str]], k: int) -> dict[str, float]:
    """Standard RRF: each list contributes 1 / (k + rank) to every id it holds.

    Rank-based rather than score-based, so a cosine similarity and a BM25 score
    — which are on completely different scales — can be combined without any
    normalisation step that would need its own calibration.
    """
    fused: dict[str, float] = {}
    for ranking in rankings:
        for position, chunk_id in enumerate(ranking, start=1):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (k + position)
    return fused


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
        self.fts_available = self._ensure_fts()

    def _ensure_fts(self) -> bool:
        """Create the keyword index, and backfill it for pre-existing databases.

        Returns False when this SQLite build has no FTS5, in which case search
        stays dense-only and everything else behaves exactly as before.
        """
        try:
            self._conn.executescript(FTS_SCHEMA)
        except sqlite3.OperationalError as exc:
            logger.warning("FTS5 unavailable, keyword retrieval disabled: %s", exc)
            return False

        # A database written before this index existed has chunks but no rows
        # here; the triggers only cover writes from now on.
        indexed = self._conn.execute("select count(*) from chunks_fts").fetchone()[0]
        total = self._conn.execute("select count(*) from chunks").fetchone()[0]
        if indexed != total:
            logger.info("backfilling keyword index: %d chunk(s)", total)
            self._conn.execute("delete from chunks_fts")
            self._conn.execute(
                "insert into chunks_fts (chunk_id, content) select id, content from chunks"
            )
        self._conn.commit()
        return True

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

    def keyword_search(self, query_text: str, limit: int) -> list[str]:
        """Chunk ids matching the question's literal terms, best first.

        Restricted to approved documents by the same join the dense path uses,
        so the keyword route cannot become a way to reach unapproved content.
        Returns ids only; scoring and metadata stay with the dense pass, which
        already computes cosine for every approved chunk.
        """
        if not self.fts_available:
            return []

        match = build_fts_query(query_text)
        if match is None:
            return []

        try:
            rows = self._conn.execute(
                "select f.chunk_id from chunks_fts f "
                "join chunks c on c.id = f.chunk_id "
                "join documents d on d.id = c.document_id "
                "where chunks_fts match ? and d.status = 'approved' "
                "order by bm25(chunks_fts) limit ?",
                (match, limit),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            # A malformed MATCH should degrade to dense-only, never 500.
            logger.warning("keyword search failed, using dense ranking only: %s", exc)
            return []

        return [row["chunk_id"] for row in rows]

    def search(
        self,
        query_vector: list[float],
        top_k: int,
        query_text: str | None = None,
    ) -> list[SearchResult]:
        """Retrieve the best chunks from APPROVED documents only.

        Dense cosine ranking alone under-weights rare literal tokens — course
        codes, regulation numbers, table values — because a chunk holding a
        table of many subjects embeds as a blur of all of them, while a long
        document *about* one subject matches it strongly on every chunk. When
        `query_text` is given and hybrid retrieval is on, a keyword ranking is
        fused with the dense one by Reciprocal Rank Fusion to fix the ordering.

        `SearchResult.score` stays the true cosine similarity in both modes.
        Fusion decides order only, so Gate 1 keeps thresholding on a real
        similarity value rather than on a rank-derived number.
        """
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
        # Deterministic: cosine descending, chunk_id as a stable tie-break.
        scored.sort(key=lambda r: (-r.score, r.chunk_id))

        config = get_pipeline_config().retrieval
        if not (config.hybrid_enabled and query_text and self.fts_available):
            return scored[:top_k]

        keyword_ranking = self.keyword_search(query_text, config.keyword_candidates)
        if not keyword_ranking:
            return scored[:top_k]

        by_id = {result.chunk_id: result for result in scored}
        # Both lists are fused at the same depth. Feeding the whole corpus as
        # the dense list would give every chunk a dense contribution and dilute
        # the keyword signal, which is the half that finds literal identifiers.
        dense_ranking = [result.chunk_id for result in scored[: config.keyword_candidates]]
        # A keyword hit whose embedding is missing cannot be scored or cited.
        keyword_ranking = [cid for cid in keyword_ranking if cid in by_id]

        fused = reciprocal_rank_fusion([dense_ranking, keyword_ranking], config.rrf_k)

        # dict keys are unique, so a chunk appearing in both rankings is fused
        # once and cannot be duplicated in the output.
        order = sorted(fused, key=lambda cid: (-fused[cid], cid))
        return [by_id[cid] for cid in order[:top_k]]

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
