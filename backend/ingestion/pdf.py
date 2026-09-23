"""PDF validation and page-preserving text extraction.

architecture.md §6: VALIDATE and EXTRACT stages.
security.md §5: upload constraints (PDF by content, size limit, reject encrypted).
"""

from io import BytesIO

import pypdf

from backend.config import get_settings
from .models import ExtractionError


def validate_pdf(file_content: bytes) -> None:
    """Validate that file_content is a readable, unencrypted PDF.

    Raises ExtractionError with a user-readable message if validation fails.
    Never logs secrets or file paths.
    """
    settings = get_settings()

    # Check size limit.
    size_mb = len(file_content) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise ExtractionError(
            f"File is {size_mb:.1f} MB; maximum size is {settings.max_upload_size_mb} MB"
        )

    # Check PDF magic bytes (content-based type check).
    if not file_content.startswith(b"%PDF"):
        raise ExtractionError("File is not a PDF (invalid magic bytes)")

    # Try to open as PDF; this also detects encrypted PDFs that pypdf cannot handle.
    try:
        reader = pypdf.PdfReader(BytesIO(file_content), strict=False)
    except Exception as exc:
        raise ExtractionError(f"Cannot read PDF: {str(exc).split(chr(10))[0]}") from exc

    # Reject encrypted PDFs. pypdf can decrypt some with a blank password, but we
    # reject them outright to be safe (architecture.md §6: "reject encrypted PDFs").
    if reader.is_encrypted:
        raise ExtractionError("File is encrypted or password-protected; encrypted PDFs cannot be processed")

    # Check that there is at least one page with extractable text.
    if not reader.pages:
        raise ExtractionError("PDF has no pages")

    has_text = False
    for page in reader.pages:
        if page.extract_text().strip():
            has_text = True
            break
    if not has_text:
        raise ExtractionError(
            "No extractable text found; scanned PDFs without OCR cannot be processed"
        )


def extract_text_with_pages(file_content: bytes) -> dict:
    """Extract text from PDF, preserving page boundaries.

    Returns:
        {
            "page_count": int,
            "pages": [
                {
                    "number": 1,  # 1-based
                    "text": "extracted text for page 1",
                },
                ...
            ]
        }

    Raises ExtractionError if extraction fails.
    """
    try:
        reader = pypdf.PdfReader(BytesIO(file_content), strict=False)
    except Exception as exc:
        raise ExtractionError(f"Cannot read PDF during extraction: {str(exc).split(chr(10))[0]}") from exc

    pages = []
    for page_idx, page in enumerate(reader.pages):
        page_number = page_idx + 1  # 1-based

        try:
            text = page.extract_text()
        except Exception as exc:
            raise ExtractionError(
                f"Cannot extract text from page {page_number}: {str(exc).split(chr(10))[0]}"
            ) from exc

        # Normalize: collapse whitespace, strip leading/trailing.
        text = " ".join(text.split())

        pages.append({"number": page_number, "text": text})

    return {
        "page_count": len(reader.pages),
        "pages": pages,
    }
