"""Local storage for the original uploaded PDFs.

Ingestion only ever kept the extracted text, so the uploaded file was discarded
once chunking finished. This module keeps the original bytes so a document can
be opened later, exactly as uploaded.

The filename is derived solely from the document id — a uuid4 hex string minted
by the store. A client-supplied filename or path is never used to build a path,
and the id is validated against a strict hex pattern before it touches the
filesystem, so path traversal is not reachable.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "data" / "uploads"

# Document ids are uuid4 hex (32 chars). Anything else never becomes a path.
_SAFE_ID = re.compile(r"\A[0-9a-f]{8,64}\Z", re.IGNORECASE)

PDF_MEDIA_TYPE = "application/pdf"


class UploadStore:
    """Stores one PDF per document id under a directory the app controls."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root else DEFAULT_UPLOAD_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, document_id: str) -> Path | None:
        """Resolve an id to its path, or None if the id is not a safe id."""
        if not document_id or not _SAFE_ID.match(document_id):
            return None

        candidate = (self.root / f"{document_id}.pdf").resolve()

        # Defence in depth: the pattern above already makes traversal
        # unreachable, but confirm the result is inside the root regardless.
        if self.root.resolve() not in candidate.parents:
            logger.warning("rejected upload path outside the storage root")
            return None

        return candidate

    def save(self, document_id: str, content: bytes) -> bool:
        """Write the original bytes unchanged. Returns False for an unsafe id."""
        path = self._path_for(document_id)
        if path is None:
            return False
        path.write_bytes(content)
        return True

    def get(self, document_id: str) -> Path | None:
        """Return the stored file's path, or None if it is not on disk."""
        path = self._path_for(document_id)
        if path is None or not path.is_file():
            return None
        return path

    def delete(self, document_id: str) -> bool:
        """Remove the stored file. Returns True only if a file was removed."""
        path = self._path_for(document_id)
        if path is None or not path.is_file():
            return False
        path.unlink()
        return True
