"""Data models for document ingestion.

architecture.md §8: schema for documents and chunks.
architecture.md §8.1: field semantics, 1-based pages, page spanning.
"""

from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from pathlib import Path


class ExtractionError(Exception):
    """Raised when PDF extraction fails in a non-recoverable way.

    Message should be user-readable and never contain secrets or file paths
    that would leak system information.
    """
    pass


@dataclass
class Chunk:
    """A fragment of a document that will become a searchable unit.

    Attributes:
        id: canonical `c_<short>` format, deterministic within an ingestion
        document_id: foreign key to documents table (will be None pre-persistence)
        content: the text of this chunk
        page_start: 1-based page number (or None if no page structure)
        page_end: 1-based page number; may equal page_start for single-page chunks
        chunk_index: 0-based sequence within the document
        char_start: character offset in the original extracted text (for future highlighting)
        char_end: character offset in the original extracted text
        section_label: human-readable heading/section, or None if not detected
        token_count: counted with tiktoken/cl100k_base
        created_at: timestamp on persistence; None until stored
    """
    id: str
    content: str
    page_start: int | None
    page_end: int | None
    chunk_index: int
    char_start: int
    char_end: int
    token_count: int
    document_id: str | None = None
    section_label: str | None = None
    created_at: datetime | None = None

    def __post_init__(self):
        if not self.id.startswith("c_"):
            raise ValueError("chunk id must use c_<short> format")
        if self.page_start is not None and self.page_end is not None:
            if self.page_start < 1 or self.page_end < 1:
                raise ValueError("page numbers are 1-based")
            if self.page_start > self.page_end:
                raise ValueError("page_start must not exceed page_end")


@dataclass
class Document:
    """A single uploaded/ingested document, metadata layer only.

    Attributes:
        title: human-readable document title, shown to students in citations
        original_filename: filename as uploaded (for admin display/provenance)
        file_hash: SHA-256 of the uploaded file (integrity + deduplication)
        page_count: number of pages in the PDF
        chunks: the extracted/chunked fragments
        injection_risk_flag: False for MVP; scanner is V2; never gates retrieval
        status: ingestion status (uploaded, processing, ready, approved, failed)
        error_message: human-readable reason if status=failed; None otherwise
        created_at: timestamp on persistence
        id: database ID (None until stored)
    """
    title: str
    original_filename: str
    file_hash: str
    page_count: int
    chunks: list[Chunk] = field(default_factory=list)
    injection_risk_flag: bool = False
    status: str = "uploaded"
    error_message: str | None = None
    created_at: datetime | None = None
    id: str | None = None

    def __post_init__(self):
        if self.status not in ("uploaded", "processing", "ready", "approved", "failed"):
            raise ValueError(f"invalid status: {self.status}")
        if self.status != "failed" and self.error_message is not None:
            raise ValueError("error_message should only be set when status=failed")
        if self.status == "failed" and not self.error_message:
            raise ValueError("error_message is required when status=failed")

    @classmethod
    def from_file(
        cls,
        pdf_path: Path,
        title: str,
        file_content: bytes | None = None,
    ) -> "Document":
        """Create a Document record from a PDF file.

        Args:
            pdf_path: path to the PDF file
            title: human-readable document title
            file_content: file bytes; if None, read from pdf_path

        Returns:
            Document with metadata populated (chunks not yet extracted)
        """
        if file_content is None:
            file_content = pdf_path.read_bytes()

        file_hash = sha256(file_content).hexdigest()
        original_filename = pdf_path.name

        return cls(
            title=title,
            original_filename=original_filename,
            file_hash=file_hash,
            page_count=0,  # updated by the extractor
            chunks=[],
            status="uploaded",
        )

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "id": self.id,
            "title": self.title,
            "original_filename": self.original_filename,
            "file_hash": self.file_hash,
            "page_count": self.page_count,
            "chunk_count": len(self.chunks),
            "chunks": [self._chunk_to_dict(c) for c in self.chunks],
            "injection_risk_flag": self.injection_risk_flag,
            "status": self.status,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @staticmethod
    def _chunk_to_dict(chunk: Chunk) -> dict:
        return {
            "id": chunk.id,
            "content": chunk.content[:100] + "..." if len(chunk.content) > 100 else chunk.content,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "chunk_index": chunk.chunk_index,
            "char_start": chunk.char_start,
            "char_end": chunk.char_end,
            "section_label": chunk.section_label,
            "token_count": chunk.token_count,
        }
