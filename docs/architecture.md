# StudentOS — System Architecture

**Status:** Draft for review
**Last Updated:** 2026-09-23
**Replaces:** the initial architecture draft dated 2026-09-23, which described a generic course-management platform and did not reflect the actual product

---

## 1. Architectural Principle

Everything in this design follows from one rule:

> **The model may only phrase what retrieval found. It may not supply facts of its own.**

The language model is treated as a *writer*, not as a *source of knowledge*. All university facts enter the system through the retrieval layer. This single constraint explains the prompt design, the validation layer, the citation model, and the not-found path.

A second rule governs safety:

> **Document content is untrusted input, exactly like a form field from the public internet.**

A PDF can contain hostile text. It is never allowed to occupy a position of authority in a prompt.

---

## 2. Tool Boundaries

These five things are conceptually separate and must not blur together.

| Tool | Role | Runs at |
|---|---|---|
| **Claude Code** | Development and orchestration — writing code, docs, reviews | Development time only. **Never in the runtime path.** |
| **Microsoft Foundry** | The runtime AI layer — chat completion and embedding models | Runtime |
| **Supabase** | Authentication, relational database, vector storage, file storage | Runtime |
| **GitHub** | Source control, issues, CI, project management | Development time |
| **Stitch** | UI/UX design of the chat and admin surfaces | Design time |

A student using StudentOS in production never touches Claude, GitHub, or Stitch. If the runtime ever depends on them, the boundary has been violated.

---

## 3. System Overview

```
┌────────────────────────────────────────────────────────────────────┐
│                          STUDENT'S BROWSER                          │
│    Chat UI  ·  Citation viewer  ·  Admin console (admins only)      │
└───────────────────────────────┬────────────────────────────────────┘
                                │  HTTPS / JSON  (JWT in header)
┌───────────────────────────────▼────────────────────────────────────┐
│                       BACKEND API (stateless)                       │
│                                                                     │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │  Routes  │→ │ Retrieval │→ │ Foundry  │→ │    Grounding     │  │
│  │  + Auth  │  │   Layer   │  │  Client  │  │    Validator     │  │
│  └──────────┘  └─────┬─────┘  └────┬─────┘  └────────┬─────────┘  │
│                      │             │                  │             │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │           Ingestion Pipeline (async, admin-triggered)         │  │
│  │   validate → extract → chunk → embed → index → await approval │  │
│  └──────────────────────────────────────────────────────────────┘  │
└──────────┬───────────────────────┬──────────────────┬──────────────┘
           │                       │                  │
┌──────────▼──────────┐  ┌─────────▼────────┐  ┌──────▼─────────────┐
│      SUPABASE       │  │ MICROSOFT FOUNDRY│  │   SUPABASE STORAGE │
│                     │  │                  │  │                    │
│  Auth (JWT, roles)  │  │  Chat model      │  │  Original PDFs     │
│  Postgres           │  │  Embedding model │  │  (private bucket)  │
│  pgvector index     │  │                  │  │                    │
│  Row Level Security │  │  No data stored  │  │                    │
└─────────────────────┘  └──────────────────┘  └────────────────────┘
```

The backend is **stateless**. All state lives in Supabase. This means it can be restarted or scaled without coordination, and it keeps the deployment cheap (see `cost-strategy.md`).

---

## 4. Component Responsibilities

### 4.1 Frontend

**Owns:** presentation and interaction. Nothing else.

- Chat view: question input, answer display, citation chips, not-found state
- Citation viewer: shows the exact retrieved passage backing a claim
- Admin console: upload, ingestion status, approve/revoke
- Auth screens (delegated to Supabase Auth)

**Explicitly does not:** call Foundry directly, hold API keys, decide whether an answer is grounded, or compute similarity. The frontend renders what the backend decided. Any frontend that could call the model directly would leak keys and bypass validation.

**Design source:** Stitch produces the visual design; the frontend implements it.

### 4.2 Backend API

