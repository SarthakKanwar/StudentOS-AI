# StudentOS — Requirements Specification

**Status:** Draft for review
**Last Updated:** 2026-09-23
**Supersedes:** the product description in the initial `README.md` and `architecture.md` drafts

---

## 1. Product Definition

StudentOS is an **AI-powered student assistant that answers questions strictly from an approved set of university documents.**

It is deliberately **not** a general-purpose chatbot. The product's value comes from a guarantee, not from breadth:

> If the answer is in the approved knowledge base, StudentOS finds it and cites it.
> If it is not, StudentOS says so — it never invents university-specific facts.

### 1.1 Target User Story

> A student asks *"When is my Computer Networks exam?"* and gets the date, the source document, and the page — without opening a single PDF.

### 1.2 Reference Interaction

**Student:** "When is my Computer Networks exam?"

**StudentOS:**
> Your Computer Networks end-term exam is scheduled for 14 December 2026 at 10:00 AM.
>
> 📚 Based on `exam_dates.pdf` · Page 3
>
> ✓ Grounded in university documents

**Student:** "What's the dress code for convocation?"

**StudentOS:**
> I couldn't find information about this in the approved university documents.
>
> I searched 4 documents but found nothing relevant to the convocation dress code. You may want to check with the administration office directly.

The second response is **as important as the first.** A confidently wrong exam date is worse than no answer, because a student may act on it.

---

## 2. Glossary

| Term | Meaning in this project |
|---|---|
| **Knowledge base (KB)** | The set of admin-approved university documents the system is allowed to answer from |
| **Chunk** | A small passage of a document (a few hundred words) stored with its embedding, used as the unit of retrieval |
| **Embedding** | A numeric vector representing the meaning of a chunk, used for similarity search |
| **Retrieval** | Finding the chunks most likely to contain the answer to a question |
| **Grounding** | The property that every factual claim in an answer traces back to retrieved chunks |
| **RAG** | Retrieval-Augmented Generation — retrieve first, then let the model write using only what was retrieved |
| **Not-found response** | The explicit, designed refusal issued when the KB does not support an answer |
| **Prompt injection** | Text inside a document that tries to issue instructions to the model, e.g. "Ignore previous instructions" |
| **Foundry** | Microsoft/Azure AI Foundry — the hosted runtime that serves the chat and embedding models |

---

## 3. Functional Requirements

Requirements are tagged **[MVP]** (required for the graded deliverable), **[V2]** (desirable, post-MVP), or **[FUT]** (future / not planned for this term).

### FR-1 — Student Question Answering

| ID | Requirement | Priority |
|---|---|---|
| FR-1.1 | A student can submit a natural-language question through a chat interface | MVP |
| FR-1.2 | The system automatically retrieves relevant passages from the KB — the student never selects a document manually | MVP |
| FR-1.3 | When the KB supports an answer, the system returns an answer grounded in retrieved passages | MVP |
| FR-1.4 | Every grounded answer displays at least one source attribution (document name + page/section where available) | MVP |
| FR-1.5 | When the KB does not sufficiently support an answer, the system returns an explicit not-found response | MVP |
| FR-1.6 | The system never states a university-specific fact that is not present in retrieved passages | MVP |
| FR-1.7 | A student can click a citation to view the supporting passage text | MVP |
| FR-1.8 | Answers stream token-by-token so the interface feels responsive | V2 |
| FR-1.9 | Follow-up questions use prior turns for context resolution ("when is *it*?") | V2 |
| FR-1.10 | A student can open the source PDF at the cited page | V2 |
| FR-1.11 | A student can give thumbs-up/down feedback on an answer | V2 |

### FR-2 — Document Ingestion & Knowledge Base Management

