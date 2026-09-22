# ADR-003: Microsoft Foundry Is the Runtime Model Layer; Claude Code Is Development-Only

**Status:** Accepted
**Date:** 2026-09-23

## Context

Several AI tools are involved in this project, and they are easy to conflate. Claude Code is being used to write the code. Microsoft Foundry is intended to serve the models that answer student questions. Without an explicit boundary, a well-meaning implementation could end up calling whichever model is convenient, producing a system that is hard to describe accurately and that does not meet the project's stated technology requirements.

## Decision

**Microsoft/Azure AI Foundry is the sole runtime AI layer.** It serves both the chat model and the embedding model used to answer student questions.

**Claude Code is a development-time tool only.** It writes code, documentation, and tests. It is never invoked by the running application, holds no runtime role, and is not a dependency of the deployed system.

The same boundary applies to the other tools: GitHub (source control, development time), Stitch (design time), Supabase (runtime data and auth).

## Rationale

**Architectural honesty.** The presentation must describe what the system actually does. "Microsoft Foundry serves the models" has to be true without qualification.

**Testability of the claim.** The boundary is verifiable: the deployed backend's dependency list and environment configuration contain no Anthropic SDK and no Anthropic credentials. A boundary you can test is a real boundary.

**Substitutability.** Confining all model access to a single `backend/foundry/` client module means the provider is one module's concern, not a cross-cutting one.

**Avoiding accidental coupling.** Without the rule, a developer debugging a prompt might reach for a different provider's API and quietly leave it in the request path.

## Consequences

**Positive:** the architecture description is accurate; the model provider is isolated behind one interface; the deployed system has no development-tool dependencies.

**Negative:** we are bound to Foundry's model catalogue and API behaviour for runtime purposes.

**Verification (2026-09-23):** the required capabilities have since been confirmed by live test rather than assumed. The Azure OpenAI **v1 API surface** (`/openai/v1/responses` and `/openai/v1/embeddings`, `api-version=preview`) provides both: strict JSON-schema output on the deployed `gpt-5-mini` (2025-08-07), and 1536-dimension vectors from `text-embedding-3-small` (v1). Full record in `architecture.md` §10.1. Writing §4.4 in terms of required *capabilities* rather than a specific function signature is what kept this a small verification task instead of a redesign.

**Enforcement:** no Anthropic SDK in backend dependencies; no Anthropic credentials in runtime configuration; all model calls routed through `backend/foundry/`; the dependency check belongs in the pre-demo security checklist.

## Alternatives Considered

- **Claude in the runtime** — rejected: contradicts the project's technology requirements and blurs the tool boundary.
- **Multi-provider abstraction with runtime switching** — rejected: speculative generality. One provider, cleanly isolated, is sufficient; a second can be added if a real need appears.
- **Direct model calls from the frontend** — rejected: would expose credentials and bypass the grounding validator entirely.
