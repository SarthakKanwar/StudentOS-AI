"""Hybrid retrieval: dense cosine fused with FTS5 keyword ranking.

Dense embeddings under-weight rare literal tokens. A chunk holding a table of
many subjects embeds as a blur of all of them, so a question naming one subject
loses to a long document *about* that subject. These tests build exactly that
shape — one table chunk against several syllabus chunks — and assert the table
chunk is reachable.

No Azure call is made; the embedder is the deterministic bag-of-words stand-in.
"""

import pytest

from backend.config import get_pipeline_config
from backend.ingestion.models import Chunk, Document
from backend.services.answering import gate1_retrieval_sufficient
from backend.services.sqlite_store import (
    SqliteStore,
    build_fts_query,
    reciprocal_rank_fusion,
)
from backend.services.store import SearchResult

from test_demo_flow import BagOfWordsEmbedder

TABLE_TEXT = (
    "End Term Examinations (ETE) Question Paper Format and Rubrics S. No. Subject Code "
    "Subject Name Exam Type Total Marks Duration (In Mins) MCQ 1 Marks MCQ 2 Marks "
    "Coding 5 Marks Coding 10 Marks 1 24APS4101 Applied Probability and Random Processes "
    "ETE 80 180 40 20 - 2 24CAI0201 Database Management Systems ETE 60 180 15 10 3 1 "
    "3 24CAI0202 Java Programming ETE 60 180 15 10 3 1 4 24CAI0203 Supervised and "
    "Unsupervised Learning ETE 80 120 40 20 - -"
)

# Long, wordy syllabus prose that mentions the subject name constantly — the
# competition that crowds out the table under dense-only retrieval.
SYLLABUS_TEXT = " ".join(
    [
        "Database Management Systems course plan objectives outcomes. "
        "This Database Management Systems course covers relational models, "
        "normalisation, transactions and concurrency in Database Management Systems."
    ]
    * 12
)


