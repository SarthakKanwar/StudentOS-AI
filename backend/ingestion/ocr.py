"""OCR fallback for scanned PDFs.

Only reached when pypdf extracts no text at all. A PDF with an embedded text
layer never touches this module, so the normal ingestion path is unchanged and
still costs nothing.

Served by Azure AI Document Intelligence (`prebuilt-read`) on the same
AIServices resource that already hosts the chat and embedding deployments, so
no extra Azure resource, endpoint or credential is introduced. Authentication is
Entra ID, as everywhere else — there is no API key.

The result is returned in exactly the shape `extract_text_with_pages` produces,
so everything downstream — chunking, embedding, retrieval, citations — cannot
tell whether text came from the text layer or from OCR. That is deliberate:
page-level citations depend on the page numbering being identical either way,
and Document Intelligence returns a `pageNumber` per page that maps 1:1 onto the
PDF's own pages.

OCR output is untrusted document data, exactly like extracted text. Nothing here
treats it as instructions; it flows into the same delimited passage block the
answer model already receives.
"""

from __future__ import annotations

import logging
import time

import httpx
from azure.core.exceptions import ClientAuthenticationError
from azure.identity import DefaultAzureCredential

from backend.config import Settings, get_settings

logger = logging.getLogger(__name__)

TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"
RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})
POLL_INTERVAL_SECONDS = 2.0


class OcrError(RuntimeError):
    """Raised when OCR cannot produce usable page text.

    The message is surfaced to an admin as the document's failure reason, so it
    is written to be read by a person, not a developer.
    """


class DocumentIntelligenceOcr:
    """Reads a scanned PDF into page-numbered text."""

    def __init__(
        self,
        settings: Settings | None = None,
        credential=None,
        http_client: httpx.Client | None = None,
        max_attempts: int = 3,
    ) -> None:
        self._settings = settings or get_settings()
        self._credential = credential
        self._http = http_client
        self._owns_http = http_client is None
        self._max_attempts = max_attempts
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    # ------------------------------------------------------------------ auth

    def _get_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires_at - 60:
            return self._token
        if self._credential is None:
            self._credential = DefaultAzureCredential()
        try:
            access_token = self._credential.get_token(TOKEN_SCOPE)
        except ClientAuthenticationError as exc:
            raise OcrError(
                "OCR is unavailable: Entra authentication failed. Run `az login`, "
                "or grant the identity the Cognitive Services User role."
            ) from exc
        self._token = access_token.token
        self._token_expires_at = float(access_token.expires_on)
        return self._token

    def _client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=90.0)
        return self._http

    @property
    def _analyze_url(self) -> str:
        endpoint = self._settings.foundry_endpoint.rstrip("/")
        return (
            f"{endpoint}/documentintelligence/documentModels/"
            f"{self._settings.ocr_model}:analyze"
            f"?api-version={self._settings.ocr_api_version}"
        )

    # --------------------------------------------------------------- reading

    def extract_pages(self, file_content: bytes) -> dict:
        """Return {"page_count": int, "pages": [{"number": int, "text": str}]}.

        Raises OcrError with a readable reason for every failure mode, so the
        document can be marked failed rather than stored empty.
        """
        operation_url = self._submit(file_content)
        result = self._poll(operation_url)
        return self._to_pages(result)

    def _submit(self, file_content: bytes) -> str:
        last_error = ""
        for attempt in range(1, self._max_attempts + 1):
            headers = {
                "Authorization": f"Bearer {self._get_token()}",
                "Content-Type": "application/pdf",
            }
            try:
                response = self._client().post(
                    self._analyze_url, content=file_content, headers=headers
                )
            except httpx.HTTPError as exc:
                last_error = f"network error ({type(exc).__name__})"
                if attempt == self._max_attempts:
                    break
                time.sleep(2 ** (attempt - 1))
                continue

            if response.status_code == 202:
                operation_url = response.headers.get("operation-location")
                if not operation_url:
                    raise OcrError("OCR service accepted the file but returned no result location")
                return operation_url

            last_error = f"HTTP {response.status_code}"
            if response.status_code == 404:
                raise OcrError(
                    "OCR is not available on the configured Azure endpoint. The "
                    "resource must expose Azure AI Document Intelligence."
                )
            if response.status_code not in RETRYABLE_STATUS or attempt == self._max_attempts:
                break
            time.sleep(2 ** (attempt - 1))

        raise OcrError(f"OCR request failed after {self._max_attempts} attempt(s): {last_error}")

    def _poll(self, operation_url: str) -> dict:
        deadline = time.time() + self._settings.ocr_timeout_seconds

        while time.time() < deadline:
            time.sleep(POLL_INTERVAL_SECONDS)
            try:
                response = self._client().get(
                    operation_url, headers={"Authorization": f"Bearer {self._get_token()}"}
                )
            except httpx.HTTPError as exc:
                raise OcrError(f"OCR polling failed ({type(exc).__name__})") from exc

            if response.status_code != 200:
                raise OcrError(f"OCR polling failed with HTTP {response.status_code}")

            body = response.json()
            status = body.get("status")

            if status == "succeeded":
                return body.get("analyzeResult") or {}
            if status == "failed":
                detail = (body.get("error") or {}).get("message", "no detail given")
                raise OcrError(f"OCR processing failed: {detail}")

        raise OcrError(
            f"OCR timed out after {self._settings.ocr_timeout_seconds}s. The document "
            "may be unusually long or the service may be busy."
        )

    @staticmethod
    def _to_pages(analyze_result: dict) -> dict:
        """Map the OCR response onto the existing page contract.

        pageNumber comes straight from the service and is 1-based, matching the
        numbering `extract_text_with_pages` produces, so a citation to page 2 of
        a scanned document points at the same physical page it would for a text
        PDF. Pages are sorted defensively rather than trusting response order.
        """
        raw_pages = analyze_result.get("pages") or []
        if not raw_pages:
            raise OcrError("OCR returned no pages for this document")

        pages = []
        for raw in sorted(raw_pages, key=lambda p: p.get("pageNumber", 0)):
            lines = raw.get("lines") or []
            text = " ".join(line.get("content", "") for line in lines)
            # Same normalisation the text-layer path applies.
            text = " ".join(text.split())
            pages.append({"number": int(raw.get("pageNumber", len(pages) + 1)), "text": text})

        if not any(page["text"] for page in pages):
            raise OcrError(
                "OCR returned no usable text. The document may be blank, or the "
                "scan quality may be too low to read."
            )

        logger.info(
            "OCR produced text for %d of %d page(s)",
            sum(1 for p in pages if p["text"]),
            len(pages),
        )
        return {"page_count": len(pages), "pages": pages}

    def close(self) -> None:
        if self._owns_http and self._http is not None:
            self._http.close()
            self._http = None


def get_ocr_client() -> DocumentIntelligenceOcr | None:
    """Return an OCR client, or None when OCR is switched off."""
    if not get_settings().ocr_enabled:
        return None
    return DocumentIntelligenceOcr()
