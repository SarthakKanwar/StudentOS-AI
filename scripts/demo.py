#!/usr/bin/env python3
"""End-to-end demo against the real Foundry deployment.

    python scripts/demo.py

Requires an Entra login that can reach the Foundry endpoint (`az login`).
Storage is whatever get_store() selects: Supabase if configured, else local
SQLite. Nothing is deployed and no Azure resource is created.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.foundry.chat import ChatClient  # noqa: E402
from backend.foundry.embeddings import EmbeddingClient  # noqa: E402
from backend.ingestion.pipeline import ingest_and_store  # noqa: E402
from backend.services.answering import answer_question  # noqa: E402
from backend.services.store import get_store, store_backend_name  # noqa: E402

HANDBOOK = Path(__file__).parent.parent / "sample-data" / "cs-department-handbook.pdf"
TITLE = "CS Department Student Handbook, Autumn 2026"

ANSWERABLE = "When is the CS-402 Computer Networks end-term examination, and where is it held?"
UNANSWERABLE = "What is the campus parking fee for electric motorcycles?"


def rule(text):
    print(f"\n{'=' * 72}\n{text}\n{'=' * 72}")


def show(response):
    print(f"  response_type : {response.response_type}")
    print(f"  gate_outcome  : {response.gate_outcome}")
    print(f"  top_score     : {response.top_score:.4f}  (retrieved {response.retrieved})")
    print(f"  answer        : {response.answer}")
    for citation in response.citations:
        pages = (
            f"p.{citation.page_start}"
            if citation.page_start == citation.page_end
            else f"pp.{citation.page_start}-{citation.page_end}"
        )
        print(f"  citation      : {citation.document_title} | {pages} | {citation.chunk_id}")
        print(f"                  \"{citation.excerpt[:110]}...\"")


def main() -> int:
    if not HANDBOOK.is_file():
        print("Run scripts/generate_demo_pdf.py first.", file=sys.stderr)
        return 1

    store = get_store()
    embedder = EmbeddingClient()
    chat = ChatClient()

    rule(f"STORAGE: {store_backend_name()}")

    rule("STEP 1 - ADMIN INGESTS THE HANDBOOK")
    existing = [d for d in store.list_documents() if d["title"] == TITLE and d["status"] != "failed"]
    if existing:
        document_id = existing[0]["id"]
        print(f"  reusing already-ingested document {document_id}")
    else:
        document = ingest_and_store(HANDBOOK, TITLE, embedder=embedder, repository=store)
        if document.status == "failed":
            print(f"  FAILED: {document.error_message}", file=sys.stderr)
            return 1
        document_id = document.id
        print(f"  ingested {document.page_count} pages into {len(document.chunks)} chunks")
        print(f"  status={document.status}  id={document_id}")

    rule("STEP 2 - BEFORE APPROVAL, NOTHING IS RETRIEVABLE")
    for document in store.list_documents():
        if document["id"] == document_id and document["status"] == "approved":
            store.revoke_document(document_id)
            print("  (revoked from a previous run so the gate can be shown)")
    response = answer_question(ANSWERABLE, store, embedder, chat)
    show(response)

    rule("STEP 3 - ADMIN APPROVES THE DOCUMENT")
    print(f"  approved: {store.approve_document(document_id)}")

    rule("STEP 4 - ANSWERABLE QUESTION (expect: grounded + citation)")
    print(f"  Q: {ANSWERABLE}")
    answerable = answer_question(ANSWERABLE, store, embedder, chat)
    show(answerable)

    rule("STEP 5 - UNANSWERABLE QUESTION (expect: not found)")
    print(f"  Q: {UNANSWERABLE}")
    unanswerable = answer_question(UNANSWERABLE, store, embedder, chat)
    show(unanswerable)

    rule("STEP 6 - GATE 3: A FABRICATED CITATION MUST NOT PASS")

    class ForgingChat:
        """Stands in for a model that invents a citation."""

        def answer(self, question, results):
            from backend.foundry.chat import GroundedAnswer

            return GroundedAnswer(True, "The exam is on 1 January 1999.", ["c_deadbeefcafe"])

    forged = answer_question(ANSWERABLE, store, embedder, ForgingChat())
    show(forged)

    rule("RESULT")
    checks = [
        ("answerable question is grounded", answerable.response_type == "grounded"),
        ("grounded answer carries a citation", bool(answerable.citations)),
        ("citation has a real page number", all(c.page_start >= 1 for c in answerable.citations)),
        ("unanswerable question is not-found", unanswerable.response_type == "not_found"),
        ("forged citation blocked by gate 3", forged.response_type == "not_found"),
        ("forged answer text never surfaced", "1999" not in forged.answer),
    ]
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")

    embedder.close()
    chat.close()
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
