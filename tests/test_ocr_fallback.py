"""OCR fallback for scanned PDFs.

The OCR service is faked throughout — no Azure call is made. What these tests
actually protect is the routing rule and the page contract: a PDF with a text
layer must never reach OCR, and OCR output must enter the existing pipeline
carrying page numbers that mean the same thing as the text-layer path's.
"""

from io import BytesIO

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from backend.ingestion.models import ExtractionError
from backend.ingestion.ocr import DocumentIntelligenceOcr, OcrError
from backend.ingestion.pdf import has_extractable_text, validate_pdf_structure
from backend.ingestion.pipeline import ingest_and_store, ingest_pdf_file
from backend.services.sqlite_store import SqliteStore

from test_demo_flow import BagOfWordsEmbedder

MARKERS = ["Alpha", "Zulu", "Kilo", "Delta"]


def scanned_pdf(page_count: int = 2) -> bytes:
    """A PDF with drawn shapes and no text layer — a stand-in for a scan."""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    for _ in range(page_count):
        c.rect(72, 500, 400, 200, fill=1)
        c.showPage()
    c.save()
    return buffer.getvalue()


def text_pdf(page_count: int = 2) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    for n in range(page_count):
        c.drawString(72, 700, f"This page carries a real embedded text layer, page {n + 1}.")
        c.showPage()
    c.save()
    return buffer.getvalue()


class FakeOcr:
    """Returns dense, page-distinct text so page attribution is checkable."""

    def __init__(self, page_count=2, error=None, pages=None):
        self.error = error
        self.calls = 0
        self._pages = pages or [
            {
                "number": n + 1,
                "text": " ".join(
                    f"{MARKERS[n % len(MARKERS)]} regulation clause number {i}."
                    for i in range(400)
                ),
            }
            for n in range(page_count)
        ]

    def extract_pages(self, file_content):
        self.calls += 1
        if self.error:
            raise self.error
        return {"page_count": len(self._pages), "pages": self._pages}

    def close(self):
        pass


class ExplodingOcr:
    """Fails the test loudly if the normal path ever reaches OCR."""

    def extract_pages(self, file_content):
        raise AssertionError("a PDF with a text layer must never reach OCR")

    def close(self):
        pass


@pytest.fixture
def store(tmp_path):
    instance = SqliteStore(tmp_path / "ocr.db")
    yield instance
    instance.close()


@pytest.fixture
def scanned_file(tmp_path):
    path = tmp_path / "scanned.pdf"
    path.write_bytes(scanned_pdf(2))
    return path


@pytest.fixture
def text_file(tmp_path):
    path = tmp_path / "normal.pdf"
    path.write_bytes(text_pdf(2))
    return path


# ─────────────────────────────────────────────────────── routing rule ──


class TestRouting:
    def test_scanned_pdf_has_no_text_layer(self, scanned_file):
        """The fixture must really be text-free, or nothing below is meaningful."""
        assert has_extractable_text(scanned_file.read_bytes()) is False

    def test_scanned_pdf_is_structurally_valid(self, scanned_file):
        """A scan is a valid PDF — it must reach OCR, not be rejected outright."""
        validate_pdf_structure(scanned_file.read_bytes())

    def test_normal_pdf_never_invokes_ocr(self, text_file):
        document = ingest_pdf_file(text_file, "Normal", ocr_client=ExplodingOcr())

        assert document.status == "ready"
        assert document.chunks

    def test_scanned_pdf_invokes_ocr(self, scanned_file):
        ocr = FakeOcr()

        document = ingest_pdf_file(scanned_file, "Scanned", ocr_client=ocr)

        assert ocr.calls == 1
        assert document.status == "ready"

    def test_ocr_disabled_fails_with_a_readable_reason(self, scanned_file, monkeypatch):
        from backend.config import get_settings

        monkeypatch.setenv("OCR_ENABLED", "false")
        get_settings.cache_clear()

        document = ingest_pdf_file(scanned_file, "Scanned")

        assert document.status == "failed"
        assert "OCR is disabled" in document.error_message
        get_settings.cache_clear()


# ──────────────────────────────────────────────────── page preservation ──