**Owns:** every decision in the system.

- Verifies the Supabase JWT on every request and resolves the caller's role
- Orchestrates the query pipeline (§5)
- Runs the ingestion pipeline (§6)
- Holds the only credentials for Foundry
- Enforces the admin-approval gate
- Writes the audit log

It is the sole trust boundary. Nothing downstream of it is trusted; nothing upstream of it is authorized.

### 4.3 Retrieval Layer

**Owns:** turning a question into candidate passages.

- Embeds the question
- Runs vector similarity search over chunks whose document has `status = 'approved'` only
- Runs keyword search in parallel and fuses the rankings (hybrid retrieval)
- Returns the top-K chunks with scores and full metadata

It is a pure function of (question, current KB). It makes no judgement about sufficiency — that is the validator's job. Keeping these separate means retrieval quality and grounding strictness can be tuned independently.

### 4.4 Foundry Client

**Owns:** all communication with the runtime model layer.

- Wraps chat completion and embedding calls
- Constructs prompts using the strict role separation defined in `security.md`
- Enforces a JSON response schema
- Handles retries, timeouts, and token accounting
- Is the **only** module permitted to hold Foundry credentials

Isolating this makes the model provider swappable and gives one place to enforce prompt discipline.

> **Implementation note:** the exact Azure AI Foundry SDK surface (client construction, deployment naming, structured-output parameters) must be confirmed against current Azure documentation at implementation time. This document specifies the *capabilities* required — a chat completion endpoint supporting system/user role separation and JSON-constrained output, plus an embedding endpoint — not a specific function signature.

### 4.5 Grounding Validator

**Owns:** the decision to answer or refuse. This is the most important module in the system.

It applies three independent gates (detailed in `grounding-strategy.md`) and can convert any model output into a not-found response. It is deterministic code, not a model call — which means its behaviour is testable and explainable in the presentation.

### 4.6 Ingestion Pipeline

**Owns:** turning an uploaded file into retrievable chunks. Runs asynchronously; a slow PDF must never block an HTTP request.

### 4.7 Supabase

| Capability | Use |
|---|---|
| **Auth** | Email/password sign-in, JWT issuance, role claims |
| **Postgres** | All relational data (§8) |
| **pgvector** | Embedding storage and similarity search |
| **Row Level Security** | Database-enforced isolation — a student cannot read another student's conversations even if the API has a bug |
| **Storage** | Original PDFs in a private bucket, served via time-limited signed URLs |

RLS matters architecturally: it makes data isolation a property of the database, not of application correctness.

### 4.8 GitHub

Source control, issue tracking, pull-request review, and CI. The evaluation suite runs in CI so that a change degrading grounding is caught before merge.

---

## 5. Runtime Request Flow

This is the path every student question takes.

