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

> **Implementation note — VERIFIED 2026-09-23.** The required capabilities were confirmed by live test against the existing deployment, not assumed from documentation. The **Azure OpenAI v1 API surface** is used: `POST {endpoint}/openai/v1/responses` for chat with strict JSON-schema output, and `POST {endpoint}/openai/v1/embeddings` for embeddings, both with `api-version=preview`. See §10.1 for the full verification record.

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
 VALIDATE        MIME type is PDF (by content) · size ≤ limit · not encrypted
    │            text is extractable (reject scans with a clear reason)
    │            compute SHA-256 file_hash (integrity + dedup)
    │            [V2] scan for injection-like patterns → injection_risk_flag
    ▼
 EXTRACT         per-page text extraction, page numbers preserved
    │            normalize whitespace, de-hyphenate line breaks
    │            drop repeated headers/footers
    ▼
 CHUNK           800 tokens per chunk, 150 token overlap
    │            tokens counted with tiktoken, cl100k_base encoding
    │            respect paragraph boundaries where possible
    │            MAY span a page break — both pages recorded (see 8.1)
    ▼
 METADATA        each chunk carries:
    │              chunk_id · document_id · document_title
    │              page_start · page_end · chunk_index · char offsets
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
| `document_title` | `Autumn 2026 End-Term Exam Schedule` | What to open — `documents.title`, never the raw filename (§8.1) |
| `page_start` · `page_end` | `3` · `3` (or `3` · `4` when the chunk spans a break) | Where to look |
| `section` | `"End-Term Schedule"` | Human-readable anchor; **NULL when not reliably detected** (§8.1) |
| `chunk_id` | `c_7f2a91` | Internal verification key — canonical `c_<short>` format (§8.1) |
| `excerpt` | `"CS-402 Computer Networks … 14 Dec 2026, 10:00"` | Immediate proof without opening the file |
| `score` | `0.87` | Retrieval confidence, shown in admin/debug view |

**Granularity:** page-level. Character-precise highlighting inside a PDF is disproportionate effort for this project; page + excerpt is enough for a student to verify in seconds. (ADR-008)

**Rendering contract:** an answer displays a citation chip per distinct source; clicking expands the excerpt.

- When `page_start == page_end`, render a single page: *"Page 3"*.
- When a chunk spans a break (`page_start != page_end`), render the range: *"Pages 3–4"*. The range is shown rather than one arbitrary page, so a student is never directed to a page that does not contain the quoted text.
- Where a document lacks page structure, both fields are null and the section label carries the locating information — the UI must handle this rather than showing "Page null".
- `section` is frequently NULL by design (§8.1) and must degrade gracefully.

---

## 8. Data Model

