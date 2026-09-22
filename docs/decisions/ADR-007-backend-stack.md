# ADR-007: Backend Language and Framework

**Status:** Accepted
**Date:** 2026-09-23
**Confirmed:** 2026-09-23
**Partially supersedes:** ADR-001, which recorded npm as the package manager on the assumption of a Node backend

## Context

The initial repository scaffolding assumed a Node.js/Express backend, but that scaffolding was created before the product was understood as a retrieval-grounded assistant. The backend's real work is: PDF text extraction, chunking, embedding calls, vector search, prompt construction, response validation, and an evaluation harness.

The frontend will be React + TypeScript regardless of this decision.

## Decision

**Python with FastAPI for the backend.** The frontend remains React + TypeScript.

This diverges from the existing scaffolding and from ADR-001, which assumed Node.

## Rationale

**Document processing.** PDF extraction with reliable page attribution is the first real engineering task (M1), and Python's libraries for it (`pypdf`, `pdfplumber`) are more mature and better documented than the JavaScript equivalents. Page-preserving extraction is a hard requirement for citations (FR-1.4), so this is load-bearing rather than a matter of taste.

**Evaluation tooling.** Evaluation is a first-class component here, not an afterthought. Python's ecosystem for scoring, statistics, and the threshold-calibration plot (`evaluation.md` §8) is substantially stronger, and Azure's AI evaluation tooling is Python-first.

**Alignment with the domain.** RAG examples, Azure AI Foundry samples, and retrieval reference implementations are predominantly Python. For a student project on a deadline, following the well-trodden path reduces the time spent translating examples.

**FastAPI specifically.** Async support for concurrent embedding calls, Pydantic models that enforce the strict request/response contracts in `architecture.md` §9 at the type level, and automatic OpenAPI documentation — useful for the presentation and for the frontend contract.

**Pydantic and the grounding schema.** The model's JSON response (Gate 2) must be parsed and validated strictly. Pydantic makes a schema violation a typed parse failure rather than a defensive `if` chain, which suits Gate 3's requirements well.

## Consequences

**Positive:** stronger libraries for the project's actual hard problems; better evaluation tooling; abundant reference material; type-enforced API contracts.

**Negative:** two languages in the repository (Python backend, TypeScript frontend), so no shared types between them — the API contract must be kept in sync manually or via generated clients from the OpenAPI schema. Contributors must be comfortable in both.

**Required follow-up:** `README.md`, `.env.example`, and ADR-001 have been updated to reflect this decision.

## Alternatives Considered

- **Node.js + Express/Fastify with TypeScript** — one language across the stack, shared types, and consistent with the existing scaffolding. Rejected on PDF tooling maturity and evaluation ecosystem. It would have been a defensible choice if the team's TypeScript experience substantially exceeded its Python experience.
- **Python + Django** — rejected: heavier than needed; no use for the ORM-plus-admin bundle given Supabase.
- **Python + Flask** — rejected: FastAPI's async support and Pydantic validation are directly useful here.
