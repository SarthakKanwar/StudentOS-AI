"""Foundry embedding client.

Talks to the verified `text-embedding-3-small` deployment through the Azure
OpenAI v1 API surface (architecture.md §10.1).

Authentication is Microsoft Entra ID via DefaultAzureCredential — no API key is
created, read or stored. In production this resolves to the container's managed
identity; locally it resolves to the developer's `az login`. Tokens are held in
memory only and never logged.
"""

from __future__ import annotations

import logging
import time

import httpx
from azure.core.exceptions import ClientAuthenticationError
from azure.identity import DefaultAzureCredential

from backend.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Verified against the live deployment on 2026-09-23 (architecture.md §10.1).
# The pgvector column is declared vector(1536); a mismatch must fail loudly
# rather than write vectors the database will reject or silently truncate.
EMBEDDING_DIMENSIONS = 1536

TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"

# The catalogue reports embeddingsMaxInputs = 2048 for this model. A smaller
# batch keeps request bodies modest and makes a partial failure cheaper to retry.
DEFAULT_BATCH_SIZE = 64

RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})


class EmbeddingError(RuntimeError):
    """Raised when embeddings cannot be produced. Never carries credentials."""


class EmbeddingClient:
    """Batched embedding client for the configured Foundry deployment."""

    def __init__(
        self,
        settings: Settings | None = None,
        credential=None,
        http_client: httpx.Client | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_attempts: int = 3,
    ) -> None:
        self._settings = settings or get_settings()
        self._credential = credential
        self._http = http_client
        self._owns_http = http_client is None
        self._batch_size = batch_size
        self._max_attempts = max_attempts
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    # ------------------------------------------------------------------ auth

    def _get_token(self) -> str:
        """Fetch (and cache) an Entra access token. The value is never logged."""
        now = time.time()
        if self._token and now < self._token_expires_at - 60:
            return self._token

        if self._credential is None:
            self._credential = DefaultAzureCredential()

        try:
            access_token = self._credential.get_token(TOKEN_SCOPE)
        except ClientAuthenticationError as exc:
            raise EmbeddingError(
                "Entra authentication failed. Run `az login`, or grant the "
                "deployment's managed identity the Cognitive Services User role. "
                f"({type(exc).__name__})"
            ) from exc

        self._token = access_token.token
        self._token_expires_at = float(access_token.expires_on)
        logger.debug("acquired Entra token for embeddings (value not logged)")
        return self._token

    # ------------------------------------------------------------------ http

    @property
    def _url(self) -> str:
        endpoint = self._settings.foundry_endpoint.rstrip("/")
        return f"{endpoint}/openai/v1/embeddings?api-version={self._settings.foundry_api_version}"

    def _client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=60.0)
        return self._http

    def _post_batch(self, inputs: list[str]) -> list[list[float]]:
        payload = {
            "model": self._settings.foundry_embedding_deployment,
            "input": inputs,
        }

        last_error = ""
        for attempt in range(1, self._max_attempts + 1):
            headers = {
                "Authorization": f"Bearer {self._get_token()}",
                "Content-Type": "application/json",
            }
            try:
                response = self._client().post(self._url, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                last_error = f"network error: {type(exc).__name__}"
                if attempt == self._max_attempts:
                    break
                time.sleep(2 ** (attempt - 1))
                continue

            if response.status_code == 200:
                return self._parse(response.json(), expected=len(inputs))

            # Body may echo the request but never the Authorization header.
            last_error = f"HTTP {response.status_code}: {response.text[:300]}"
            if response.status_code not in RETRYABLE_STATUS or attempt == self._max_attempts:
                break
            time.sleep(2 ** (attempt - 1))

        raise EmbeddingError(f"Embedding request failed after {self._max_attempts} attempt(s). {last_error}")

    @staticmethod
    def _parse(body: dict, expected: int) -> list[list[float]]:
        try:
            rows = sorted(body["data"], key=lambda row: row["index"])
            vectors = [row["embedding"] for row in rows]
        except (KeyError, TypeError) as exc:
            raise EmbeddingError("Embedding response did not match the expected schema") from exc

        if len(vectors) != expected:
            raise EmbeddingError(f"Expected {expected} embeddings, received {len(vectors)}")

        for vector in vectors:
            if len(vector) != EMBEDDING_DIMENSIONS:
                raise EmbeddingError(
                    f"Embedding dimension is {len(vector)}, expected {EMBEDDING_DIMENSIONS}. "
                    "The pgvector column is declared vector(1536); refusing to store a mismatch."
                )
        return vectors

    # ----------------------------------------------------------------- public

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed texts in order, batching as needed.

        Raises EmbeddingError on auth failure, transport failure, a schema
        mismatch, or any vector whose dimension is not 1536.
        """
        if not texts:
            return []
        if any(not text.strip() for text in texts):
            raise EmbeddingError("Cannot embed an empty or whitespace-only text")

        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            vectors.extend(self._post_batch(batch))
        return vectors

    @property
    def model_version(self) -> str:
        """Recorded on every stored vector so a re-embed can be detected."""
        return self._settings.foundry_embedding_deployment

    def close(self) -> None:
        if self._owns_http and self._http is not None:
            self._http.close()
            self._http = None

    def __enter__(self) -> "EmbeddingClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