| ID | Requirement | Priority |
|---|---|---|
| FR-2.1 | An admin can upload a document (PDF at minimum) | MVP |
| FR-2.2 | Uploads are validated: file type, size limit, and non-empty extractable text | MVP |
| FR-2.3 | Text is extracted with page numbers preserved | MVP |
| FR-2.4 | Extracted text is split into overlapping chunks with stable identifiers | MVP |
| FR-2.5 | Each chunk stores metadata: document id, document title, page number, chunk index, character offsets | MVP |
| FR-2.6 | Each chunk is embedded and indexed for similarity search | MVP |
| FR-2.7 | A document is only searchable after an admin marks it **approved** | MVP |
| FR-2.8 | An admin can list documents with ingestion status (`uploaded` → `processing` → `ready` → `approved`, or `failed`) | MVP |
| FR-2.9 | An admin can revoke approval; revoked documents immediately stop being retrievable | MVP |
| FR-2.10 | Ingestion failures surface a readable reason (e.g. "scanned PDF — no extractable text") | MVP |
| FR-2.11 | Re-uploading a document creates a new version rather than silently overwriting | V2 |
| FR-2.12 | Scanned/image PDFs are OCR-processed | FUT |
| FR-2.13 | DOCX, HTML, and spreadsheet ingestion | FUT |

### FR-3 — Grounding & Safety

| ID | Requirement | Priority |
|---|---|---|
| FR-3.1 | Retrieved document text is passed to the model as **data**, never as system instructions | MVP |
| FR-3.2 | Instructions embedded inside documents are ignored (see `security.md`) | MVP |
| FR-3.3 | The model returns a structured result containing an answer, citations, and a sufficiency flag | MVP |
| FR-3.4 | Every citation returned by the model is verified to correspond to an actually-retrieved chunk before display | MVP |
| FR-3.5 | An answer with zero valid citations is converted into a not-found response | MVP |
| FR-3.6 | Ingestion flags documents containing injection-like patterns for admin review | V2 |
| FR-3.7 | A second-pass entailment check verifies each answer sentence against its cited chunk | V2 |

### FR-4 — Authentication & Authorization

| ID | Requirement | Priority |
|---|---|---|
| FR-4.1 | Students authenticate before using the chat | MVP |
| FR-4.2 | Two roles exist: `student` and `admin` | MVP |
| FR-4.3 | Only admins can upload, approve, or delete documents | MVP |
| FR-4.4 | A student can only see their own conversation history | MVP |
| FR-4.5 | Sign-in is restricted to a university email domain | V2 |
| FR-4.6 | Per-course or per-cohort document visibility scoping | FUT |

### FR-5 — Evaluation & Observability

| ID | Requirement | Priority |
|---|---|---|
| FR-5.1 | A versioned evaluation question set is stored in the repository | MVP |
| FR-5.2 | An evaluation run can be executed from a script and produces a scored report | MVP |
| FR-5.3 | Metrics include answer accuracy, not-found correctness, citation validity, and injection resistance | MVP |
| FR-5.4 | Each query logs retrieval scores, decision path, latency, and token usage | MVP |
| FR-5.5 | Evaluation runs in CI on pull requests touching retrieval or prompts | V2 |

---

## 4. Non-Functional Requirements

| ID | Category | Requirement | Target |
|---|---|---|---|
| NFR-1 | **Correctness** | Hallucinated university-specific facts | **0 tolerated** in the evaluation set |
| NFR-2 | **Correctness** | Correct answers on known-answer questions | ≥ 90% |
| NFR-3 | **Correctness** | Correct refusals on out-of-KB questions | ≥ 95% |
| NFR-4 | **Correctness** | Citation validity (cited chunk exists and supports the claim) | 100% of displayed citations resolve |
| NFR-5 | **Security** | Prompt-injection attempts that alter behaviour | 0 successful in the adversarial set |
| NFR-6 | **Performance** | End-to-end answer latency (p95) | ≤ 6 s non-streaming; ≤ 2 s to first token when streaming |
| NFR-7 | **Performance** | Retrieval latency (p95) | ≤ 500 ms |
| NFR-8 | **Cost** | Total cloud spend for the project | ≤ $50, hard ceiling $100 |
| NFR-9 | **Cost** | Marginal cost per student question | ≤ $0.01 |
| NFR-10 | **Scale** | KB size supported | 50 documents / ~2,000 chunks (demo scale) |
| NFR-11 | **Scale** | Concurrent users | 10 (demo scale) |
| NFR-12 | **Reliability** | Model/API failure behaviour | Fail closed — show an error, never a fabricated answer |
| NFR-13 | **Maintainability** | Prompts, thresholds, and chunking params live in version-controlled config, not hardcoded | — |
| NFR-14 | **Privacy** | No student question content sent to any service other than the configured Foundry endpoint and Supabase | — |
| NFR-15 | **Auditability** | Every answer reconstructible from logs: question, retrieved chunk ids, scores, decision | — |
| NFR-16 | **Accessibility** | Keyboard navigable; citations readable by screen reader | WCAG 2.1 AA for the chat view |

