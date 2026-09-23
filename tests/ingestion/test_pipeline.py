"""Tests for the complete ingestion pipeline."""

import pytest

from backend.ingestion.models import Document, ExtractionError
from backend.ingestion.pipeline import ingest_pdf_file


class TestIngestPdfFile:
    def test_valid_pdf_ingested(self, tmp_path, simple_pdf):
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(simple_pdf)

        doc = ingest_pdf_file(pdf_path, title="Test Document")

        assert doc.title == "Test Document"
        assert doc.original_filename == "test.pdf"
        assert doc.page_count == 1
        assert doc.status == "ready"
        assert doc.error_message is None
        assert len(doc.chunks) > 0
        assert doc.file_hash  # SHA-256 computed

    def test_file_hash_computed(self, tmp_path, simple_pdf):
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(simple_pdf)

        doc = ingest_pdf_file(pdf_path, title="Test")

        import hashlib

        expected_hash = hashlib.sha256(simple_pdf).hexdigest()
        assert doc.file_hash == expected_hash

    def test_title_vs_filename_preserved(self, tmp_path, simple_pdf):
        pdf_path = tmp_path / "weird_filename_v2_FINAL.pdf"
        pdf_path.write_bytes(simple_pdf)

        doc = ingest_pdf_file(pdf_path, title="Course Syllabus")

        assert doc.title == "Course Syllabus"  # human-readable
        assert doc.original_filename == "weird_filename_v2_FINAL.pdf"  # as-uploaded

    def test_non_pdf_fails(self, tmp_path, non_pdf_bytes):
        pdf_path = tmp_path / "notapdf.txt"
        pdf_path.write_bytes(non_pdf_bytes)

        doc = ingest_pdf_file(pdf_path, title="Test")

        assert doc.status == "failed"
        assert doc.error_message is not None
        assert "pdf" in doc.error_message.lower()

    def test_encrypted_pdf_fails(self, tmp_path, encrypted_pdf):
        pdf_path = tmp_path / "encrypted.pdf"
        pdf_path.write_bytes(encrypted_pdf)

        doc = ingest_pdf_file(pdf_path, title="Test")

        assert doc.status == "failed"
        assert "encrypt" in doc.error_message.lower() or "password" in doc.error_message.lower()

    def test_multi_page_document(self, tmp_path, multi_page_pdf):
        pdf_path = tmp_path / "multi.pdf"
        pdf_path.write_bytes(multi_page_pdf)

        doc = ingest_pdf_file(pdf_path, title="Multi-Page Document")

        assert doc.page_count == 3
        assert len(doc.chunks) > 0

    def test_chunk_metadata_complete(self, tmp_path, multi_page_pdf):
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(multi_page_pdf)

        doc = ingest_pdf_file(pdf_path, title="Test")

        for chunk in doc.chunks:
            assert chunk.id.startswith("c_")
            assert chunk.page_start is not None
            assert chunk.page_end is not None
            assert chunk.page_start >= 1
            assert chunk.page_end >= 1
            assert chunk.page_start <= chunk.page_end
            assert chunk.token_count > 0
            assert chunk.content  # has text
            assert chunk.char_start >= 0
            assert chunk.char_end >= chunk.char_start

    def test_injection_risk_flag_defaults_false(self, tmp_path, simple_pdf):
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(simple_pdf)

        doc = ingest_pdf_file(pdf_path, title="Test")

        assert doc.injection_risk_flag is False

    def test_nonexistent_file_fails(self, tmp_path):
        pdf_path = tmp_path / "does_not_exist.pdf"

        doc = ingest_pdf_file(pdf_path, title="Test")

        assert doc.status == "failed"
        assert "cannot read file" in doc.error_message.lower()

    def test_document_to_dict(self, tmp_path, simple_pdf):
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(simple_pdf)

        doc = ingest_pdf_file(pdf_path, title="Test")
        dict_repr = doc.to_dict()

        assert dict_repr["title"] == "Test"
        assert dict_repr["status"] == "ready"
        assert dict_repr["page_count"] == 1
        assert "chunks" in dict_repr
        assert dict_repr["chunk_count"] > 0