```
  Student question
        │
   ┌────▼─────────────────────────────────────┐
   │ 1. AUTHENTICATE & VALIDATE                │
   │    Verify JWT · resolve role              │
   │    Length limit · rate limit              │
   └────┬─────────────────────────────────────┘
        │
   ┌────▼─────────────────────────────────────┐
   │ 2. QUERY PROCESSING                       │
   │    Normalize whitespace/case              │
   │    Embed question (Foundry embedding)     │
   └────┬─────────────────────────────────────┘
        │
   ┌────▼─────────────────────────────────────┐
   │ 3. RETRIEVAL                              │
   │    Vector search  ─┐                      │
   │                    ├─ fuse (RRF) → top-K  │
   │    Keyword search ─┘                      │
   │    Filter: status = 'approved' only       │
   └────┬─────────────────────────────────────┘
        │
   ┌────▼─────────────────────────────────────┐
   │ 4. GATE 1 — RETRIEVAL SUFFICIENCY         │◄── cheapest gate:
   │    Is top score ≥ threshold?               │    no model call
   │    NO ──────────────────────► NOT FOUND    │    if it fails
   └────┬─────────────────────────────────────┘
        │ YES
   ┌────▼─────────────────────────────────────┐
   │ 5. CONTEXT ASSEMBLY                       │
   │    Order chunks · attach chunk ids        │
   │    Wrap in untrusted-data delimiters      │
   │    Fit to token budget                    │
   └────┬─────────────────────────────────────┘
        │
   ┌────▼─────────────────────────────────────┐
   │ 6. FOUNDRY MODEL CALL                     │
   │    System msg: rules only (never doc text)│
   │    User msg: question + delimited context │
   │    Response constrained to JSON schema    │
   │    temperature = 0                        │
   └────┬─────────────────────────────────────┘
        │
   ┌────▼─────────────────────────────────────┐
   │ 7. GATE 2 — MODEL SELF-REPORT             │
   │    sufficient == false? ───► NOT FOUND    │
   └────┬─────────────────────────────────────┘
        │ sufficient
   ┌────▼─────────────────────────────────────┐
   │ 8. GATE 3 — CITATION VERIFICATION         │◄── the gate that
   │    Every cited id in retrieved set?       │    catches a lying
   │    At least one valid citation?           │    model
   │    NO ──────────────────────► NOT FOUND   │
   └────┬─────────────────────────────────────┘
        │ YES
   ┌────▼─────────────────────────────────────┐
   │ 9. RESPONSE ASSEMBLY & LOGGING            │
   │    Attach doc titles + page numbers       │
   │    Persist message + citations + scores   │
   └────┬─────────────────────────────────────┘
        │
   ┌────▼──────────────┐      ┌────────────────────────┐
   │ GROUNDED ANSWER   │  OR  │  NOT-FOUND RESPONSE    │
   │ text + citations  │      │  reason + searched N   │
   └───────────────────┘      └────────────────────────┘
```

Three properties worth defending in the presentation:

1. **The cheap gate runs first.** If retrieval finds nothing, no model call happens — that saves money *and* removes any chance of hallucination.
2. **The last gate is deterministic code.** Even a model that ignores its instructions and invents a citation is caught, because the citation id will not resolve.
3. **Every failure path lands on not-found.** There is no code path that emits an ungrounded answer. Failure is always *toward* refusal.

---

## 6. Knowledge-Base / Document Pipeline

```
 UPLOAD          admin uploads PDF → stored in Supabase Storage
    │            record created with status = uploaded
    ▼
 VALIDATE        MIME type is PDF · size ≤ limit · not encrypted
    │            text is extractable (reject scans with a clear reason)
    │            scan for injection-like patterns → risk flag
    ▼
 EXTRACT         per-page text extraction, page numbers preserved
    │            normalize whitespace, de-hyphenate line breaks
    │            drop repeated headers/footers
    ▼
 CHUNK           ~800 tokens per chunk, ~150 token overlap
    │            respect paragraph boundaries where possible
    │            never span a page break without recording both pages
    ▼
 METADATA        each chunk carries:
    │              chunk_id · document_id · document_title
    │              page_number · chunk_index · char offsets
    ▼
 EMBED           batch chunks → Foundry embedding model → vectors
    │            store in pgvector column
    ▼
 INDEX           build/refresh vector index + full-text index
    │            status = ready
    ▼
 APPROVE         admin reviews and approves  →  status = approved
    │            ONLY NOW is the document retrievable
    ▼
 RETRIEVAL       available to student queries
```

**Why the approval gate exists:** it is the mechanism that makes "approved university documents" a real guarantee rather than a slogan. Ingestion is mechanical; approval is a human accepting responsibility for the content. It is also the injection kill-switch — a flagged document is quarantined until a person looks at it.

### 6.1 Document status — the single source of truth

`documents.status` is the **only** field that determines whether a document is retrievable. There is no separate `approved` boolean; a second representation of the same fact would be two things to keep in sync, and this is the most safety-critical flag in the system.