---

## 5. MVP Scope (The Graded Deliverable)

The MVP is the smallest system that credibly demonstrates the core guarantee.

**In scope:**

1. Admin uploads PDFs → extraction → chunking → embeddings → indexed
2. Admin approval gate before a document becomes answerable
3. Student login (Supabase Auth)
4. Chat interface: ask → automatic retrieval → grounded answer with citations
5. Explicit not-found response when unsupported
6. Prompt-injection defence with a passing adversarial test set
7. Evaluation script covering all five test categories
8. Deployed and demonstrable end-to-end

**Deliberately excluded from MVP:** streaming, multi-turn context resolution, OCR, non-PDF formats, document versioning, feedback capture, per-course scoping, analytics dashboards.

---

## 6. Future Features (Post-MVP, Not This Term)

- OCR for scanned documents
- Multi-format ingestion (DOCX, HTML, XLSX)
- Per-course / per-cohort document visibility
- Conversation memory and clarifying-question flows
- Proactive notifications ("your exam is in 3 days")
- Calendar / LMS integration
- Multilingual question answering
- Student feedback loop feeding retrieval tuning
- Answer caching for repeated questions

---

## 7. Explicitly Out of Scope

These are **not** being built, and the reasons are architectural — they should be defended as deliberate choices in the presentation.

| Out of scope | Why |
|---|---|
| **General-knowledge Q&A** ("explain TCP handshake") | Dilutes the grounding guarantee; the product's value is the KB boundary. The system refuses and says why. |
| **Fine-tuning a model on university data** | Expensive, slow to update, and *worsens* attribution — a fine-tuned model cannot cite a page. RAG is strictly better here (ADR-002). |
| **Multi-agent runtime** | Explicitly rejected. One retrieval step, one model call, deterministic validation. Agents add nondeterminism, cost, and failure surface with no benefit for this problem. |
| **Autonomous actions** (registering for courses, emailing staff) | Write actions require a trust and authorization model far beyond project scope. Read-only by design. |
| **Personalized academic advice / grade prediction** | Requires student-record data we do not have and raises consent issues. |
| **Real-time sync with university systems** | No access to such systems; the KB is admin-curated by design. |
| **Claude or any Anthropic model in the runtime** | Claude Code is a development tool only. The runtime model layer is Microsoft Foundry (ADR-003). |

---

## 8. Assumptions and Open Questions

**Assumptions made:**

- Documents are provided as digital (text-extractable) PDFs, not scans
- The document set is small enough that a single admin curates it manually
- Students and admins are the only actors; no staff/faculty role
- The demo runs against sample documents we create, not real university records

**Open questions requiring a decision — see §"Decisions Required" in the handover summary:**

1. Backend language: Python or Node/TypeScript
2. Vector store: Supabase `pgvector` or Azure AI Search
3. Whether real university PDFs will be supplied, or we author realistic samples
4. Deployment target for the demo

> **No assumptions have been made about actual university data.** All sample documents in `sample-data/` will be clearly synthetic and labelled as such.
