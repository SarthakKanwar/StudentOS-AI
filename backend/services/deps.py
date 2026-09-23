"""Shared singletons for the API.

Deliberately simple: the demo is single-process, so one store, one embedding
client and one chat client are enough.
"""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def get_shared_store():
    from .store import get_store

    return get_store()


@lru_cache(maxsize=1)
def get_upload_store():
    from .file_storage import UploadStore

    return UploadStore()


@lru_cache(maxsize=1)
def get_embedder():
    from backend.foundry.embeddings import EmbeddingClient

    return EmbeddingClient()


@lru_cache(maxsize=1)
def get_chat_client():
    from backend.foundry.chat import ChatClient

    return ChatClient()


def reset() -> None:
    """Used by tests to drop cached singletons."""
    get_shared_store.cache_clear()
    get_upload_store.cache_clear()
    get_embedder.cache_clear()
    get_chat_client.cache_clear()
