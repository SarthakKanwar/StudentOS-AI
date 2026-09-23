"""Tests for tokenization and chunking."""

import pytest

from backend.config import get_pipeline_config
from backend.ingestion.chunker import CHUNK_ID_HEX_LENGTH, chunk_pages
from backend.ingestion.models import ExtractionError


def synthetic_pages(page_count=2, sentences_per_page=400):
    """Pages long enough to produce several chunks.

    Built directly rather than through a PDF: chunking is a pure function over
    page text, and the PDF fixtures are too short to cross a chunk boundary.
    Each page uses a distinct marker word so page attribution is checkable.
    """
    markers = ["Alpha", "Zulu", "Kilo", "Delta", "Echo"]
    return [
        {
            "number": n + 1,
            "text": " ".join(
                f"{markers[n % len(markers)]} regulation clause number {i}." for i in range(sentences_per_page)
            ),
        }
        for n in range(page_count)
    ]


class TestChunking:
    def test_simple_chunk_creation(self, multi_page_pdf):
        from backend.ingestion.pdf import extract_text_with_pages

        extracted = extract_text_with_pages(multi_page_pdf)
        chunks = chunk_pages(extracted["pages"])

        assert len(chunks) > 0

    def test_chunk_id_format(self, multi_page_pdf):
        from backend.ingestion.pdf import extract_text_with_pages

        extracted = extract_text_with_pages(multi_page_pdf)
        chunks = chunk_pages(extracted["pages"])

        for chunk in chunks:
            assert chunk.id.startswith("c_")
            assert len(chunk.id) == 2 + CHUNK_ID_HEX_LENGTH

    def test_chunk_id_deterministic(self, multi_page_pdf):
        from backend.ingestion.pdf import extract_text_with_pages

        extracted = extract_text_with_pages(multi_page_pdf)
        chunks1 = chunk_pages(extracted["pages"])
        chunks2 = chunk_pages(extracted["pages"])

        assert len(chunks1) == len(chunks2)
        for c1, c2 in zip(chunks1, chunks2):
            assert c1.id == c2.id

    def test_page_numbers_are_one_based(self, multi_page_pdf):
        from backend.ingestion.pdf import extract_text_with_pages

        extracted = extract_text_with_pages(multi_page_pdf)
        chunks = chunk_pages(extracted["pages"])

        for chunk in chunks:
            if chunk.page_start is not None:
                assert chunk.page_start >= 1
            if chunk.page_end is not None:
                assert chunk.page_end >= 1

    def test_page_start_lte_page_end(self, multi_page_pdf):
        from backend.ingestion.pdf import extract_text_with_pages

        extracted = extract_text_with_pages(multi_page_pdf)
        chunks = chunk_pages(extracted["pages"])

        for chunk in chunks:
            assert chunk.page_start <= chunk.page_end

    def test_chunk_size_follows_configuration(self):
        """Non-final chunks must be the configured size, not merely non-empty."""
        config = get_pipeline_config()
        expected = config.chunking.chunk_size_tokens

        chunks = chunk_pages(synthetic_pages())

        assert len(chunks) > 1, "fixture must cross a chunk boundary to test this"
        for chunk in chunks[:-1]:
            # strip() can shave a token at either edge.
            assert abs(chunk.token_count - expected) <= 5, (
                f"chunk {chunk.chunk_index} has {chunk.token_count} tokens, expected ~{expected}"
            )

    def test_consecutive_chunks_actually_overlap(self):
        """The start of each chunk must reappear inside its predecessor.

        With a 150-token overlap (~600 characters) the opening of chunk n+1 sits
        well inside chunk n. Without real overlap, retrieval would lose any
        passage that straddles a boundary.
        """
        chunks = chunk_pages(synthetic_pages())

        assert len(chunks) > 1, "fixture must produce multiple chunks"
        for earlier, later in zip(chunks, chunks[1:]):
            opening = later.content[:100]
            assert opening in earlier.content, (
                f"chunk {later.chunk_index} does not overlap chunk {earlier.chunk_index}"
            )

    def test_overlap_is_smaller_than_the_chunk(self):
        """Chunks must advance; identical neighbours would mean no progress."""
        chunks = chunk_pages(synthetic_pages())

        for earlier, later in zip(chunks, chunks[1:]):
            assert later.content != earlier.content

    def test_page_spanning_chunk_records_both_pages(self):
        """A chunk crossing a page break must carry both page numbers."""
        pages = synthetic_pages(page_count=2)
        chunks = chunk_pages(pages)

        spanning = [c for c in chunks if c.page_start != c.page_end]
        assert spanning, "fixture must produce at least one page-spanning chunk"

        for chunk in spanning:
            assert chunk.page_start < chunk.page_end
            # Marker words prove the chunk genuinely contains both pages.
            assert "Alpha" in chunk.content and "Zulu" in chunk.content

    def test_page_attribution_matches_chunk_content(self):
        """Every chunk's claimed pages must match the text it actually holds."""
        chunks = chunk_pages(synthetic_pages(page_count=3))
        markers = {1: "Alpha", 2: "Zulu", 3: "Kilo"}

        for chunk in chunks:
            claimed = set(range(chunk.page_start, chunk.page_end + 1))
            present = {page for page, word in markers.items() if word in chunk.content}
            assert claimed == present, (
                f"chunk {chunk.chunk_index} claims pages {sorted(claimed)} "
                f"but contains text from {sorted(present)}"
            )

    def test_chunk_ids_are_unique_within_a_document(self):
        chunks = chunk_pages(synthetic_pages(page_count=3))
        ids = [c.id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_same_text_in_different_documents_gets_different_ids(self):
        """Ids are the chunks primary key, so they are scoped per document."""
        pages = synthetic_pages()
        first = chunk_pages(pages, document_key="hash-of-document-a")
        second = chunk_pages(pages, document_key="hash-of-document-b")

        assert {c.id for c in first}.isdisjoint({c.id for c in second})

    def test_section_label_nullable(self, multi_page_pdf):
        from backend.ingestion.pdf import extract_text_with_pages

        extracted = extract_text_with_pages(multi_page_pdf)
        chunks = chunk_pages(extracted["pages"])

        # section_label is optional and can be None
        for chunk in chunks:
            # In MVP, we don't extract section labels, so these should all be None
            assert chunk.section_label is None or isinstance(chunk.section_label, str)

    def test_chunk_index_sequential(self, multi_page_pdf):
        from backend.ingestion.pdf import extract_text_with_pages

        extracted = extract_text_with_pages(multi_page_pdf)
        chunks = chunk_pages(extracted["pages"])

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_char_offsets_valid(self, multi_page_pdf):
        from backend.ingestion.pdf import extract_text_with_pages

        extracted = extract_text_with_pages(multi_page_pdf)
        chunks = chunk_pages(extracted["pages"])

        for chunk in chunks:
            assert chunk.char_start >= 0
            assert chunk.char_end >= chunk.char_start
