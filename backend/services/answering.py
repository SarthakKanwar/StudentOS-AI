"""Grounded answering: the three gates.

Gate 1  retrieval sufficiency   deterministic code, BEFORE the model is called
Gate 2  model self-report       the model's own grounded flag
Gate 3  citation verification   deterministic code, AFTER the model answers

Every failure path lands on not-found. There is no route that returns an
ungrounded answer, which is the whole point of the product.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field

from backend.config import get_pipeline_config

logger = logging.getLogger(__name__)

NOT_FOUND_MESSAGE = "Information not found in the approved university documents."

EXCERPT_CHARS = 240


@dataclass
class Citation:
    chunk_id: str
    document_title: str
    page_start: int | None
    page_end: int | None
    excerpt: str
    score: float


@dataclass
class AnswerResponse:
    response_type: str  # "grounded" | "not_found"
    answer: str
    citations: list[Citation] = field(default_factory=list)
    gate_outcome: str = ""  # which gate decided, for the demo debug view
    top_score: float = 0.0
    retrieved: int = 0

    def to_dict(self) -> dict:
        return {
            "response_type": self.response_type,
            "answer": self.answer,
            "citations": [asdict(c) for c in self.citations],
            "gate_outcome": self.gate_outcome,
            "top_score": round(self.top_score, 4),
            "retrieved": self.retrieved,
        }


def _not_found(gate_outcome: str, top_score: float = 0.0, retrieved: int = 0) -> AnswerResponse:
    return AnswerResponse(
        response_type="not_found",
        answer=NOT_FOUND_MESSAGE,
        citations=[],
        gate_outcome=gate_outcome,
        top_score=top_score,
        retrieved=retrieved,
    )


def gate1_retrieval_sufficient(results, tau_min: float) -> bool:
    """Is there any chunk similar enough to be worth asking the model about?

    Runs before any model call, so an unanswerable question costs nothing and
    cannot produce a hallucination.
    """
    return bool(results) and results[0].score >= tau_min


def gate3_verify_citations(citations: list[str], results, store) -> list[str]:
    """Return the subset of citations that genuinely resolve.

    A citation survives only if it names a chunk that was actually retrieved for
    this query, whose document is still approved right now, and which carries
    usable page information. A model that invents an id fails here because the
    id will not be in the retrieved set.
    """
    retrieved_by_id = {r.chunk_id: r for r in results}
    verified: list[str] = []

    for chunk_id in citations:
        result = retrieved_by_id.get(chunk_id)
        if result is None:
            logger.warning("gate 3 rejected unretrieved citation %s", chunk_id)
            continue
        if hasattr(store, "is_chunk_approved") and not store.is_chunk_approved(chunk_id):
            logger.warning("gate 3 rejected citation %s: document no longer approved", chunk_id)
            continue
        if result.page_start is None or result.page_start < 1:
            logger.warning("gate 3 rejected citation %s: invalid page information", chunk_id)
            continue
        verified.append(chunk_id)

    return verified


def answer_question(question: str, store, embedder, chat_client) -> AnswerResponse:
    """Run the full grounded-answering flow."""
    config = get_pipeline_config()
    tau_min = config.grounding.tau_min
    top_k = config.retrieval.top_k
    max_context = config.retrieval.max_context_chunks

    question = (question or "").strip()
    if not question:
        return _not_found("empty_question")

    query_vector = embedder.embed_texts([question])[0]
    results = store.search(query_vector, top_k)
    top_score = results[0].score if results else 0.0

    # ---- GATE 1 -------------------------------------------------------------
    if not gate1_retrieval_sufficient(results, tau_min):
        logger.info("gate 1 stopped the query (top_score=%.4f < %.2f)", top_score, tau_min)
        return _not_found("gate1_insufficient_retrieval", top_score, len(results))

    context = results[:max_context]

    model_answer = chat_client.answer(question, context)

    # ---- GATE 2 -------------------------------------------------------------
    if not model_answer.grounded:
        logger.info("gate 2 stopped the query: model reported insufficient evidence")
        return _not_found("gate2_model_not_grounded", top_score, len(results))

    # ---- GATE 3 -------------------------------------------------------------
    verified_ids = gate3_verify_citations(model_answer.citations, context, store)

    if not verified_ids:
        logger.info("gate 3 stopped the query: no citation resolved")
        return _not_found("gate3_no_valid_citations", top_score, len(results))

    if not model_answer.answer.strip():
        return _not_found("empty_answer_text", top_score, len(results))

    by_id = {r.chunk_id: r for r in context}
    citations = [
        Citation(
            chunk_id=cid,
            document_title=by_id[cid].document_title,
            page_start=by_id[cid].page_start,
            page_end=by_id[cid].page_end,
            excerpt=by_id[cid].content[:EXCERPT_CHARS].strip(),
            score=round(by_id[cid].score, 4),
        )
        for cid in verified_ids
    ]

    return AnswerResponse(
        response_type="grounded",
        answer=model_answer.answer.strip(),
        citations=citations,
        gate_outcome="passed_all_gates",
        top_score=top_score,
        retrieved=len(results),
    )