class TestPagePreservation:
    def test_ocr_pages_keep_their_numbers(self, scanned_file):
        document = ingest_pdf_file(scanned_file, "Scanned", ocr_client=FakeOcr(page_count=3))

        assert document.page_count == 3
        for chunk in document.chunks:
            assert chunk.page_start >= 1
            assert chunk.page_end >= chunk.page_start

    def test_page_one_stays_page_one_and_page_two_stays_page_two(self, scanned_file):
        """The citation promise: claimed pages must match the text actually held."""
        document = ingest_pdf_file(scanned_file, "Scanned", ocr_client=FakeOcr(page_count=2))
        markers = {1: "Alpha", 2: "Zulu"}

        for chunk in document.chunks:
            claimed = set(range(chunk.page_start, chunk.page_end + 1))
            present = {page for page, word in markers.items() if word in chunk.content}
            assert claimed == present, (
                f"chunk claims pages {sorted(claimed)} but holds text from {sorted(present)}"
            )

    def test_out_of_order_ocr_pages_are_sorted(self):
        result = DocumentIntelligenceOcr._to_pages(
            {
                "pages": [
                    {"pageNumber": 3, "lines": [{"content": "third"}]},
                    {"pageNumber": 1, "lines": [{"content": "first"}]},
                    {"pageNumber": 2, "lines": [{"content": "second"}]},
                ]
            }
        )

        assert [p["number"] for p in result["pages"]] == [1, 2, 3]
        assert [p["text"] for p in result["pages"]] == ["first", "second", "third"]

    def test_ocr_text_is_normalised_like_the_text_layer_path(self):
        result = DocumentIntelligenceOcr._to_pages(
            {"pages": [{"pageNumber": 1, "lines": [{"content": "spaced"}, {"content": "  out  "}]}]}
        )
        assert result["pages"][0]["text"] == "spaced out"


# ─────────────────────────────────────────────────────── failure modes ──


class TestOcrFailures:
    @pytest.mark.parametrize(
        "error,expected",
        [
            (OcrError("OCR is unavailable: Entra authentication failed."), "unavailable"),
            (OcrError("OCR processing failed: corrupt image"), "processing failed"),
            (OcrError("OCR returned no usable text."), "no usable text"),
            (OcrError("OCR timed out after 180s."), "timed out"),
        ],
    )
    def test_ocr_failure_marks_the_document_failed(self, scanned_file, error, expected):
        document = ingest_pdf_file(scanned_file, "Scanned", ocr_client=FakeOcr(error=error))

        assert document.status == "failed"
        assert expected in document.error_message
        assert document.chunks == []

    def test_ocr_returning_blank_pages_is_a_failure_not_an_empty_document(self):
        with pytest.raises(OcrError, match="no usable text"):
            DocumentIntelligenceOcr._to_pages(
                {"pages": [{"pageNumber": 1, "lines": []}, {"pageNumber": 2, "lines": []}]}
            )

    def test_ocr_returning_no_pages_is_a_failure(self):
        with pytest.raises(OcrError, match="no pages"):
            DocumentIntelligenceOcr._to_pages({"pages": []})

    def test_failed_ocr_document_is_never_stored_ready(self, scanned_file, store):
        document = ingest_and_store(
            scanned_file,
            "Scanned",
            embedder=BagOfWordsEmbedder(),
            repository=store,
            ocr_client=FakeOcr(error=OcrError("OCR processing failed: unreadable")),
        )

        assert document.status == "failed"
        assert store.get_document(document.id)["status"] == "failed"
        assert store.count_chunks(document.id) == 0


# ──────────────────────────────────────── OCR through the existing RAG ──


