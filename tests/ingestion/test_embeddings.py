"""Foundry embedding client tests.

Every call is mocked: no Azure resource is contacted and no credential is used.
"""

import httpx
import pytest

from backend.foundry.embeddings import (
    EMBEDDING_DIMENSIONS,
    EmbeddingClient,
    EmbeddingError,
)

REAL_TOKEN = "fake-token-value-that-must-never-be-logged"


class FakeToken:
    def __init__(self, token=REAL_TOKEN, expires_on=9_999_999_999):
        self.token = token
        self.expires_on = expires_on


class FakeCredential:
    def __init__(self):
        self.calls = 0

    def get_token(self, scope):
        self.calls += 1
        return FakeToken()


class FakeResponse:
    def __init__(self, status_code, json_body=None, text=""):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text

    def json(self):
        return self._json


class FakeHttp:
    """Stands in for httpx.Client, returning queued responses in order."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    def post(self, url, json=None, headers=None):
        self.requests.append({"url": url, "json": json, "headers": headers})
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        pass


def embedding_body(count, dimensions=EMBEDDING_DIMENSIONS):
    return {
        "data": [
            {"index": i, "embedding": [0.01 * (i + 1)] * dimensions} for i in range(count)
        ]
    }


def make_client(responses, **kwargs):
    return EmbeddingClient(
        credential=FakeCredential(),
        http_client=FakeHttp(responses),
        max_attempts=kwargs.pop("max_attempts", 3),
        **kwargs,
    )


class TestEmbedTexts:
    def test_returns_one_vector_per_text_in_order(self):
        client = make_client([FakeResponse(200, embedding_body(3))])

        vectors = client.embed_texts(["a", "b", "c"])

        assert len(vectors) == 3
        assert all(len(v) == EMBEDDING_DIMENSIONS for v in vectors)
        assert vectors[0][0] == pytest.approx(0.01)
        assert vectors[2][0] == pytest.approx(0.03)

    def test_vectors_are_1536_dimensional(self):
        client = make_client([FakeResponse(200, embedding_body(1))])
        assert len(client.embed_texts(["only"])[0]) == 1536

    def test_out_of_order_response_is_reordered_by_index(self):
        body = {
            "data": [
                {"index": 1, "embedding": [0.2] * EMBEDDING_DIMENSIONS},
                {"index": 0, "embedding": [0.1] * EMBEDDING_DIMENSIONS},
            ]
        }
        client = make_client([FakeResponse(200, body)])

        vectors = client.embed_texts(["first", "second"])

        assert vectors[0][0] == pytest.approx(0.1)
        assert vectors[1][0] == pytest.approx(0.2)

    def test_empty_input_makes_no_request(self):
        http = FakeHttp([])
        client = EmbeddingClient(credential=FakeCredential(), http_client=http)

        assert client.embed_texts([]) == []
        assert http.requests == []

    def test_blank_text_is_rejected_before_any_request(self):
        http = FakeHttp([])
        client = EmbeddingClient(credential=FakeCredential(), http_client=http)

        with pytest.raises(EmbeddingError, match="empty"):
            client.embed_texts(["fine", "   "])
        assert http.requests == []

    def test_batches_are_split_by_batch_size(self):
        http = FakeHttp(
            [
                FakeResponse(200, embedding_body(2)),
                FakeResponse(200, embedding_body(2)),
                FakeResponse(200, embedding_body(1)),
            ]
        )
        client = EmbeddingClient(credential=FakeCredential(), http_client=http, batch_size=2)

        vectors = client.embed_texts(["a", "b", "c", "d", "e"])

        assert len(vectors) == 5
        assert len(http.requests) == 3
        assert [len(r["json"]["input"]) for r in http.requests] == [2, 2, 1]


class TestDimensionGuard:
    def test_wrong_dimension_is_rejected(self):
        """The pgvector column is vector(1536); a mismatch must not be stored."""
        client = make_client([FakeResponse(200, embedding_body(1, dimensions=768))])

        with pytest.raises(EmbeddingError, match="dimension is 768"):
            client.embed_texts(["text"])

    def test_missing_vector_is_rejected(self):
        client = make_client([FakeResponse(200, embedding_body(1))])

        with pytest.raises(EmbeddingError, match="Expected 2 embeddings"):
            client.embed_texts(["one", "two"])

    def test_malformed_response_is_rejected(self):
        client = make_client([FakeResponse(200, {"unexpected": "shape"})])

        with pytest.raises(EmbeddingError, match="schema"):
            client.embed_texts(["text"])


class TestRetries:
    def test_retries_on_429_then_succeeds(self, monkeypatch):
        monkeypatch.setattr("backend.foundry.embeddings.time.sleep", lambda _: None)
        http = FakeHttp(
            [
                FakeResponse(429, text="rate limited"),
                FakeResponse(200, embedding_body(1)),
            ]
        )
        client = EmbeddingClient(credential=FakeCredential(), http_client=http)

        assert len(client.embed_texts(["text"])) == 1
        assert len(http.requests) == 2

    def test_gives_up_after_max_attempts(self, monkeypatch):
        monkeypatch.setattr("backend.foundry.embeddings.time.sleep", lambda _: None)
        http = FakeHttp([FakeResponse(503, text="unavailable")] * 3)
        client = EmbeddingClient(credential=FakeCredential(), http_client=http, max_attempts=3)

        with pytest.raises(EmbeddingError, match="after 3 attempt"):
            client.embed_texts(["text"])
        assert len(http.requests) == 3

    def test_client_error_is_not_retried(self):
        """A 400 will not fix itself; retrying just burns quota."""
        http = FakeHttp([FakeResponse(400, text="bad request")])
        client = EmbeddingClient(credential=FakeCredential(), http_client=http)

        with pytest.raises(EmbeddingError, match="HTTP 400"):
            client.embed_texts(["text"])
        assert len(http.requests) == 1

    def test_network_error_is_retried(self, monkeypatch):
        monkeypatch.setattr("backend.foundry.embeddings.time.sleep", lambda _: None)
        http = FakeHttp(
            [httpx.ConnectError("boom"), FakeResponse(200, embedding_body(1))]
        )
        client = EmbeddingClient(credential=FakeCredential(), http_client=http)

        assert len(client.embed_texts(["text"])) == 1


class TestAuthentication:
    def test_uses_entra_bearer_token(self):
        http = FakeHttp([FakeResponse(200, embedding_body(1))])
        client = EmbeddingClient(credential=FakeCredential(), http_client=http)

        client.embed_texts(["text"])

        assert http.requests[0]["headers"]["Authorization"] == f"Bearer {REAL_TOKEN}"

    def test_token_is_cached_across_batches(self):
        credential = FakeCredential()
        http = FakeHttp([FakeResponse(200, embedding_body(1))] * 3)
        client = EmbeddingClient(credential=credential, http_client=http, batch_size=1)

        client.embed_texts(["a", "b", "c"])

        assert len(http.requests) == 3
        assert credential.calls == 1

    def test_expired_token_is_refreshed(self):
        credential = FakeCredential()
        http = FakeHttp([FakeResponse(200, embedding_body(1))] * 2)
        client = EmbeddingClient(credential=credential, http_client=http, batch_size=1)

        client.embed_texts(["a"])
        client._token_expires_at = 0  # simulate expiry
        client.embed_texts(["b"])

        assert credential.calls == 2

    def test_token_never_appears_in_an_error_message(self, monkeypatch):
        monkeypatch.setattr("backend.foundry.embeddings.time.sleep", lambda _: None)
        http = FakeHttp([FakeResponse(500, text="server exploded")] * 3)
        client = EmbeddingClient(credential=FakeCredential(), http_client=http)

        with pytest.raises(EmbeddingError) as exc_info:
            client.embed_texts(["text"])

        assert REAL_TOKEN not in str(exc_info.value)


class TestRequestShape:
    def test_targets_the_v1_embeddings_endpoint(self):
        http = FakeHttp([FakeResponse(200, embedding_body(1))])
        client = EmbeddingClient(credential=FakeCredential(), http_client=http)

        client.embed_texts(["text"])

        assert "/openai/v1/embeddings" in http.requests[0]["url"]
        assert "api-version=" in http.requests[0]["url"]

    def test_sends_the_configured_deployment(self):
        http = FakeHttp([FakeResponse(200, embedding_body(1))])
        client = EmbeddingClient(credential=FakeCredential(), http_client=http)

        client.embed_texts(["text"])

        assert http.requests[0]["json"]["model"] == "test-embedding-deployment"

    def test_model_version_is_the_deployment_name(self):
        client = make_client([])
        assert client.model_version == "test-embedding-deployment"
