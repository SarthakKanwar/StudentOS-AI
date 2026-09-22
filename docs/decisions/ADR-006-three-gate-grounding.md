# ADR-006: Three-Gate Grounding with an Explicit Not-Found Contract

**Status:** Accepted
**Date:** 2026-09-23

## Context

The system must never state a university-specific fact that is not supported by the knowledge base (FR-1.6, NFR-1). A language model asked about an exam date will produce a fluent, specific date whether or not it has the information — and the wrong answer is indistinguishable from the right one to a student.

The naive approach is to instruct the model to say "I don't know" when unsure. That is a suggestion, not a control: it fails exactly when the model is most confidently wrong.

## Decision

**Three independent gates sit between a question and a displayed answer. Any one of them can force a not-found response.**

| Gate | Where | Nature | Catches |
|---|---|---|---|
| 1 — Retrieval sufficiency | Before the model call | Deterministic code | Nothing relevant exists in the KB |
| 2 — Model self-report | The model call | Model judgement (`sufficient` boolean in a required JSON schema) | Retrieved content that does not actually answer the question |
| 3 — Citation verification | After the model call | Deterministic code | A model that answered anyway and invented a source |

Additionally, the not-found response is a **designed product surface** with its own copy and internal reason codes — not an error state.

## Rationale

**Gates 1 and 3 are ordinary code, not model calls.** This is the crux. A system whose safety depends entirely on a model choosing to behave is not a safe system. Gate 3 tests set membership: a cited `chunk_id` either was or was not in the retrieved set. No prompt-level attack defeats a set-membership test in backend code.

**The gates fail differently.** Gate 2 cannot catch a model that ignores its instructions, because such a model will also misreport sufficiency. Gate 3 catches exactly that case. Independence is what makes the layering worth the complexity.

**Gate 1 runs first because it is cheapest.** An unanswerable question costs one embedding call (~$0.0000004) and never reaches the chat model. The safest path is also the cheapest — a pleasing alignment rather than a trade-off.

**Every failure path lands on not-found.** There is no code path that emits an ungrounded answer. Failures degrade toward refusal.

**The asymmetry is deliberate.** We accept refusing some answerable questions (false refusal rate ≤ 10%) in exchange for never fabricating (hallucination rate 0%). A student who misses an exam because of an invented date is actively harmed; a student told to check with the office is merely inconvenienced.

## Consequences

**Positive:** the guarantee holds even when the model misbehaves; gate logic is unit-testable without any model call, so safety-critical code is verified on every commit at zero cost; `retrieval_logs.gate_outcome` records which gate decided each outcome, making the system explainable in the presentation rather than magical.

**Negative:** some answerable questions are refused, and that rate must be measured and managed. Thresholds require empirical calibration against our own corpus (`grounding-strategy.md` §7) — a copied threshold is meaningless. The JSON schema requirement rules out naive token streaming in the MVP, since Gate 3 needs the complete response before display.

**Deferred:** a fourth gate performing sentence-level entailment checking against cited chunks, deferred because it roughly doubles per-query cost and the first three should be measured before adding a fourth.

## Alternatives Considered

- **Prompt instruction alone ("say I don't know if unsure")** — rejected: unenforceable, and it fails precisely in the dangerous case.
- **Similarity threshold alone (Gate 1 only)** — rejected: retrieval can surface superficially similar but irrelevant passages; similarity is not sufficiency.
- **Post-hoc fact-checking with a second model** — rejected for MVP: doubles cost and latency, and introduces a second model that can also be wrong. Recorded as the possible Gate 4.
- **Human review of answers** — rejected: incompatible with an interactive assistant.
