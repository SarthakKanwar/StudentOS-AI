"""Viewing the original uploaded PDF, and admin-only document deletion.

Covers only the new behaviour. External services are never contacted: the store
and upload directory are redirected to a tmp_path, and ingestion is done with a
fake embedder.
"""

import hashlib
import re

import pytest
from fastapi.testclient import TestClient

from backend.foundry.embeddings import EMBEDDING_DIMENSIONS
from backend.ingestion.pipeline import ingest_and_store
from backend.main import create_app
from backend.services import deps
from backend.services.file_storage import UploadStore
from backend.services.sqlite_store import SqliteStore

from test_demo_flow import HANDBOOK, BagOfWordsEmbedder


@pytest.fixture
def store(tmp_path):
    instance = SqliteStore(tmp_path / "docs.db")
    yield instance
    instance.close()


@pytest.fixture
def uploads(tmp_path):
    return UploadStore(tmp_path / "uploads")


@pytest.fixture
def client(store, uploads, monkeypatch):
    """App wired to the throwaway store and upload directory."""
    monkeypatch.setattr(deps, "get_shared_store", lambda: store)
    monkeypatch.setattr(deps, "get_upload_store", lambda: uploads)
    import backend.routes.admin as admin_routes

    monkeypatch.setattr(admin_routes, "get_shared_store", lambda: store)
    monkeypatch.setattr(admin_routes, "get_upload_store", lambda: uploads)

    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def ingested(store, uploads):
    """A real ingested document with its original PDF stored alongside it."""
    if not HANDBOOK.is_file():
        pytest.skip("run scripts/generate_demo_pdf.py first")

    document = ingest_and_store(
        HANDBOOK,
        "CS Department Student Handbook, Autumn 2026",
        embedder=BagOfWordsEmbedder(),
        repository=store,
    )
    assert document.status == "ready"
    uploads.save(document.id, HANDBOOK.read_bytes())
    return document


# ────────────────────────────────────────────────────────────── viewing ──


class TestViewPdf:
    def test_admin_can_view_the_original_pdf(self, client, ingested):
        response = client.get(f"/api/admin/documents/{ingested.id}/file")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF")

    def test_served_bytes_are_the_original_file_unchanged(self, client, ingested):
        """Byte-for-byte: the upload is preserved, not re-rendered."""
        response = client.get(f"/api/admin/documents/{ingested.id}/file")

        assert hashlib.sha256(response.content).hexdigest() == (
            hashlib.sha256(HANDBOOK.read_bytes()).hexdigest()
        )

    def test_pdf_opens_inline_rather_than_downloading(self, client, ingested):
        response = client.get(f"/api/admin/documents/{ingested.id}/file")
        assert "inline" in response.headers.get("content-disposition", "")

    def test_admin_can_view_a_failed_document(self, client, store, uploads):
        """A failed upload is still viewable, so an admin can see what arrived."""
        from backend.ingestion.models import Document

        document_id = store.create_document(
            Document(title="Broken", original_filename="broken.pdf", file_hash="h", page_count=0)
        )
        store.mark_failed(document_id, "No extractable text found")
        uploads.save(document_id, b"%PDF-1.4 not really parseable")

        response = client.get(f"/api/admin/documents/{document_id}/file")
        assert response.status_code == 200

    def test_student_can_view_an_approved_pdf(self, client, store, ingested):
        store.approve_document(ingested.id)

        response = client.get(f"/api/documents/{ingested.id}/file")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF")

    def test_student_cannot_view_an_unapproved_pdf(self, client, ingested):
        """The document is only 'ready' — the student route must refuse."""
        response = client.get(f"/api/documents/{ingested.id}/file")

        assert response.status_code == 403
        assert b"%PDF" not in response.content

    def test_revoking_closes_the_student_route_immediately(self, client, store, ingested):
        store.approve_document(ingested.id)
        assert client.get(f"/api/documents/{ingested.id}/file").status_code == 200

        store.revoke_document(ingested.id)
        assert client.get(f"/api/documents/{ingested.id}/file").status_code == 403

    def test_unknown_document_returns_404(self, client):
        assert client.get("/api/documents/deadbeefdeadbeef/file").status_code == 404
        assert client.get("/api/admin/documents/deadbeefdeadbeef/file").status_code == 404

    def test_document_without_a_stored_file_returns_404(self, client, store):
        """Ingested before file storage existed — the row exists, the file does not."""
        from backend.ingestion.models import Document

        document_id = store.create_document(
            Document(title="Old", original_filename="old.pdf", file_hash="h", page_count=1)
        )
        store.mark_ready(document_id)

        assert client.get(f"/api/admin/documents/{document_id}/file").status_code == 404


