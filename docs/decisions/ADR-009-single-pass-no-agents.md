# ADR-009: Single-Pass Retrieval and Generation — No Multi-Agent Runtime

**Status:** Accepted
**Date:** 2026-09-23

## Context

A common pattern for question-answering systems is an agentic loop: a planner model decomposes the question, decides which tools to call, issues searches, evaluates results, and iterates until satisfied. This is flexible and handles complex multi-hop questions well.

The alternative is a fixed pipeline: retrieve once, generate once, validate deterministically.

## Decision

**Use a single-pass pipeline: one retrieval step, one model call, deterministic validation. No agent loop, no tool-calling at generation time, no planner model.**

This constraint is stated as a project requirement and is recorded here with its reasoning.

## Rationale

**Determinism enables the guarantee.** The three-gate design (ADR-006) depends on knowing exactly which chunks were retrieved for a given question, so Gate 3 can test citation membership against that set. An agent that issues several searches across several turns makes "the retrieved set" a moving target and the validation correspondingly harder to reason about.

**Injection risk multiplies with tools.** ADR-005 establishes that document content is untrusted. An agent with tools gives injected text something to *invoke*. The single strongest injection defence available is simply not exposing any tools on the generation call — an injected instruction has nothing to act on.

**Cost and latency.** An agent loop makes several model calls per question. The single-pass design costs ~$0.001 per query with a p95 target of 6 seconds. An agentic version would multiply both, against a $100 ceiling.

**Debuggability.** When an answer is wrong, there are exactly three places to look: retrieval, the prompt, or the gates. `retrieval_logs` captures the whole decision in one row. Diagnosing an agent loop means reconstructing a multi-step trajectory — considerably harder, and harder still to explain in a presentation.

**The complexity is not needed here.** Agent loops earn their cost on multi-hop reasoning over large, heterogeneous tool surfaces. StudentOS answers factual lookups over a few dozen curated PDFs. Cross-document questions (`evaluation.md` §2.2) are handled by retrieving top-K across all documents in one pass — no iteration required.

## Consequences

**Positive:** the retrieved set is well-defined, making Gate 3 sound; no tool surface for injected instructions; predictable cost and latency; a single log row explains any answer; the architecture is explainable in one diagram.

**Negative:** genuinely multi-hop questions ("which of my exams is closest to the assignment deadline in the syllabus?") may fail where an agent could chain lookups. Such failures surface as not-found responses rather than wrong answers, which is the acceptable direction — and they will be visible in the evaluation results rather than hidden.

**If a class of questions genuinely requires iteration**, the correct response is a bounded, explicit second retrieval pass with the same three gates applied — not an open-ended agent loop. Any such change would need a new ADR.

## Alternatives Considered

- **Agentic RAG with a planner and tool-calling** — rejected: nondeterministic retrieval set, larger injection surface, higher cost and latency, harder to debug and to present. Explicitly out of scope for this project.
- **Query decomposition (split the question, retrieve per sub-question, merge)** — a lighter middle ground that keeps determinism. Rejected for MVP as unnecessary complexity, but it is the natural first step if cross-document accuracy proves inadequate at M6.
- **Iterative retrieval with a relevance-check loop** — rejected: adds model calls and complicates Gate 3 for a marginal recall gain at this corpus size.
