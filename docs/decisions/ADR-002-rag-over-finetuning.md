# ADR-002: Use Retrieval-Augmented Generation, Not Fine-Tuning

**Status:** Accepted
**Date:** 2026-09-23

## Context

StudentOS must answer questions from university documents. There are two broad ways to give a language model access to that information:

1. **Fine-tuning** — further train a model on the university documents so the knowledge is absorbed into its weights.
2. **RAG (Retrieval-Augmented Generation)** — leave the model unchanged; retrieve relevant passages at question time and supply them as context.

Fine-tuning is often the intuitive choice ("teach the model our data"), so the reasoning for rejecting it should be recorded explicitly.

## Decision

**Use RAG. Do not fine-tune.**

## Rationale

**Attribution.** This is decisive. A fine-tuned model cannot tell you which document a fact came from — the knowledge is diffused across weights. StudentOS's core requirement is citing a document and page (FR-1.4). RAG makes attribution structural: the passage is right there, with its identifier, before the model speaks.

**The not-found guarantee.** A fine-tuned model has no reliable notion of "this was not in my training data." With RAG, absence is directly observable — retrieval returns nothing above threshold, and the system refuses without ever calling the model (`grounding-strategy.md` Gate 1).

**Update cost.** A revised exam schedule means re-ingesting one PDF (seconds, ~$0.0002). With fine-tuning it means a new training run, and the old dates remain latent in the weights.

**Verifiability.** Gate 3 verifies that cited chunks were actually retrieved. There is no equivalent check for a fine-tuned model's output — nothing to compare the claim against.

**Cost.** Fine-tuning would consume most of the $100 budget before answering a single question (`cost-strategy.md` §5).

**Corpus size.** Fine-tuning needs substantial training data. A few dozen university PDFs is far too little to fine-tune usefully, but ideal for retrieval.

## Consequences

**Positive:** citations are native; the KB updates instantly; absence is detectable; costs are per-query and tiny; the model layer is swappable.

**Negative:** answer quality now depends on retrieval quality, making the retrieval layer the critical component (hence M2 gating on measured recall@5). Each query carries context tokens, and context window size bounds how much evidence one answer can use.

**Accepted trade-off:** we take a retrieval-quality problem — which is measurable and fixable — over an attribution problem, which is neither.

## Alternatives Considered

- **Fine-tuning** — rejected above.
- **Hybrid (fine-tune for tone + RAG for facts)** — rejected: added cost and complexity for a stylistic benefit achievable with prompting.
- **Full documents in context, no retrieval** — rejected: does not scale past a few documents, costs far more per query, and degrades accuracy as context grows.
