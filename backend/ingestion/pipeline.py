"""Complete ingestion pipeline: validate → extract → chunk → embed → persist.

Architecture.md §6: the ingestion pipeline from PDF to searchable chunks.

`ingest_pdf_file` is purely local and needs no cloud resources.
`ingest_and_store` adds Foundry embeddings and Supabase persistence.
"""

import logging
from pathlib import Path

from .chunker import chunk_pages
from .models import Document, ExtractionError
from .pdf import (
    extract_text_with_pages,
    has_extractable_text,
    validate_pdf_structure,
)

logger = logging.getLogger(__name__)


def _ocr_pages(file_content: bytes, ocr_client) -> dict:
    """Run the OCR fallback and return pages in the standard shape.

    Raises ExtractionError so the caller handles it exactly like any other
    extraction failure — a scanned document that cannot be read becomes
    `failed` with a readable reason, never an empty `ready` document.
    """
    from .ocr import OcrError, get_ocr_client

    client = ocr_client if ocr_client is not None else get_ocr_client()
    if client is None:
        raise ExtractionError(
            "No extractable text found; this is a scanned PDF and OCR is disabled"
        )

    try:
        return client.extract_pages(file_content)
    except OcrError as exc:
        raise ExtractionError(str(exc)) from exc


def ingest_pdf_file(pdf_path: Path, title: str, ocr_client=None) -> Document:
    """Ingest a PDF file end-to-end.

    Args:
        pdf_path: path to the PDF file
        title: human-readable document title

    Returns:
        Document with chunks extracted and metadata populated

    Status is set to 'ready' on success, or 'failed' with an error_message.
    No persistence to Supabase occurs here; that is a later step.
    """
    # Read file
    try:
        file_content = pdf_path.read_bytes()
    except Exception as exc:
        return Document(
            title=title,
            original_filename=pdf_path.name,
            file_hash="",
            page_count=0,
            status="failed",
            error_message=f"Cannot read file: {exc}",
        )

    # Create document record with file hash
    doc = Document.from_file(pdf_path, title, file_content)

    # VALIDATE — structure only. The text check happens next, because a scanned
    # PDF is structurally fine and should reach OCR rather than be rejected.
    try:
        validate_pdf_structure(file_content)
    except ExtractionError as exc:
        doc.status = "failed"
        doc.error_message = str(exc)
        return doc

    # EXTRACT — text layer when there is one, OCR only when there is not.
    try:
        if has_extractable_text(file_content):
            extracted = extract_text_with_pages(file_content)
        else:
            logger.info("no text layer found; falling back to OCR")
            extracted = _ocr_pages(file_content, ocr_client)
        doc.page_count = extracted["page_count"]
    except ExtractionError as exc:
        doc.status = "failed"
        doc.error_message = str(exc)
        return doc

    # CHUNK
    try:
        doc.chunks = chunk_pages(extracted["pages"], document_key=doc.file_hash)
    except ExtractionError as exc:
        doc.status = "failed"
        doc.error_message = str(exc)
        return doc

    # If no chunks were generated from non-empty text, fail
    if not doc.chunks and sum(len(p["text"]) for p in extracted["pages"]) > 0:
        doc.status = "failed"
        doc.error_message = "No chunks could be generated from the extracted text"
        return doc

    # Success
    doc.status = "ready"
    return doc


def ingest_and_store(
    pdf_path: Path,
    title: str,
    embedder=None,
    repository=None,
    ocr_client=None,
) -> Document:
    """Ingest a PDF and persist it with embeddings.

    Stages: validate → extract → chunk → embed (Foundry) → store (Supabase).

    The document row is written as `processing` before any chunk is stored and
    only becomes `ready` once every chunk and embedding has landed. If any stage
    fails, partially written chunks are deleted and the row is marked `failed`
    with a readable reason — a half-ingested document is never left looking
    healthy, because a `ready` document with missing chunks would silently
    answer questions from an incomplete corpus.

    `embedder` and `repository` are injectable so this can be tested without
    touching Azure or Supabase.
    """
    from backend.foundry.embeddings import EmbeddingClient, EmbeddingError
    from backend.services.persistence import DocumentRepository, PersistenceError

    # Local stages first — cheap, and no cloud resource is touched if they fail.
    # OCR is the one exception, and it only runs for a PDF with no text layer.
    doc = ingest_pdf_file(pdf_path, title, ocr_client=ocr_client)
    local_failure = doc.error_message if doc.status == "failed" else None

    repository = repository or DocumentRepository()

    # Record the document even when local ingestion failed, so an admin can see
    # the failure and its reason (FR-2.8, FR-2.10).
    document_id = repository.create_document(doc)
    doc.id = document_id

    if local_failure:
        repository.mark_failed(document_id, local_failure)
        return doc

    owns_embedder = embedder is None
    embedder = embedder or EmbeddingClient()

    try:
        vectors = embedder.embed_texts([chunk.content for chunk in doc.chunks])
        repository.store_chunks(document_id, doc.chunks)
        repository.store_embeddings(doc.chunks, vectors, embedder.model_version)
    except (EmbeddingError, PersistenceError) as exc:
        reason = str(exc)
        logger.warning("ingestion failed for document %s: %s", document_id, reason)
        _unwind(repository, document_id, reason)
        doc.status = "failed"
        doc.error_message = reason
        return doc
    finally:
        if owns_embedder:
            embedder.close()

    repository.mark_ready(document_id)
    doc.status = "ready"
    return doc


def _unwind(repository, document_id: str, reason: str) -> None:
    """Delete partial chunks and record the failure.

    Cleanup is best-effort: if deleting the chunks itself fails, marking the
    document `failed` still matters more, because status is what gates
    retrieval. Orphaned chunks attached to a non-approved document are
    unreachable either way.
    """
    try:
        repository.delete_chunks(document_id)
    except Exception as exc:
        logger.warning("could not delete partial chunks for %s: %s", document_id, exc)
    try:
        repository.mark_failed(document_id, reason)
    except Exception as exc:
        logger.error("could not mark document %s failed: %s", document_id, exc)
