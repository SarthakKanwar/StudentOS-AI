"""Tokenization and chunking.

architecture.md §6, §8.1: 800 token chunks, 150 token overlap, tiktoken/cl100k_base.
Chunks are identified with deterministic c_<short> IDs.
"""

import hashlib
from collections import deque

import tiktoken

from backend.config import get_pipeline_config
from .models import Chunk, ExtractionError


def chunk_pages(pages: list[dict], document_key: str = "") -> list[Chunk]:
    """Split extracted pages into overlapping chunks.

    Args:
        pages: list of {"number": int (1-based), "text": str}
        document_key: scopes chunk ids to one document (the file hash is used
            in the pipeline) so identical text in two documents cannot collide

    Returns:
        list of Chunk objects with deterministic IDs, page boundaries preserved

    Raises:
        ExtractionError if tokenization fails
    """
    config = get_pipeline_config()
    chunk_size = config.chunking.chunk_size_tokens
    overlap_size = config.chunking.chunk_overlap_tokens

    if config.chunking.tokenizer != "tiktoken" or config.chunking.encoding != "cl100k_base":
        raise ExtractionError(
            f"unsupported tokenizer: {config.chunking.tokenizer}/{config.chunking.encoding}"
        )

    try:
        enc = tiktoken.get_encoding("cl100k_base")
    except Exception as exc:
        raise ExtractionError(f"cannot load tokenizer: {exc}") from exc

    # Build a single text with page markers, track which page each char belongs to.
    full_text = ""
    page_map = []  # (char_idx) -> page_number (1-based)

    for page in pages:
        page_num = page["number"]
        page_text = page["text"]
        for char in page_text:
            page_map.append(page_num)
            full_text += char
        # Add a space between pages
        page_map.append(page_num)
        full_text += " "

    if not full_text.strip():
        return []

    # Tokenize the full text
    try:
        tokens = enc.encode(full_text)
    except Exception as exc:
        raise ExtractionError(f"cannot tokenize text: {exc}") from exc

    if not tokens:
        return []

    # Build token-to-char map. This is approximate since tokenization is lossy,
    # but it's good enough for metadata/verification.
    token_boundaries = []
    current_char_idx = 0

    for token_id in tokens:
        token_text = enc.decode([token_id])
        token_boundaries.append(current_char_idx)
        # Rough estimate: tokens usually map to multiple characters.
        current_char_idx += max(1, len(token_text))

    # Chunk with overlap
    chunks = []
    chunk_idx = 0
    token_pos = 0

    while token_pos < len(tokens):
        chunk_start_token = token_pos
        chunk_end_token = min(token_pos + chunk_size, len(tokens))

        # Map token range to character range
        if chunk_start_token < len(token_boundaries):
            chunk_start_char = token_boundaries[chunk_start_token]
        else:
            chunk_start_char = current_char_idx

        if chunk_end_token < len(token_boundaries):
            chunk_end_char = token_boundaries[chunk_end_token]
        else:
            chunk_end_char = len(full_text)

        # Avoid empty chunks
        if chunk_start_char >= chunk_end_char:
            token_pos += max(1, chunk_size - overlap_size)
            continue

        chunk_text = full_text[chunk_start_char:chunk_end_char].strip()
        if not chunk_text:
            token_pos += max(1, chunk_size - overlap_size)
            continue

        # Determine which pages this chunk spans
        pages_in_chunk = set()
        for char_idx in range(chunk_start_char, min(chunk_end_char, len(page_map))):
            if char_idx < len(page_map):
                pages_in_chunk.add(page_map[char_idx])

        if not pages_in_chunk:
            token_pos += max(1, chunk_size - overlap_size)
            continue

        page_start = min(pages_in_chunk)
        page_end = max(pages_in_chunk)

        # Generate deterministic chunk ID
        chunk_id = _generate_chunk_id(chunk_text, chunk_idx, document_key)

        # Count actual tokens in this chunk
        try:
            chunk_tokens = enc.encode(chunk_text)
            token_count = len(chunk_tokens)
        except Exception as exc:
            raise ExtractionError(f"cannot count tokens for chunk {chunk_idx}: {exc}") from exc

        chunk = Chunk(
            id=chunk_id,
            content=chunk_text,
            page_start=page_start,
            page_end=page_end,
            chunk_index=chunk_idx,
            char_start=chunk_start_char,
            char_end=chunk_end_char,
            token_count=token_count,
            section_label=None,  # V2+: extract from headings
        )

        chunks.append(chunk)
        chunk_idx += 1

        # Advance with overlap
        token_pos += max(1, chunk_size - overlap_size)

    return chunks


CHUNK_ID_HEX_LENGTH = 12


def _generate_chunk_id(chunk_text: str, chunk_index: int, document_key: str = "") -> str:
    """Generate a deterministic, short chunk ID.

    Format: c_<12-hex-chars>, e.g. c_7f2a91c4e08b (architecture.md §8.1).

    Determinism: same text, index and document always produce the same id
    within an ingestion run. Stability across re-ingestion is not required.

    Width: 12 hex chars, not 6. This id is the chunks table primary key, and at
    the 2,000-chunk scale of NFR-10 a 6-char id carries an ~11% birthday
    collision probability (~53% at 5,000), which would surface as an insert
    failure part-way through ingestion. 12 chars drops that below 1e-8.

    document_key scopes the id to one document so that identical text at the
    same index in two documents does not collide.
    """
    combined = f"{document_key}:{chunk_index}:{chunk_text}"
    digest = hashlib.sha256(combined.encode()).hexdigest()
    return f"c_{digest[:CHUNK_ID_HEX_LENGTH]}"
