"""Admin endpoints: upload, approve, list."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.config import get_settings
from backend.ingestion.pipeline import ingest_and_store
from backend.services.deps import get_embedder, get_shared_store

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


@router.get("/documents")
def list_documents() -> dict:
    return {"documents": get_shared_store().list_documents()}
