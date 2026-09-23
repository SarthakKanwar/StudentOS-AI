"""Supabase persistence tests.

The Supabase client is faked throughout: no project is contacted.
"""

import pytest

from backend.ingestion.models import Chunk
from backend.services.persistence import (
    DocumentRepository,
    PersistenceError,
    SupabaseNotConfigured,
    _vector_literal,
    is_supabase_configured,
)


class FakeQuery:
    def __init__(self, table, log, fail_on=None):
        self._table = table
        self._log = log
        self._fail_on = fail_on
        self._op = None
        self._payload = None
        self._filters = {}

    def insert(self, payload):
        self._op, self._payload = "insert", payload
        return self

    def update(self, payload):
        self._op, self._payload = "update", payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, column, value):
        self._filters[column] = value
        return self

    def execute(self):
        entry = {
            "table": self._table,
            "op": self._op,
            "payload": self._payload,
            "filters": self._filters,
        }
        self._log.append(entry)
        if self._fail_on and self._fail_on(entry):
            raise RuntimeError("supabase rejected the request")
        if self._op == "insert":
            rows = self._payload if isinstance(self._payload, list) else [self._payload]
            return FakeResult([{**row, "id": row.get("id", "doc-uuid-1")} for row in rows])
        return FakeResult([])


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeSupabase:
    def __init__(self, fail_on=None):
        self.log = []
        self._fail_on = fail_on

    def table(self, name):
        return FakeQuery(name, self.log, self._fail_on)


@pytest.fixture
def repo():
    return DocumentRepository(client=FakeSupabase())


def make_chunks(count=3):
    return [
        Chunk(
            id=f"c_{i:012x}",
            content=f"chunk {i}",
            page_start=1,
            page_end=1,
            chunk_index=i,
            char_start=i * 10,
            char_end=(i + 1) * 10,
            token_count=5,
        )
        for i in range(count)
    ]


class TestSupabaseConfigured:
    @pytest.mark.parametrize(
        "url",
        [
            "https://example-project.invalid",
            "https://<your-supabase-project-url>",
            "http://localhost:54321",
            "",
        ],
    )
    def test_placeholders_are_not_configured(self, monkeypatch, url):
        monkeypatch.setenv("SUPABASE_URL", url)
        from backend.config import get_settings

        get_settings.cache_clear()
        assert is_supabase_configured() is False

    def test_real_project_url_is_configured(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "https://abcdefghijkl.supabase.co")
        from backend.config import get_settings

        get_settings.cache_clear()
        assert is_supabase_configured() is True

    def test_unconfigured_client_raises_a_actionable_error(self, monkeypatch):
        monkeypatch.setenv("SUPABASE_URL", "https://example-project.invalid")
        from backend.config import get_settings

        get_settings.cache_clear()
        repository = DocumentRepository()

        with pytest.raises(SupabaseNotConfigured, match="migrations/0001_initial_schema.sql"):
            _ = repository.client


class TestCreateDocument:
    def test_document_starts_as_processing_not_ready(self, repo):
        """A row must never appear ready before its chunks exist."""
        from backend.ingestion.models import Document

        doc = Document(
            title="Exam Schedule",
            original_filename="exam_v2_FINAL.pdf",
            file_hash="abc123",
            page_count=4,
        )

        repo.create_document(doc)

        payload = repo._client.log[0]["payload"]
        assert payload["status"] == "processing"
        assert payload["title"] == "Exam Schedule"
        assert payload["original_filename"] == "exam_v2_FINAL.pdf"
        assert payload["file_hash"] == "abc123"
        assert payload["injection_risk_flag"] is False

    def test_returns_the_new_document_id(self, repo):
        from backend.ingestion.models import Document

        doc = Document(title="T", original_filename="f.pdf", file_hash="h", page_count=1)
        assert repo.create_document(doc) == "doc-uuid-1"


class TestStoreChunks:
    def test_chunk_fields_are_persisted(self, repo):
        repo.store_chunks("doc-1", make_chunks(1))

        row = repo._client.log[0]["payload"][0]
        assert row["id"].startswith("c_")
        assert row["document_id"] == "doc-1"
        assert row["page_start"] == 1
        assert row["page_end"] == 1
        assert row["section_label"] is None
        assert row["token_count"] == 5

    def test_large_sets_are_batched(self, repo):
        repo.store_chunks("doc-1", make_chunks(250))

        assert len(repo._client.log) == 3
        assert [len(e["payload"]) for e in repo._client.log] == [100, 100, 50]

    def test_failure_is_wrapped(self):
        client = FakeSupabase(fail_on=lambda e: e["table"] == "chunks")
        repository = DocumentRepository(client=client)

        with pytest.raises(PersistenceError, match="store chunks"):
            repository.store_chunks("doc-1", make_chunks(1))


class TestStoreEmbeddings:
    def test_vector_is_rendered_as_a_pgvector_literal(self, repo):
        chunks = make_chunks(1)
        repo.store_embeddings(chunks, [[0.5, -0.25]], "text-embedding-3-small")

        row = repo._client.log[0]["payload"][0]
        assert row["embedding"] == "[0.5,-0.25]"
        assert row["chunk_id"] == chunks[0].id
        assert row["model_version"] == "text-embedding-3-small"

    def test_count_mismatch_is_rejected(self, repo):
        with pytest.raises(PersistenceError, match="does not match chunk count"):
            repo.store_embeddings(make_chunks(3), [[0.1]], "m")

    def test_vector_literal_format(self):
        assert _vector_literal([1.0, 2.5, -3.0]) == "[1.0,2.5,-3.0]"


class TestStatusTransitions:
    def test_mark_ready_clears_any_error(self, repo):
        repo.mark_ready("doc-1")

        entry = repo._client.log[0]
        assert entry["payload"] == {"status": "ready", "error_message": None}
        assert entry["filters"] == {"id": "doc-1"}

    def test_mark_failed_records_a_readable_reason(self, repo):
        repo.mark_failed("doc-1", "Scanned PDF - no extractable text")

        payload = repo._client.log[0]["payload"]
        assert payload["status"] == "failed"
        assert payload["error_message"] == "Scanned PDF - no extractable text"

    def test_long_error_is_truncated(self, repo):
        repo.mark_failed("doc-1", "x" * 5000)
        assert len(repo._client.log[0]["payload"]["error_message"]) == 2000

    def test_delete_chunks_targets_the_document(self, repo):
        repo.delete_chunks("doc-1")

        entry = repo._client.log[0]
        assert entry["table"] == "chunks"
        assert entry["op"] == "delete"
        assert entry["filters"] == {"document_id": "doc-1"}
