"""End-to-end demo flow: ingest -> approve -> ask -> gated answer.

External services are faked. The embedder is a deterministic bag-of-words
vectoriser, so cosine similarity behaves realistically (a question sharing
wording with a chunk scores high, an unrelated one scores near zero) without
calling Azure.
"""

import hashlib
import re
from pathlib import Path

import pytest

from backend.foundry.chat import GroundedAnswer
from backend.foundry.embeddings import EMBEDDING_DIMENSIONS
from backend.ingestion.pipeline import ingest_and_store
from backend.services.answering import NOT_FOUND_MESSAGE, answer_question
from backend.services.sqlite_store import SqliteStore

HANDBOOK = Path(__file__).resolve().parents[1] / "sample-data" / "cs-department-handbook.pdf"

# Full-sentence questions, as a student would actually type them. Bag-of-words
# cosine is length-sensitive, so a two-word fragment scores below tau_min
# against an 800-token chunk; that is a property of this stand-in embedder, not
# of the product.
ATTENDANCE_QUESTION = (
    "What is the minimum percentage attendance a student must maintain in every "
    "registered course to sit the end-term examination?"
)


def bucket(word: str) -> int:
    return int(hashlib.sha256(word.encode()).hexdigest()[:8], 16) % EMBEDDING_DIMENSIONS


class BagOfWordsEmbedder:
    model_version = "fake-bow"

    def embed_texts(self, texts):
        vectors = []
        for text in texts:
            vector = [0.0] * EMBEDDING_DIMENSIONS
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                vector[bucket(word)] += 1.0
            vectors.append(vector)
        return vectors

    def close(self):
        pass


class ScriptedChat:
    """Returns a prepared model response, recording what it was asked."""

    def __init__(self, grounded=True, answer="An answer.", citations=None, use_first_chunk=True):
        self._grounded = grounded
        self._answer = answer
        self._citations = citations
        self._use_first_chunk = use_first_chunk
        self.received = None

    def answer(self, question, results):
        self.received = results
        citations = self._citations
        if citations is None:
            citations = [results[0].chunk_id] if (results and self._use_first_chunk) else []
        return GroundedAnswer(self._grounded, self._answer, list(citations))


@pytest.fixture
def store(tmp_path):
    instance = SqliteStore(tmp_path / "demo.db")
    yield instance
    instance.close()


@pytest.fixture
def ingested(store):
    if not HANDBOOK.is_file():
        pytest.skip("run scripts/generate_demo_pdf.py first")
    document = ingest_and_store(
        HANDBOOK,
        "CS Department Student Handbook, Autumn 2026",
        embedder=BagOfWordsEmbedder(),
        repository=store,
    )
    assert document.status == "ready"
    return document


# 1 ------------------------------------------------------------------ ingest


def test_pdf_can_be_ingested(ingested, store):
    assert ingested.page_count == 4
    assert len(ingested.chunks) >= 2

    documents = store.list_documents()
    assert len(documents) == 1
    assert documents[0]["status"] == "ready"
    assert documents[0]["chunk_count"] == len(ingested.chunks)


def test_ingested_document_is_not_yet_retrievable(ingested, store):
    """'ready' is not 'approved'. Nothing is searchable before a human approves."""
    embedder = BagOfWordsEmbedder()
    results = store.search(embedder.embed_texts(["computer networks exam"])[0], 8)
    assert results == []


# 2 ----------------------------------------------------------------- approve


def test_document_can_be_approved(ingested, store):
    assert store.approve_document(ingested.id) is True
    assert store.list_documents()[0]["status"] == "approved"


def test_approving_an_unknown_document_fails(store):
    assert store.approve_document("does-not-exist") is False


# 3 --------------------------------------------------------------- retrieval


def test_question_retrieves_relevant_content(ingested, store):
    store.approve_document(ingested.id)
    embedder = BagOfWordsEmbedder()

    results = store.search(
        embedder.embed_texts(["When is the CS-402 Computer Networks examination?"])[0], 8
    )

    assert results
    assert results[0].score > 0
    assert results == sorted(results, key=lambda r: r.score, reverse=True)
    # The winning chunk must actually contain the exam date.
    assert "14 December 2026" in results[0].content
    assert results[0].document_title.startswith("CS Department")
    assert results[0].page_start >= 1


def test_revoking_approval_immediately_stops_retrieval(ingested, store):
    store.approve_document(ingested.id)
    embedder = BagOfWordsEmbedder()
    query = embedder.embed_texts(["examination schedule"])[0]
    assert store.search(query, 8)

    store.revoke_document(ingested.id)
    assert store.search(query, 8) == []


# 4 ------------------------------------------------------- grounded answering