| Status | Meaning | Retrievable? |
|---|---|---|
| `uploaded` | File stored, not yet processed | No |
| `processing` | Extraction / chunking / embedding in progress | No |
| `ready` | Fully indexed, awaiting admin approval | No |
| `approved` | Admin has approved it | **Yes** |
| `failed` | Ingestion failed; `error_message` explains why | No |

**Legal transitions:**

```
uploaded → processing → ready → approved
                ↓         ↑        │
             failed       └────────┘   (revoke)
```

- **Approval:** `ready → approved`, also setting `approved_by` and `approved_at`.
- **Revocation:** `approved → ready`. The document stays fully indexed — only its retrievability changes, so re-approving is instant and requires no re-indexing.
- `approved_by` and `approved_at` are **metadata only**. They record who approved it and when; they never determine retrievability. They are retained after revocation as an audit trail of the prior approval.

**Every retrieval query filters on `status = 'approved'`.** Gate 3 re-checks the same condition at validation time (`grounding-strategy.md` §5, check 4), which is what makes revocation take effect immediately rather than at the next re-index.

---

## 7. Source Attribution

A citation is meaningful only if a student can verify it in seconds.

**Each citation carries:**

| Field | Example | Purpose |
|---|---|---|
| `document_title` | `exam_dates.pdf` | What to open |
| `page_number` | `3` | Where to look |
| `section` | `"End-Term Schedule"` | Human-readable anchor when available |
| `chunk_id` | `c_7f2a…` | Internal verification key |
| `excerpt` | `"CS-402 Computer Networks … 14 Dec 2026, 10:00"` | Immediate proof without opening the file |
| `score` | `0.87` | Retrieval confidence, shown in admin/debug view |

**Granularity:** page-level. Character-precise highlighting inside a PDF is disproportionate effort for this project; page + excerpt is enough for a student to verify in seconds. (ADR-008)

**Rendering contract:** an answer displays a citation chip per distinct source; clicking expands the excerpt. Where a document lacks page structure, `page_number` is null and the section label carries the locating information — the UI must handle this rather than showing "Page null".

---

## 8. Data Model

```
users (Supabase Auth)
  id · email · role(student|admin) · created_at

documents
  id · title · original_filename · storage_path · file_hash
  uploaded_by → users.id
  status          -- uploaded|processing|ready|approved|failed  (SOURCE OF TRUTH, see 6.1)
  approved_by · approved_at   -- audit metadata only; never gates retrieval
  page_count · injection_risk_flag · error_message · created_at

chunks
  id · document_id → documents.id
  content · page_number · chunk_index · char_start · char_end
  section_label · token_count · created_at

chunk_embeddings
  chunk_id → chunks.id · embedding vector(1536) · model_version

conversations
  id · user_id → users.id · title · created_at

messages
  id · conversation_id → conversations.id
  role(user|assistant) · content
  response_type(grounded|not_found|error)
  latency_ms · prompt_tokens · completion_tokens · created_at

message_citations
  id · message_id → messages.id · chunk_id → chunks.id
  rank · retrieval_score · excerpt

retrieval_logs
  id · message_id → messages.id
  retrieved_chunk_ids[] · scores[] · top_score
  gate_outcome(passed|failed_gate1|failed_gate2|failed_gate3)

eval_questions
  id · question · category · expected_behavior
  expected_answer_contains[] · expected_source · active

eval_runs
  id · commit_sha · started_at · config_snapshot
  accuracy · not_found_correctness · citation_validity · injection_resistance

audit_log
  id · actor_id · action · entity_type · entity_id · metadata · created_at
```

`chunk_embeddings` is split from `chunks` so that re-embedding with a different model does not rewrite content rows, and so that a plain `SELECT` on chunks does not drag 1,536 floats per row.

`retrieval_logs.gate_outcome` is what makes the presentation demo possible — it records *which* gate stopped an answer.

---

## 9. API Boundaries

All endpoints require a valid Supabase JWT unless noted. Responses are JSON. Admin endpoints additionally require `role = admin`.

### Student

