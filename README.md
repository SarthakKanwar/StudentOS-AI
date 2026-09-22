# StudentOS

An AI-powered student assistant that answers questions **only** from approved university documents — with source attribution, and with an explicit "not found" when the answer isn't there.

StudentOS is deliberately **not** a general-purpose chatbot. Its value is a guarantee:

> If the answer is in the approved knowledge base, StudentOS finds it and cites it.
> If it isn't, StudentOS says so — it never invents university-specific facts.

## Example

**Student:** "When is my Computer Networks exam?"

> Your Computer Networks end-term exam is scheduled for 14 December 2026 at 10:00 AM.
>
> 📚 Based on `exam_dates.pdf` · Page 3
>
> ✓ Grounded in university documents

**Student:** "What's the dress code for convocation?"

> I couldn't find information about this in the approved university documents.
>
> I searched 4 documents but found nothing relevant. You may want to check with the administration office directly.

The second response matters as much as the first. A confidently wrong exam date is worse than no answer.

## Project Status

📋 **Planning complete — implementation starts at M1.**

Architecture, requirements, grounding strategy, security model, evaluation strategy, and cost strategy are documented, and all stack decisions are settled. Next up: the ingestion pipeline (M1) — see [project-plan.md](docs/project-plan.md).

## How It Works

```
Question → retrieve relevant passages → [Gate 1: enough found?]
        → Microsoft Foundry model with passages as DATA
        → [Gate 2: model says context suffices?]
        → [Gate 3: do citations actually resolve?]
        → grounded answer + sources   OR   explicit not-found
```

Three independent gates stand between a question and a displayed answer. Gates 1 and 3 are ordinary backend code, not model calls — so the guarantee holds even if the model misbehaves. Any gate can force a not-found response, and there is no code path that produces an answer without a verified citation.

Full detail in [docs/grounding-strategy.md](docs/grounding-strategy.md).

## Tool Boundaries

These are conceptually separate and must not blur:

| Tool | Role | Runs at |
|---|---|---|
| **Microsoft Foundry** | Runtime AI — chat and embedding models | Runtime |
| **Supabase** | Auth, Postgres, pgvector, file storage | Runtime |
| **Claude Code** | Development and orchestration | Development only — never in the runtime path |
| **GitHub** | Source control, issues, CI | Development |
| **Stitch** | UI/UX design | Design |

## Documentation

| Document | Contents |
|---|---|
| [requirements.md](docs/requirements.md) | Functional and non-functional requirements, MVP scope, what's explicitly out of scope |
| [architecture.md](docs/architecture.md) | System design, runtime request flow, document pipeline, data model, API boundaries |
| [grounding-strategy.md](docs/grounding-strategy.md) | The three gates, not-found design, threshold calibration, demo plan |
| [security.md](docs/security.md) | Threat model, prompt-injection defences, auth, secrets, fail-closed behaviour |
| [evaluation.md](docs/evaluation.md) | Five test categories, metrics, evaluation set design, CI integration |
| [cost-strategy.md](docs/cost-strategy.md) | Budget, per-query cost, free-tier limits, cost controls |
| [project-plan.md](docs/project-plan.md) | Milestones M0–M7, GitHub issues, risks, open decisions |
| [decisions/](docs/decisions/) | Architecture decision records |

### Key Decisions

- [ADR-002](docs/decisions/ADR-002-rag-over-finetuning.md) — RAG, not fine-tuning
- [ADR-003](docs/decisions/ADR-003-foundry-runtime-boundary.md) — Foundry is the runtime; Claude Code is development-only
- [ADR-004](docs/decisions/ADR-004-vector-store.md) — Supabase pgvector
- [ADR-005](docs/decisions/ADR-005-document-content-is-untrusted.md) — Document content is untrusted data
- [ADR-006](docs/decisions/ADR-006-three-gate-grounding.md) — Three-gate grounding
- [ADR-007](docs/decisions/ADR-007-backend-stack.md) — Python + FastAPI backend
- [ADR-008](docs/decisions/ADR-008-citation-granularity.md) — Page-level citations
- [ADR-009](docs/decisions/ADR-009-single-pass-no-agents.md) — Single-pass, no agent loop
- [ADR-010](docs/decisions/ADR-010-synthetic-first-sample-data.md) — Synthetic sample data first
- [ADR-011](docs/decisions/ADR-011-single-status-approval-model.md) — Single-status document approval
- [ADR-012](docs/decisions/ADR-012-version-controlled-retrieval-config.md) — Version-controlled retrieval config

## Repository Structure

```
StudentOS/
├── frontend/            React + TypeScript chat and admin UI
├── backend/
│   ├── routes/          API endpoints and auth
│   ├── services/        Ingestion pipeline, grounding validator
│   ├── retrieval/       Embedding, vector + keyword search, fusion
│   └── foundry/         Microsoft Foundry client (sole holder of model credentials)
├── tests/
│   ├── grounding/       Gate logic and not-found behaviour
│   ├── retrieval/       Recall and ranking
│   └── regression/      Baseline comparisons
├── config/
│   └── retrieval.yaml   Thresholds and chunking params (version-controlled)
├── scripts/             Ingestion and evaluation scripts
├── sample-data/         Synthetic university documents (clearly labelled)
└── docs/                Documentation and ADRs
```

## Stack

| Layer | Technology |
|---|---|
| Frontend | React + TypeScript + Vite |
| Backend | Python + FastAPI |
| Database & vectors | Supabase Postgres + pgvector |
| Auth & storage | Supabase |
| Models | Microsoft Foundry (chat + embeddings) |

## Setup

⚠️ Implementation has not started. Setup instructions will be filled in during M1.

The shape will be:

1. Clone the repository
2. Create a virtual environment and install backend dependencies
3. Install frontend dependencies
4. Copy `.env.example` to `.env` and fill in your own values
5. Run database migrations against your Supabase project
6. Start the backend and frontend

**Never commit `.env`.** It is gitignored. `.env.example` contains variable names and placeholders only.

## Security Note

All sample documents in `sample-data/` are synthetic and clearly labelled. No real student records or university documents are included in this repository.
