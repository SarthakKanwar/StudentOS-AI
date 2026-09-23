"""Ingestion test fixtures and helpers."""

import io
from pathlib import Path

import pytest
from pypdf import PdfWriter


def create_test_pdf(pages: list[str], encrypted: bool = False) -> bytes:
    """Create a minimal PDF in memory for testing.

    Args:
        pages: list of strings, one per page
        encrypted: if True, encrypt the PDF

    Returns:
        PDF bytes
    """
    from pypdf import PdfReader

    # Use pypdf to create a PDF. Since pypdf doesn't have a PdfWriter that
    # creates from scratch easily, we'll create minimal PDF manually.
    # For testing, a very simple PDF structure is enough.

    writer = PdfWriter()
    for page_text in pages:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        c.drawString(50, 750, page_text[:100] if page_text else "")
        c.showPage()
        c.save()
        buffer.seek(0)

        reader = PdfReader(buffer)
        for page in reader.pages:
            writer.add_page(page)

    if encrypted:
        writer.encrypt("password")

    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output.getvalue()


@pytest.fixture
def simple_pdf():
    """A one-page PDF with minimal text."""
    return create_test_pdf(["Hello world"])


@pytest.fixture
def multi_page_pdf():
    """A three-page PDF."""
    return create_test_pdf([
        "Page one: This is the first page with some text.",
        "Page two: This is the second page with different text.",
        "Page three: This is the third page with even more text.",
    ])


@pytest.fixture
def large_text_pdf():
    """A PDF with enough text to create multiple chunks (800 tokens each)."""
    large_text = "word " * 250  # ~1250 words, ~2000 tokens
    return create_test_pdf([large_text])


@pytest.fixture
def encrypted_pdf():
    """An encrypted PDF that should be rejected."""
    return create_test_pdf(["Secret content"], encrypted=True)


@pytest.fixture
def non_pdf_bytes():
    """Random bytes that are not a PDF."""
    return b"This is not a PDF file at all\x00\x01\x02"


@pytest.fixture
def sample_data_dir(tmp_path):
    """Create a temporary sample-data directory."""
    return tmp_path / "sample-data"