```
users (Supabase Auth)
  id · email · role(student|admin) · created_at

documents
  id
  title               -- human-readable document title, shown in citations
  original_filename   -- the uploaded filename, retained for provenance
  storage_path
  file_hash           -- SHA-256 of the uploaded bytes (integrity + dedup, see 8.1)
  uploaded_by → users.id
  status              -- uploaded|processing|ready|approved|failed  (SOURCE OF TRUTH, see 6.1)
  approved_by · approved_at   -- audit metadata only; never gates retrieval
  page_count
  injection_risk_flag -- column exists from M1; the scanner that sets it is V2 (see 8.1)
  error_message · created_at

chunks
  id                      -- `c_<short>` e.g. c_7f2a91 — canonical format, see 8.1
  document_id → documents.id
  content
  page_start · page_end   -- 1-BASED page numbers; a chunk MAY span a page boundary (see 8.1)
  chunk_index · char_start · char_end
  section_label       -- NULLABLE; populated only when reliably detected
  token_count         -- counted with tiktoken/cl100k_base, per config/retrieval.yaml
  created_at

chunk_embeddings
  chunk_id → chunks.id · embedding vector(1536) · model_version
  -- 1536 verified against the live text-embedding-3-small deployment (§10.1)

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

### 8.1 Field semantics

Decisions resolved 2026-09-23, before the M1 schema was written. Each closes an ambiguity that would have been expensive to change after migration.

**`chunks.id` — canonical chunk identifier**

Format: **`c_<short-identifier>`**, for example `c_7f2a91`.

It is **deterministic for a given chunk within a single document ingestion** — the same document ingested with the same configuration produces the same ids in the same run.

Why a short prefixed id rather than a UUID: chunk ids travel into the model prompt as passage labels and come back in the `citations` array, where Gate 3 tests them by set membership (`grounding-strategy.md` §5). A short id costs fewer prompt tokens on every query, and it stays readable when inspecting `retrieval_logs` by eye during the demo — a UUID column is effectively unreadable at a glance. The `c_` prefix makes the id self-describing in logs and in the prompt.

**Stability across re-ingestion is explicitly *not* required in M1.** Re-ingesting a document — after a chunking-parameter change, for instance — may produce entirely new chunk ids, and old `message_citations` rows may therefore stop resolving. This is accepted for the MVP: the knowledge base is admin-curated and small, re-ingestion is rare, and building id stability now would mean version-tracking infrastructure that FR-2.11 has already deferred to V2. Carried forward as an **M6 hardening concern**, not designed around in M1.

**`chunks.page_start` / `chunks.page_end` — page spanning and 1-based numbering**

**Page numbers are stored 1-based.** Page 1 is the first page of the PDF. PDF libraries (`pypdf`, `pdfplumber`) index pages from **0**, so extraction **must add 1 before persisting**. Storing 1-based values means what is in the database is exactly what a student reads in the citation and exactly what they see printed on the page — no off-by-one conversion sits between the database and the UI, and none can be forgotten in one code path while being applied in another.

A chunk **may** span a page boundary, and when it does **both** page numbers are recorded. For a chunk wholly inside one page, `page_start == page_end`.

The alternative — forcing every chunk to stop at a page break — would produce short, semantically truncated chunks whenever a table or paragraph runs across pages, which is exactly where exam schedules tend to live. Splitting on page boundaries would damage retrieval quality to satisfy a storage convenience.

This does **not** relax the page-level citation requirement (ADR-008). A citation still names a page. Where a cited chunk spans pages, the citation renders the range (`pages 3–4`) rather than silently picking one, so a student is never sent to the wrong page.

**`documents.title` vs `documents.original_filename`**

- `title` is the **human-readable document title** — "Autumn 2026 End-Term Exam Schedule". This is what citations display.
- `original_filename` is the file as uploaded — `exam_dates_v2_FINAL.pdf`. Retained for provenance and admin display; **not** shown to students.

Citations therefore read *"Autumn 2026 End-Term Exam Schedule · Page 3"*, not a filename. A filename is an artefact of whoever saved the file and is often meaningless or misleading to a reader.

**`chunks.section_label` — optional**

NULLABLE. Populated **only when a section or heading is reliably detected**; otherwise NULL. Heading extraction is unreliable across PDF layouts, so a guessed label is worse than none — it would appear in a citation as false precision. The UI must handle NULL (`architecture.md` §7 rendering contract).

**`documents.file_hash` — SHA-256**

SHA-256 of the uploaded file's bytes, used for:
- **Integrity** — detecting whether a stored file has changed since ingestion.
- **Deduplication** — identifying a re-upload of a byte-identical document, so an admin can be warned rather than silently creating a duplicate set of chunks.

It is *not* a version identifier. Document versioning is FR-2.11 (V2).

**`documents.injection_risk_flag` — column now, scanner later**

The **column exists from M1** and defaults to false. The **scanner that sets it is deferred to V2** (FR-3.6).

The two are separated deliberately: adding the column now costs nothing and avoids a migration later, while the scanner is pattern-matching that is trivially evaded and therefore never load-bearing (ADR-005). Injection defence in the MVP rests on the architectural layers — role separation, delimiting, constrained output, and Gate 3 citation verification — not on detecting bad documents at upload.

Until the scanner exists, the flag stays false for every document, and the admin approval gate is the human check in the VALIDATE stage.

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
| Chat model | Foundry — `gpt-5-mini` (2025-08-07), GlobalStandard | **Deployed and verified** (ADR-003, §10.1) |
| Embeddings | Foundry — `text-embedding-3-small` (v1), Standard, 1536 dims | **Deployed and verified** (§10.1) |
| PDF extraction | `pypdf` / `pdfplumber` | Decided |
| Tokenizer | `tiktoken`, `cl100k_base` encoding — defines "token" for chunking and `chunks.token_count` | Decided (`config/retrieval.yaml`) |
| Validation | Pydantic — enforces the API and model-response schemas | Decided |
| Testing | `pytest` (backend), `vitest` (frontend) | Decided |
| CI | GitHub Actions | Decided |

All stack decisions are now settled; implementation is unblocked.

### 10.1 Verified runtime environment

**Verified 2026-09-23** during Phase 1 readiness review, by live capability test against the existing Azure deployment. These are measured results, not documentation claims.

**Existing Azure environment** (provisioned before this review; nothing was created or modified to perform these tests):

| | |
|---|---|
| Subscription | Azure for Students (Chitkara University tenant), Enabled |
| Foundry resource | `stuos-resource`, kind `AIServices`, SKU S0 |
| Foundry project | `stuos` (`Microsoft.CognitiveServices/accounts/projects`) |
| Region | `uaenorth` |
| Endpoint | `https://stuos-resource.cognitiveservices.azure.com` |

