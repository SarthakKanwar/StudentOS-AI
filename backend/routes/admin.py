"""Admin endpoints: upload, approve, list."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.config import get_settings
from backend.ingestion.pipeline import ingest_and_store
from backend.services.deps import get_embedder, get_shared_store, get_upload_store
from backend.services.file_storage import PDF_MEDIA_TYPE

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


class UploadResponse(BaseModel):
    document_id: str | None
    title: str
    status: str
    page_count: int
    chunk_count: int
    error_message: str | None = None


class ApproveResponse(BaseModel):
    document_id: str
    status: str


class DeleteResponse(BaseModel):
    document_id: str
    deleted: bool
    file_removed: bool


def _serve_pdf(document_id: str, document: dict) -> FileResponse:
    """Serve the stored original, inline so the browser's PDF viewer opens it."""
    path = get_upload_store().get(document_id)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail="The original file for this document is not stored. Documents "
            "ingested before file storage was added have no saved copy.",
        )

    return FileResponse(
        path,
        media_type=PDF_MEDIA_TYPE,
        filename=document.get("original_filename") or f"{document_id}.pdf",
        content_disposition_type="inline",
    )


@router.post("/admin/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
) -> UploadResponse:
    settings = get_settings()
    content = await file.read()

    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File is {size_mb:.1f} MB; maximum is {settings.max_upload_size_mb} MB",
        )

    suffix = Path(file.filename or "upload.pdf").suffix or ".pdf"
    tmp_dir = Path(tempfile.mkdtemp(prefix="studentos-upload-"))
    tmp_path = tmp_dir / (Path(file.filename or "upload.pdf").name)
    tmp_path.write_bytes(content)

    try:
        document = ingest_and_store(
            tmp_path,
            title.strip() or tmp_path.stem,
            embedder=get_embedder(),
            repository=get_shared_store(),
        )
    finally:
        tmp_path.unlink(missing_ok=True)
        tmp_dir.rmdir()

    # Keep the original bytes so the document can be opened later. Failed
    # documents are stored too, so an admin can see what was actually uploaded.
    if document.id:
        get_upload_store().save(document.id, content)

    return UploadResponse(
        document_id=document.id,
        title=document.title,
        status=document.status,
        page_count=document.page_count,
        chunk_count=len(document.chunks),
        error_message=document.error_message,
    )


@router.post("/admin/approve/{document_id}", response_model=ApproveResponse)
def approve_document(document_id: str) -> ApproveResponse:
    """ready → approved. Only now is the document retrievable."""
    store = get_shared_store()
    if not store.approve_document(document_id):
        raise HTTPException(
            status_code=409,
            detail="Document cannot be approved; it must exist and be in 'ready' status",
        )
    return ApproveResponse(document_id=document_id, status="approved")


@router.post("/admin/revoke/{document_id}", response_model=ApproveResponse)
def revoke_document(document_id: str) -> ApproveResponse:
    """approved → ready. Takes effect immediately, with no re-indexing."""
    store = get_shared_store()
    if not store.revoke_document(document_id):
        raise HTTPException(status_code=409, detail="Document is not currently approved")
    return ApproveResponse(document_id=document_id, status="ready")


@router.delete("/admin/documents/{document_id}", response_model=DeleteResponse)
def delete_document(document_id: str) -> DeleteResponse:
    """Permanently remove one document, its stored PDF and its indexed data.

    Works from any status. Chunks and embeddings go with it through the schema's
    cascade, so a deleted document stops being retrievable immediately.
    """
    store = get_shared_store()

    if store.get_document(document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")

    file_removed = get_upload_store().delete(document_id)
    deleted = store.delete_document(document_id)

    logger.info("deleted document %s (file_removed=%s)", document_id, file_removed)
    return DeleteResponse(document_id=document_id, deleted=deleted, file_removed=file_removed)


@router.get("/admin/documents/{document_id}/file")
def admin_document_file(document_id: str) -> FileResponse:
    """Admin view of the original PDF, at any status including failed."""
    document = get_shared_store().get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return _serve_pdf(document_id, document)


@router.get("/documents")
def list_documents() -> dict:
    return {"documents": get_shared_store().list_documents()}


@router.get("/documents/{document_id}/file")
def document_file(document_id: str) -> FileResponse:
    """Student-facing view of the original PDF — approved documents only.

    Lives beside the public document list rather than under /admin, and applies
    the same approved-only rule that retrieval does. Revoking a document closes
    this route immediately, exactly as it closes retrieval.
    """
    document = get_shared_store().get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.get("status") != "approved":
        raise HTTPException(
            status_code=403,
            detail="This document is not approved and cannot be viewed",
        )

    return _serve_pdf(document_id, document)