class TestPathTraversal:
    @pytest.mark.parametrize(
        "bad_id",
        ["../../../../etc/passwd", "..%2f..%2fsecret", "abc/../../x", "not-hex-id", ""],
    )
    def test_traversal_attempts_never_read_a_file(self, client, bad_id):
        response = client.get(f"/api/admin/documents/{bad_id}/file")
        assert response.status_code in (404, 403, 307)
        assert b"%PDF" not in response.content

    def test_upload_store_rejects_unsafe_ids(self, uploads):
        for bad in ["../escape", "a/b", "nothex!", ""]:
            assert uploads.save(bad, b"x") is False
            assert uploads.get(bad) is None
            assert uploads.delete(bad) is False


# ───────────────────────────────────────────────────────────── deletion ──


class TestDelete:
    def test_admin_can_delete_a_document(self, client, ingested):
        response = client.delete(f"/api/admin/documents/{ingested.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["deleted"] is True
        assert body["file_removed"] is True

    def test_record_chunks_and_embeddings_are_all_gone(self, client, store, ingested):
        assert store.count_chunks(ingested.id) > 0
        assert store.count_embeddings(ingested.id) > 0

        client.delete(f"/api/admin/documents/{ingested.id}")

        assert store.get_document(ingested.id) is None
        assert store.count_chunks(ingested.id) == 0
        assert store.count_embeddings(ingested.id) == 0

    def test_original_pdf_is_removed_from_disk(self, client, uploads, ingested):
        assert uploads.get(ingested.id) is not None

        client.delete(f"/api/admin/documents/{ingested.id}")

        assert uploads.get(ingested.id) is None

    def test_deleted_document_is_no_longer_viewable(self, client, ingested):
        client.delete(f"/api/admin/documents/{ingested.id}")

        assert client.get(f"/api/admin/documents/{ingested.id}/file").status_code == 404
        assert client.get(f"/api/documents/{ingested.id}/file").status_code == 404

    def test_deleted_document_is_no_longer_retrievable(self, client, store, ingested):
        """The core guarantee: deletion removes it from search, not just the list."""
        store.approve_document(ingested.id)
        embedder = BagOfWordsEmbedder()
        query = embedder.embed_texts(
            ["What is the minimum percentage attendance a student must maintain?"]
        )[0]
        assert store.search(query, 8)

        client.delete(f"/api/admin/documents/{ingested.id}")

        assert store.search(query, 8) == []

    def test_deleting_an_approved_document_works(self, client, store, ingested):
        store.approve_document(ingested.id)

        assert client.delete(f"/api/admin/documents/{ingested.id}").status_code == 200
        assert store.get_document(ingested.id) is None

    def test_deleting_a_failed_document_works(self, client, store, uploads):
        from backend.ingestion.models import Document

        document_id = store.create_document(
            Document(title="Broken", original_filename="b.pdf", file_hash="h", page_count=0)
        )
        store.mark_failed(document_id, "No extractable text found")
        uploads.save(document_id, b"%PDF-1.4 broken")

        assert client.delete(f"/api/admin/documents/{document_id}").status_code == 200
        assert store.get_document(document_id) is None
        assert uploads.get(document_id) is None

    def test_deleting_one_document_leaves_another_untouched(self, client, store, uploads, ingested):
        from backend.ingestion.models import Document

        other_id = store.create_document(
            Document(title="Keep me", original_filename="k.pdf", file_hash="h2", page_count=1)
        )
        store.mark_ready(other_id)
        uploads.save(other_id, b"%PDF-1.4 keep")

        client.delete(f"/api/admin/documents/{ingested.id}")

        assert store.get_document(other_id) is not None
        assert uploads.get(other_id) is not None
        assert store.get_document(ingested.id) is None

    def test_deleting_an_unknown_document_returns_404(self, client):
        assert client.delete("/api/admin/documents/deadbeefdeadbeef").status_code == 404

    def test_document_disappears_from_the_listing(self, client, ingested):
        before = client.get("/api/documents").json()["documents"]
        assert any(d["id"] == ingested.id for d in before)

        client.delete(f"/api/admin/documents/{ingested.id}")

        after = client.get("/api/documents").json()["documents"]
        assert not any(d["id"] == ingested.id for d in after)
