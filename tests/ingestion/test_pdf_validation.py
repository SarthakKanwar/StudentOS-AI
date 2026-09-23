"""Tests for PDF validation (security.md §5)."""

import pytest

from backend.ingestion.models import ExtractionError
from backend.ingestion.pdf import extract_text_with_pages, validate_pdf


class TestValidatePdf:
    def test_valid_pdf_accepted(self, simple_pdf):
        validate_pdf(simple_pdf)  # should not raise

    def test_non_pdf_rejected(self, non_pdf_bytes):
        with pytest.raises(ExtractionError, match="not a PDF"):
            validate_pdf(non_pdf_bytes)

    def test_encrypted_pdf_rejected(self, encrypted_pdf):
        with pytest.raises(ExtractionError, match="encrypted|password"):
            validate_pdf(encrypted_pdf)

    def test_empty_pdf_rejected(self):
        # A PDF with no pages
        from pypdf import PdfWriter

        writer = PdfWriter()
        import io

        output = io.BytesIO()
        writer.write(output)
        empty_pdf = output.getvalue()

        with pytest.raises(ExtractionError, match="no pages|no extractable"):
            validate_pdf(empty_pdf)


class TestExtractTextWithPages:
    def test_single_page_extraction(self, simple_pdf):
        result = extract_text_with_pages(simple_pdf)

        assert result["page_count"] == 1
        assert len(result["pages"]) == 1
        assert result["pages"][0]["number"] == 1
        assert "Hello" in result["pages"][0]["text"]

    def test_multi_page_extraction(self, multi_page_pdf):
        result = extract_text_with_pages(multi_page_pdf)

        assert result["page_count"] == 3
        assert len(result["pages"]) == 3
        assert result["pages"][0]["number"] == 1
        assert result["pages"][1]["number"] == 2
        assert result["pages"][2]["number"] == 3

    def test_page_numbers_are_one_based(self, multi_page_pdf):
        result = extract_text_with_pages(multi_page_pdf)

        for page in result["pages"]:
            assert page["number"] >= 1

    def test_text_normalized(self, multi_page_pdf):
        result = extract_text_with_pages(multi_page_pdf)

        for page in result["pages"]:
            # Text should not have leading/trailing whitespace or collapse multiple spaces
            text = page["text"]
            assert text == text.strip()
            assert "  " not in text  # multiple spaces collapsed
