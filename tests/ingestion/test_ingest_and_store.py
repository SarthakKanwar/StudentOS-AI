"""End-to-end ingestion with embeddings and persistence, both faked.

These tests exist to prove the failure rule: a document is only ever marked
`ready` when every chunk and every embedding has been stored. Anything else
lands on `failed` with a readable reason.
"""

import pytest

from backend.foundry.embeddings import EMBEDDING_DIMENSIONS, EmbeddingError
from backend.ingestion.pipeline import ingest_and_store
from backend.services.persistence import PersistenceError


class FakeRepository:
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def _record(self, name, *args):
        self.calls.append(name)
        if self.fail_on == name:
            raise PersistenceError(f"simulated failure in {name}")

    def create_document(self, document):
        self._record("create_document")
        return "doc-uuid-1"

    def store_chunks(self, document_id, chunks):
        self.stored_chunks = chunks
        self._record("store_chunks")

    def store_embeddings(self, chunks, vectors, model_version):
        self.stored_vectors = vectors
        self.model_version = model_version
        self._record("store_embeddings")

    def mark_ready(self, document_id):
        self._record("mark_ready")

    def mark_failed(self, document_id, error_message):
        self.failure_reason = error_message
        self._record("mark_failed")

    def delete_chunks(self, document_id):
        self._record("delete_chunks")


class FakeEmbedder:
    model_version = "text-embedding-3-small"

    def __init__(self, error=None):
        self.error = error
        self.embedded = None

    def embed_texts(self, texts):
        if self.error:
            raise self.error
        self.embedded = texts
        return [[0.01] * EMBEDDING_DIMENSIONS for _ in texts]

    def close(self):
        pass


@pytest.fixture
def pdf(tmp_path, multi_page_pdf):
    path = tmp_path / "syllabus.pdf"
    path.write_bytes(multi_page_pdf)
    return path


class TestHappyPath:
    def test_document_is_stored_and_marked_ready(self, pdf):
        repo, embedder = FakeRepository(), FakeEmbedder()

        doc = ingest_and_store(pdf, "Course Syllabus", embedder=embedder, repository=repo)

        assert doc.status == "ready"
        assert doc.error_message is None
        assert doc.id == "doc-uuid-1"
        assert repo.calls == [
            "create_document",
            "store_chunks",
            "store_embeddings",
            "mark_ready",
        ]

    def test_ready_comes_after_both_stores(self, pdf):
        """Ordering is the guarantee: ready must never precede the data."""
        repo = FakeRepository()

        ingest_and_store(pdf, "T", embedder=FakeEmbedder(), repository=repo)

        assert repo.calls.index("mark_ready") > repo.calls.index("store_chunks")
        assert repo.calls.index("mark_ready") > repo.calls.index("store_embeddings")

    def test_every_chunk_is_embedded(self, pdf):
        repo, embedder = FakeRepository(), FakeEmbedder()

        doc = ingest_and_store(pdf, "T", embedder=embedder, repository=repo)

        assert len(embedder.embedded) == len(doc.chunks)
        assert embedder.embedded == [c.content for c in doc.chunks]
        assert len(repo.stored_vectors) == len(doc.chunks)

    def test_model_version_is_recorded(self, pdf):
        repo = FakeRepository()
        ingest_and_store(pdf, "T", embedder=FakeEmbedder(), repository=repo)
        assert repo.model_version == "text-embedding-3-small"

    def test_page_metadata_survives_to_persistence(self, pdf):
        repo = FakeRepository()
        ingest_and_store(pdf, "T", embedder=FakeEmbedder(), repository=repo)

        for chunk in repo.stored_chunks:
            assert chunk.page_start >= 1
            assert chunk.page_end >= chunk.page_start


class TestLocalFailure:
    def test_invalid_pdf_is_recorded_as_failed(self, tmp_path, non_pdf_bytes):
        path = tmp_path / "bad.pdf"
        path.write_bytes(non_pdf_bytes)
        repo = FakeRepository()

        doc = ingest_and_store(path, "Broken", embedder=FakeEmbedder(), repository=repo)

        assert doc.status == "failed"
        assert "pdf" in doc.error_message.lower()
        assert "mark_failed" in repo.calls
        assert "mark_ready" not in repo.calls

    def test_no_chunks_are_stored_for_a_local_failure(self, tmp_path, non_pdf_bytes):
        path = tmp_path / "bad.pdf"
        path.write_bytes(non_pdf_bytes)
        repo = FakeRepository()

        ingest_and_store(path, "Broken", embedder=FakeEmbedder(), repository=repo)

        assert "store_chunks" not in repo.calls
        assert "store_embeddings" not in repo.calls

    def test_failed_document_is_still_visible_to_an_admin(self, tmp_path, non_pdf_bytes):
        """FR-2.8/FR-2.10: the row must exist so the failure can be seen."""
        path = tmp_path / "bad.pdf"
        path.write_bytes(non_pdf_bytes)
        repo = FakeRepository()

        ingest_and_store(path, "Broken", embedder=FakeEmbedder(), repository=repo)

        assert repo.calls[0] == "create_document"
        assert repo.failure_reason


class TestEmbeddingFailure:
    def test_embedding_error_marks_the_document_failed(self, pdf):
        repo = FakeRepository()
        embedder = FakeEmbedder(error=EmbeddingError("Entra authentication failed"))

        doc = ingest_and_store(pdf, "T", embedder=embedder, repository=repo)

        assert doc.status == "failed"
        assert "Entra authentication failed" in doc.error_message
        assert "mark_ready" not in repo.calls

    def test_nothing_is_stored_when_embedding_fails(self, pdf):
        repo = FakeRepository()
        embedder = FakeEmbedder(error=EmbeddingError("dimension is 768"))

        ingest_and_store(pdf, "T", embedder=embedder, repository=repo)

        assert "store_chunks" not in repo.calls
        assert "store_embeddings" not in repo.calls


class TestPersistenceFailure:
    def test_chunk_store_failure_unwinds_and_fails(self, pdf):
        repo = FakeRepository(fail_on="store_chunks")

        doc = ingest_and_store(pdf, "T", embedder=FakeEmbedder(), repository=repo)

        assert doc.status == "failed"
        assert "delete_chunks" in repo.calls
        assert "mark_failed" in repo.calls
        assert "mark_ready" not in repo.calls

    def test_embedding_store_failure_removes_orphaned_chunks(self, pdf):
        """Chunks landed but vectors did not — the chunks must not survive."""
        repo = FakeRepository(fail_on="store_embeddings")

        doc = ingest_and_store(pdf, "T", embedder=FakeEmbedder(), repository=repo)

        assert doc.status == "failed"
        assert repo.calls.index("delete_chunks") > repo.calls.index("store_chunks")
        assert "mark_ready" not in repo.calls

    def test_cleanup_failure_still_marks_the_document_failed(self, pdf):
        """If cleanup itself breaks, status still has to be correct."""

        class StubbornRepository(FakeRepository):
            def delete_chunks(self, document_id):
                self.calls.append("delete_chunks")
                raise PersistenceError("cannot delete")

        repo = StubbornRepository(fail_on="store_embeddings")

        doc = ingest_and_store(pdf, "T", embedder=FakeEmbedder(), repository=repo)

        assert doc.status == "failed"
        assert "mark_failed" in repo.calls
        assert "mark_ready" not in repo.calls