**Model deployments:**

| Deployment | Model | Version | SKU | State |
|---|---|---|---|---|
| `gpt-5-mini` | gpt-5-mini | 2025-08-07 | GlobalStandard | Succeeded |
| `text-embedding-3-small` | text-embedding-3-small | 1 | Standard | Succeeded |

#### Test 1 — Structured output (Gate 2 prerequisite) ✅ VERIFIED

| | |
|---|---|
| API surface | Azure OpenAI **v1 Responses API** — `POST {endpoint}/openai/v1/responses?api-version=preview` |
| Request | `text.format.type = "json_schema"` with `strict: true` |
| Result | **HTTP 200**, response status `completed` |
| Returned | `{"answer":"hello"}` — valid JSON, exact schema match |
| Conclusion | **Strict JSON-schema enforcement is accepted by the deployed `gpt-5-mini`.** |

This was the load-bearing unknown in the readiness review. Gate 2 (`grounding-strategy.md` §4) requires the model to return a schema-constrained object carrying `sufficient`, `answer` and `citations`. That contract is confirmed implementable as specified — **no change to the three-gate grounding design is required.**

#### Test 2 — Embedding dimensions (pgvector prerequisite) ✅ VERIFIED

| | |
|---|---|
| API surface | Azure OpenAI **v1 Embeddings API** — `POST {endpoint}/openai/v1/embeddings?api-version=preview` |
| Input | one short test string |
| Result | **HTTP 200** |
| Returned vector length | **1536** |
| Conclusion | The `embedding vector(1536)` column in §8 matches the live deployment. **No change to the pgvector design is required.** |

#### Authentication

Both tests authenticated with **Microsoft Entra ID bearer tokens**, acquired from the developer's existing Azure CLI login (`az account get-access-token --resource https://cognitiveservices.azure.com`).

**No API key was created, retrieved, or stored**, and no credential was written to any file. This is also the intended production pattern: it maps directly onto managed identity when the backend is deployed, so no key needs to exist at any point. `FOUNDRY_API_KEY` remains in `.env.example` as an alternative for local development only.

#### Scope of these tests

Both tests were **inference calls only**. No Azure resource was created, modified, or deleted; no model was deployed; no resource provider was registered. The Azure resource list and deployment list were re-checked afterwards and were unchanged.

#### Still unverified

- **Per-query cost.** `gpt-5-mini` is a reasoning model and bills internal reasoning at output-token rates. The estimates in `cost-strategy.md` were derived for a non-reasoning GPT-4o-mini-class model and do not describe this deployment. They must be re-derived from measured usage once M3 runs real grounded-answering prompts — a single trivial probe is not a basis for revising them.
- **Container Apps prerequisites.** `Microsoft.App`, `Microsoft.ContainerRegistry` and `Microsoft.OperationalInsights` are **NotRegistered** on this subscription. Registration is required before M7 deployment and was deliberately not performed.

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
