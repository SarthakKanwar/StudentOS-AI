"""Document ingestion pipeline.

Stages:
  1. PDF validation (type, size, encryption, extractability)
  2. Page-preserving text extraction (1-based page numbers)
  3. Tokenization and chunking (tiktoken, cl100k_base)
  4. Structured document/chunk output

Persistence to Supabase and embeddings via Foundry are separate concerns.
"""

from .models import Chunk, Document, ExtractionError
from .pipeline import ingest_and_store, ingest_pdf_file

__all__ = ["Chunk", "Document", "ExtractionError", "ingest_and_store", "ingest_pdf_file"]
