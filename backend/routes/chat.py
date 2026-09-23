"""Student chat endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.foundry.chat import AnswerError
from backend.foundry.embeddings import EmbeddingError
from backend.services.answering import NOT_FOUND_MESSAGE, answer_question
from backend.services.deps import get_chat_client, get_embedder, get_shared_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)


@router.post("/chat")
def chat(request: ChatRequest) -> dict:
    settings = get_settings()
    question = request.question.strip()

    if len(question) > settings.max_question_length:
        raise HTTPException(
            status_code=400,
            detail=f"Question exceeds {settings.max_question_length} characters",
        )

    try:
        response = answer_question(
            question,
            store=get_shared_store(),
            embedder=get_embedder(),
            chat_client=get_chat_client(),
        )
    except (EmbeddingError, AnswerError) as exc:
        # Fail closed: an upstream failure degrades to refusal, never to an
        # unsupported answer.
        logger.warning("answering failed, returning not-found: %s", exc)
        return {
            "response_type": "not_found",
            "answer": NOT_FOUND_MESSAGE,
            "citations": [],
            "gate_outcome": "upstream_error",
            "top_score": 0.0,
            "retrieved": 0,
        }

    return response.to_dict()