```
POST   /api/chat/query
       → { question, conversation_id? }
       ← { type: "grounded",   answer, citations[], conversation_id, message_id }
       ← { type: "not_found",  message, documents_searched, conversation_id }
       ← { type: "error",      message }

GET    /api/conversations                 list own conversations
GET    /api/conversations/:id/messages    own messages + citations
GET    /api/chunks/:id                    passage text behind a citation
GET    /api/documents                     approved documents (title/page count only)
```

### Admin

```
POST   /api/admin/documents               upload (multipart)
GET    /api/admin/documents               all documents + ingestion status
GET    /api/admin/documents/:id           detail + chunk count + risk flag
POST   /api/admin/documents/:id/approve
POST   /api/admin/documents/:id/revoke
DELETE /api/admin/documents/:id
POST   /api/admin/documents/:id/reindex
GET    /api/admin/metrics                 query volume, not-found rate, cost
POST   /api/admin/eval/run                trigger evaluation
```

### System

```
GET    /api/health                        no auth
```

**Contract rules the frontend depends on:**

- The `type` discriminator is always present — the UI branches on it and has no other way to distinguish a grounded answer from a refusal.
- A `grounded` response always has ≥ 1 citation. If the backend cannot guarantee that, it must return `not_found` instead.
- The backend never returns raw model output. Everything has passed validation.
- Errors never carry provider details or stack traces to the client.

---

## 10. Technology Stack

| Layer | Choice | Status |
|---|---|---|
| Frontend | React + TypeScript + Vite | Recommended |
| Styling | Tailwind CSS, implementing the Stitch design | Recommended |
| Backend | Python + FastAPI | Decided (ADR-007) |
| Database | Supabase Postgres | Decided |
| Vector store | Supabase pgvector | Decided (ADR-004) |
| Auth | Supabase Auth | Decided |
| File storage | Supabase Storage | Decided |
| Chat model | Foundry — small/efficient chat model (e.g. GPT-4o-mini class) | Decided (ADR-003) |
| Embeddings | Foundry — `text-embedding-3-small` class, 1536 dims | Decided |
| PDF extraction | `pypdf` / `pdfplumber` | Decided |
| Validation | Pydantic — enforces the API and model-response schemas | Decided |
| Testing | `pytest` (backend), `vitest` (frontend) | Decided |
| CI | GitHub Actions | Decided |

All stack decisions are now settled; implementation is unblocked.

---

## 11. Deployment

Target: a single small container for the backend, static hosting for the frontend, everything else managed.

- Backend: Azure Container Apps (scale-to-zero) or Azure App Service free tier
- Frontend: static build on Azure Static Web Apps free tier or Vercel free tier
- Supabase: free tier
- Foundry: pay-per-token, no provisioned capacity

No GPUs, no always-on VMs, no fine-tuning, no dedicated vector-database service. Rationale and numbers in `cost-strategy.md`.

---

## 12. Security Posture

Summarised here, detailed in `security.md`:

- Document text is untrusted data and never occupies the system role
- Foundry credentials exist only in the backend
- Supabase RLS enforces data isolation at the database layer
- Structured JSON output constrains what the model can influence
- Citation verification means a compromised prompt still cannot produce a fake source
- No tool/function calling is exposed at generation time, so injected text has nothing to call

---

## 13. What This Architecture Deliberately Does Not Do

| Not doing | Why |
|---|---|
| Multi-agent orchestration | One retrieval + one model call is sufficient and deterministic. Agents add nondeterminism, latency, and cost for no gain here. Explicitly out of scope. |
| Fine-tuning | Cannot produce citations, expensive to update, worse for this goal than RAG (ADR-002). |
| Answering from model world-knowledge as fallback | Would destroy the core guarantee. Refusal is the correct behaviour. |
| Streaming in MVP | Validation (Gate 3) requires the complete response before display. Streaming needs a buffered design; deferred to V2. |
| Caching answers | Correctness first; caching adds an invalidation problem when documents change. |