class TestOcrThroughExistingPipeline:
    def test_ocr_document_uses_the_existing_chunk_id_format(self, scanned_file):
        document = ingest_pdf_file(scanned_file, "Scanned", ocr_client=FakeOcr())

        for chunk in document.chunks:
            assert chunk.id.startswith("c_")
            assert len(chunk.id) == 14
            assert chunk.token_count > 0

    def test_ocr_document_is_embedded_and_stored_like_any_other(self, scanned_file, store):
        document = ingest_and_store(
            scanned_file,
            "Scanned Notice",
            embedder=BagOfWordsEmbedder(),
            repository=store,
            ocr_client=FakeOcr(),
        )

        assert document.status == "ready"
        assert store.count_chunks(document.id) == len(document.chunks)
        assert store.count_embeddings(document.id) == len(document.chunks)

    def test_ocr_document_is_not_auto_approved(self, scanned_file, store):
        """Approval stays the same human gate it is for every other document."""
        document = ingest_and_store(
            scanned_file, "Scanned", embedder=BagOfWordsEmbedder(),
            repository=store, ocr_client=FakeOcr(),
        )

        assert store.get_document(document.id)["status"] == "ready"
        assert store.search(BagOfWordsEmbedder().embed_texts(["Alpha regulation"])[0], 8) == []

    def test_approved_ocr_document_is_retrievable_with_a_page_citation(self, scanned_file, store):
        document = ingest_and_store(
            scanned_file, "Scanned Notice", embedder=BagOfWordsEmbedder(),
            repository=store, ocr_client=FakeOcr(),
        )
        store.approve_document(document.id)

        results = store.search(
            BagOfWordsEmbedder().embed_texts(
                ["Zulu regulation clause number requirements for students"]
            )[0],
            8,
        )

        assert results
        top = results[0]
        assert top.document_title == "Scanned Notice"
        assert top.page_start >= 1
        # The winning passage must genuinely contain the page it claims.
        claimed = set(range(top.page_start, top.page_end + 1))
        present = {p for p, w in {1: "Alpha", 2: "Zulu"}.items() if w in top.content}
        assert claimed == present

    def test_approve_and_revoke_work_for_ocr_documents(self, scanned_file, store):
        document = ingest_and_store(
            scanned_file, "Scanned", embedder=BagOfWordsEmbedder(),
            repository=store, ocr_client=FakeOcr(),
        )
        query = BagOfWordsEmbedder().embed_texts(["Alpha regulation clause"])[0]

        assert store.approve_document(document.id) is True
        assert store.search(query, 8)

        assert store.revoke_document(document.id) is True
        assert store.search(query, 8) == []

    def test_deleting_an_ocr_document_removes_its_indexed_data(self, scanned_file, store):
        document = ingest_and_store(
            scanned_file, "Scanned", embedder=BagOfWordsEmbedder(),
            repository=store, ocr_client=FakeOcr(),
        )
        assert store.count_chunks(document.id) > 0

        assert store.delete_document(document.id) is True

        assert store.get_document(document.id) is None
        assert store.count_chunks(document.id) == 0
        assert store.count_embeddings(document.id) == 0


class TestNormalPathUnchanged:
    def test_text_pdf_still_produces_the_same_result_as_before(self, text_file):
        """Regression guard on the fast path: no OCR client involved at all."""
        document = ingest_pdf_file(text_file, "Normal")

        assert document.status == "ready"
        assert document.page_count == 2
        assert document.chunks
        assert "embedded text layer" in document.chunks[0].content

    def test_non_pdf_still_rejected_before_any_ocr_attempt(self, tmp_path):
        path = tmp_path / "bad.pdf"
        path.write_bytes(b"this is not a pdf at all")

        document = ingest_pdf_file(path, "Bad", ocr_client=ExplodingOcr())

        assert document.status == "failed"
        assert "not a PDF" in document.error_message

    def test_encrypted_pdf_still_rejected_before_any_ocr_attempt(self, tmp_path):
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        c.rect(72, 500, 100, 100, fill=1)
        c.showPage()
        c.save()

        import pypdf

        writer = pypdf.PdfWriter()
        for page in pypdf.PdfReader(BytesIO(buffer.getvalue())).pages:
            writer.add_page(page)
        writer.encrypt("secret")
        out = BytesIO()
        writer.write(out)

        path = tmp_path / "enc.pdf"
        path.write_bytes(out.getvalue())

        document = ingest_pdf_file(path, "Encrypted", ocr_client=ExplodingOcr())

        assert document.status == "failed"
        assert "encrypted" in document.error_message.lower()


def test_extraction_error_is_raised_not_ocr_error(scanned_file):
    """The pipeline only handles ExtractionError, so OcrError must be translated."""
    from backend.ingestion.pipeline import _ocr_pages

    with pytest.raises(ExtractionError):
        _ocr_pages(scanned_file.read_bytes(), FakeOcr(error=OcrError("boom")))