def test_grounded_question_produces_answer_with_citation(ingested, store):
    store.approve_document(ingested.id)
    chat = ScriptedChat(grounded=True, answer="The CS-402 examination is on 14 December 2026.")

    response = answer_question(
        "When is the CS-402 Computer Networks examination?",
        store=store,
        embedder=BagOfWordsEmbedder(),
        chat_client=chat,
    )

    assert response.response_type == "grounded"
    assert response.gate_outcome == "passed_all_gates"
    assert response.citations
    citation = response.citations[0]
    assert citation.chunk_id.startswith("c_")
    assert citation.document_title.startswith("CS Department")
    assert citation.page_start >= 1
    assert citation.page_end >= citation.page_start
    assert citation.excerpt


def test_model_only_sees_max_context_chunks(ingested, store):
    from backend.config import get_pipeline_config

    store.approve_document(ingested.id)
    chat = ScriptedChat()

    answer_question(ATTENDANCE_QUESTION, store, BagOfWordsEmbedder(), chat)

    assert len(chat.received) <= get_pipeline_config().retrieval.max_context_chunks


# 5 ---------------------------------------------------------------- not found


def test_unknown_question_produces_not_found(ingested, store):
    """Gate 1 stops it, so the model is never called."""
    store.approve_document(ingested.id)

    class ExplodingChat:
        def answer(self, question, results):
            raise AssertionError("Gate 1 must stop this before any model call")

    response = answer_question(
        "What is the campus parking fee for electric motorcycles?",
        store=store,
        embedder=BagOfWordsEmbedder(),
        chat_client=ExplodingChat(),
    )

    assert response.response_type == "not_found"
    assert response.answer == NOT_FOUND_MESSAGE
    assert response.gate_outcome == "gate1_insufficient_retrieval"
    assert response.citations == []


def test_empty_knowledge_base_returns_not_found(store):
    response = answer_question("anything at all", store, BagOfWordsEmbedder(), ScriptedChat())
    assert response.response_type == "not_found"
    assert response.gate_outcome == "gate1_insufficient_retrieval"


def test_gate2_rejects_when_model_reports_not_grounded(ingested, store):
    store.approve_document(ingested.id)
    chat = ScriptedChat(grounded=False, answer="")

    response = answer_question(
        "When is the CS-402 examination?", store, BagOfWordsEmbedder(), chat
    )

    assert response.response_type == "not_found"
    assert response.gate_outcome == "gate2_model_not_grounded"
    assert response.answer == NOT_FOUND_MESSAGE


# 6 ------------------------------------------------------------------ gate 3


def test_fabricated_citation_cannot_pass_gate3(ingested, store):
    """The core safety property: an invented chunk id never reaches the student."""
    store.approve_document(ingested.id)
    chat = ScriptedChat(
        grounded=True,
        answer="The examination is on 1 January 1999.",
        citations=["c_deadbeefcafe"],
    )

    response = answer_question(
        "When is the CS-402 examination?", store, BagOfWordsEmbedder(), chat
    )

    assert response.response_type == "not_found"
    assert response.gate_outcome == "gate3_no_valid_citations"
    assert "1 January 1999" not in response.answer


def test_answer_with_no_citations_is_rejected(ingested, store):
    store.approve_document(ingested.id)
    chat = ScriptedChat(grounded=True, answer="Trust me.", citations=[])

    response = answer_question(ATTENDANCE_QUESTION, store, BagOfWordsEmbedder(), chat)

    assert response.response_type == "not_found"
    assert response.gate_outcome == "gate3_no_valid_citations"


def test_gate3_keeps_valid_citations_and_drops_invented_ones(ingested, store):
    store.approve_document(ingested.id)
    embedder = BagOfWordsEmbedder()
    real_id = store.search(embedder.embed_texts([ATTENDANCE_QUESTION])[0], 8)[0].chunk_id

    chat = ScriptedChat(
        grounded=True,
        answer="Attendance must be at least 75 percent.",
        citations=[real_id, "c_000000000000"],
    )
    response = answer_question(ATTENDANCE_QUESTION, store, embedder, chat)

    assert response.response_type == "grounded"
    assert [c.chunk_id for c in response.citations] == [real_id]


def test_gate3_rejects_citation_whose_document_was_revoked(ingested, store):
    """Approval is re-checked at validation time, not just at retrieval time."""
    store.approve_document(ingested.id)
    embedder = BagOfWordsEmbedder()

    class RevokingChat(ScriptedChat):
        def answer(self, question, results):
            # Simulate an admin revoking approval while the model was thinking.
            store.revoke_document(ingested.id)
            return super().answer(question, results)

    response = answer_question(
        ATTENDANCE_QUESTION, store, embedder, RevokingChat(grounded=True, answer="75 percent.")
    )

    assert response.response_type == "not_found"
    assert response.gate_outcome == "gate3_no_valid_citations"