def make_chunk(chunk_id: str, content: str, index: int, page: int = 1) -> Chunk:
    return Chunk(
        id=chunk_id,
        content=content,
        page_start=page,
        page_end=page,
        chunk_index=index,
        char_start=0,
        char_end=len(content),
        token_count=max(1, len(content) // 4),
    )


@pytest.fixture
def store(tmp_path):
    instance = SqliteStore(tmp_path / "hybrid.db")
    yield instance
    instance.close()


@pytest.fixture
def embedder():
    return BagOfWordsEmbedder()


def add_document(store, embedder, title, chunks, approve=True):
    document_id = store.create_document(
        Document(title=title, original_filename=f"{title}.pdf", file_hash=title, page_count=1)
    )
    store.store_chunks(document_id, chunks)
    store.store_embeddings(
        chunks, embedder.embed_texts([c.content for c in chunks]), "fake-bow"
    )
    store.mark_ready(document_id)
    if approve:
        store.approve_document(document_id)
    return document_id


@pytest.fixture
def corpus(store, embedder):
    """One table chunk against eight syllabus chunks, all approved."""
    table_id = add_document(store, embedder, "exam-format", [make_chunk("c_table000001", TABLE_TEXT, 0)])
    add_document(
        store,
        embedder,
        "dbms-syllabus",
        [make_chunk(f"c_syllabus{i:04d}", SYLLABUS_TEXT, i) for i in range(8)],
    )
    return table_id


# ──────────────────────────────────────────────────── query construction ──


class TestFtsQueryBuilding:
    def test_ordinary_question_becomes_quoted_terms(self):
        assert build_fts_query("What is the duration?") == '"What" OR "is" OR "the" OR "duration"'

    def test_course_codes_and_numbers_survive(self):
        query = build_fts_query("subject 24CAI0201 duration 180 mins")
        assert '"24CAI0201"' in query
        assert '"180"' in query

    @pytest.mark.parametrize(
        "hostile",
        [
            'duration" OR chunks_fts MATCH "x',
            "NEAR(a b) AND *",
            "^start -minus :colon",
            'a" OR "1"="1',
            "((((",
        ],
    )
    def test_fts_operators_cannot_escape_from_user_input(self, hostile):
        """Only alphanumeric runs survive, each quoted — no operator can leak."""
        query = build_fts_query(hostile)
        if query is None:
            return
        for token in query.split(" OR "):
            assert token.startswith('"') and token.endswith('"')
            assert '"' not in token[1:-1]

    @pytest.mark.parametrize("empty", ["", "   ", "?!.,;:", "a", None])
    def test_unusable_input_returns_none(self, empty):
        assert build_fts_query(empty) is None


class TestKeywordSearchSafety:
    def test_hostile_input_does_not_crash(self, store, corpus):
        for hostile in ['" OR "', "MATCH *", "((((", "", "   ", "NEAR()"]:
            assert isinstance(store.keyword_search(hostile, 10), list)

    def test_unusable_query_returns_empty(self, store, corpus):
        assert store.keyword_search("?!,.", 10) == []


# ───────────────────────────────────────────────────── approval filtering ──


class TestApprovedOnly:
    def test_unapproved_document_is_invisible_to_keyword_search(self, store, embedder):
        add_document(
            store, embedder, "unapproved", [make_chunk("c_secret000001", TABLE_TEXT, 0)],
            approve=False,
        )

        assert store.keyword_search("24CAI0201 Database Management Systems", 10) == []

    def test_revoking_removes_a_document_from_keyword_search(self, store, embedder):
        document_id = add_document(
            store, embedder, "revocable", [make_chunk("c_revoke000001", TABLE_TEXT, 0)]
        )
        assert store.keyword_search("24CAI0201", 10) == ["c_revoke000001"]

        store.revoke_document(document_id)

        assert store.keyword_search("24CAI0201", 10) == []

    def test_failed_document_is_invisible_to_keyword_search(self, store, embedder):
        document_id = store.create_document(
            Document(title="f", original_filename="f.pdf", file_hash="f", page_count=1)
        )
        store.store_chunks(document_id, [make_chunk("c_failed000001", TABLE_TEXT, 0)])
        store.mark_failed(document_id, "broken")

        assert store.keyword_search("24CAI0201", 10) == []

    def test_hybrid_search_never_returns_unapproved_chunks(self, store, embedder, corpus):
        add_document(
            store, embedder, "hidden", [make_chunk("c_hidden000001", TABLE_TEXT, 0)],
            approve=False,
        )

        results = store.search(
            embedder.embed_texts(["24CAI0201 duration"])[0], 20, query_text="24CAI0201 duration"
        )

        assert all(r.chunk_id != "c_hidden000001" for r in results)


# ──────────────────────────────────────────────────────── keyword finding ──


class TestKeywordRetrieval:
    def test_exact_course_code_finds_the_table(self, store, corpus):
        assert store.keyword_search("24CAI0201", 10)[0] == corpus_table_id()

    def test_exact_table_value_finds_the_table(self, store, corpus):
        assert "c_table000001" in store.keyword_search("180 Duration Mins", 10)

    def test_natural_language_question_finds_the_table(self, store, corpus):
        hits = store.keyword_search(
            "What is the duration of the Database Management Systems ETE?", 25
        )
        assert "c_table000001" in hits

    def test_punctuation_and_numbers_are_handled(self, store, corpus):
        hits = store.keyword_search("duration (in mins)? 180 -- ETE, 24CAI0201.", 25)
        assert "c_table000001" in hits


def corpus_table_id():
    return "c_table000001"


# ──────────────────────────────────────────────────────────────── fusion ──


class TestFusion:
    def test_rrf_rewards_agreement_between_rankings(self):
        """Top in both rankings beats top in only one."""
        fused = reciprocal_rank_fusion([["a", "b", "c"], ["a", "c", "b"]], k=5)

        assert fused["a"] > fused["b"]
        assert fused["a"] > fused["c"]

    def test_rrf_is_symmetric_for_mirrored_rankings(self):
        """Reversed lists: the extremes tie, because each is first once."""
        fused = reciprocal_rank_fusion([["a", "b", "c"], ["c", "b", "a"]], k=5)

        assert fused["a"] == pytest.approx(fused["c"])
        assert fused["b"] < fused["a"]

    def test_rrf_handles_ids_present_in_only_one_ranking(self):
        fused = reciprocal_rank_fusion([["a"], ["b"]], k=5)
        assert set(fused) == {"a", "b"}

    def test_hybrid_lifts_the_table_chunk_above_dense_only(self, store, embedder, corpus):
        """The regression this whole change exists for."""
        question = "What is the duration of the Database Management Systems ETE?"
        vector = embedder.embed_texts([question])[0]

        dense = [r.chunk_id for r in store.search(vector, 20)]
        hybrid = [r.chunk_id for r in store.search(vector, 20, query_text=question)]

        assert hybrid.index("c_table000001") < dense.index("c_table000001")

    def test_table_chunk_reaches_the_model_context(self, store, embedder, corpus):
        config = get_pipeline_config().retrieval
        question = "What is the duration of the Database Management Systems ETE?"

        results = store.search(
            embedder.embed_texts([question])[0], config.top_k, query_text=question
        )
        context = [r.chunk_id for r in results[: config.max_context_chunks]]

        assert "c_table000001" in context

    def test_no_duplicate_chunks_after_fusion(self, store, embedder, corpus):
        question = "Database Management Systems duration 180 ETE 24CAI0201"
        results = store.search(
            embedder.embed_texts([question])[0], 20, query_text=question
        )

        ids = [r.chunk_id for r in results]
        assert len(ids) == len(set(ids))

    def test_ordering_is_deterministic(self, store, embedder, corpus):
        question = "What is the duration of the Database Management Systems ETE?"
        vector = embedder.embed_texts([question])[0]

        first = [r.chunk_id for r in store.search(vector, 20, query_text=question)]
        second = [r.chunk_id for r in store.search(vector, 20, query_text=question)]

        assert first == second


# ──────────────────────────────────────── score integrity and Gate 1 ──


class TestScoreAndGateIntegrity:
    def test_score_stays_the_true_cosine_not_the_fused_rank(self, store, embedder, corpus):
        """Fusion reorders; it must never overwrite the similarity value."""
        question = "What is the duration of the Database Management Systems ETE?"
        vector = embedder.embed_texts([question])[0]

        dense = {r.chunk_id: r.score for r in store.search(vector, 50)}
        hybrid = {r.chunk_id: r.score for r in store.search(vector, 50, query_text=question)}

        for chunk_id, score in hybrid.items():
            assert score == pytest.approx(dense[chunk_id])
            assert 0.0 <= score <= 1.0

    def test_max_cosine_is_unchanged_by_hybrid(self, store, embedder, corpus):
        """Gate 1's input must be identical with and without fusion."""
        question = "What is the duration of the Database Management Systems ETE?"
        vector = embedder.embed_texts([question])[0]

        dense_max = max(r.score for r in store.search(vector, 20))
        hybrid_max = max(r.score for r in store.search(vector, 20, query_text=question))

        assert dense_max == pytest.approx(hybrid_max)

    def test_gate1_reads_the_maximum_not_the_first_result(self):
        """Under fusion the best-ordered chunk need not be the most similar."""
        results = [
            SearchResult("c_a", "x", "d", "T", 1, 1, score=0.20),
            SearchResult("c_b", "y", "d", "T", 1, 1, score=0.55),
        ]

        assert gate1_retrieval_sufficient(results, tau_min=0.35) is True

    def test_gate1_still_refuses_when_nothing_is_similar_enough(self):
        results = [
            SearchResult("c_a", "x", "d", "T", 1, 1, score=0.20),
            SearchResult("c_b", "y", "d", "T", 1, 1, score=0.11),
        ]

        assert gate1_retrieval_sufficient(results, tau_min=0.35) is False

    def test_gate1_refuses_on_empty_results(self):
        assert gate1_retrieval_sufficient([], tau_min=0.35) is False


class TestFallbackBehaviour:
    def test_hybrid_disabled_falls_back_to_dense_order(self, store, embedder, corpus, monkeypatch):
        from backend.config import get_pipeline_config as loader

        question = "What is the duration of the Database Management Systems ETE?"
        vector = embedder.embed_texts([question])[0]
        dense = [r.chunk_id for r in store.search(vector, 20)]

        config = loader()
        monkeypatch.setattr(config.retrieval, "hybrid_enabled", False)

        assert [r.chunk_id for r in store.search(vector, 20, query_text=question)] == dense

    def test_no_query_text_falls_back_to_dense_order(self, store, embedder, corpus):
        question = "What is the duration of the Database Management Systems ETE?"
        vector = embedder.embed_texts([question])[0]

        assert [r.chunk_id for r in store.search(vector, 20)] == [
            r.chunk_id for r in store.search(vector, 20, query_text=None)
        ]

    def test_keyword_index_is_backfilled_for_an_existing_database(self, tmp_path, embedder):
        """A database written before the index existed must still be searchable."""
        path = tmp_path / "legacy.db"
        first = SqliteStore(path)
        add_document(first, embedder, "legacy", [make_chunk("c_legacy000001", TABLE_TEXT, 0)])
        first._conn.executescript("drop trigger chunks_fts_after_insert; drop table chunks_fts;")
        first._conn.commit()
        first.close()

        reopened = SqliteStore(path)
        try:
            assert reopened.fts_available is True
            assert reopened.keyword_search("24CAI0201", 10) == ["c_legacy000001"]
        finally:
            reopened.close()

    def test_deleting_a_document_clears_its_keyword_index_rows(self, store, embedder):
        document_id = add_document(
            store, embedder, "temp", [make_chunk("c_temp00000001", TABLE_TEXT, 0)]
        )
        assert store.keyword_search("24CAI0201", 10) == ["c_temp00000001"]

        store.delete_document(document_id)

        assert store.keyword_search("24CAI0201", 10) == []
