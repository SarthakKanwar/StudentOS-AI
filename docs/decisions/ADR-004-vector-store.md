# ADR-004: Use Supabase Postgres with pgvector as the Vector Store

**Status:** Accepted
**Date:** 2026-09-23
**Confirmed:** 2026-09-23

## Context

Retrieval needs a store for ~2,000 chunk embeddings (1,536 dimensions each) supporting similarity search, and ideally hybrid (vector + keyword) search. Supabase is already in the stack for authentication, relational data, and file storage.

The realistic options are Supabase `pgvector`, Azure AI Search, or a managed vector database such as Pinecone.

## Decision

**Use Supabase Postgres with the `pgvector` extension.** Azure AI Search is recorded as the documented upgrade path if retrieval quality proves insufficient.

## Rationale

**One datastore.** Chunks, their metadata, their embeddings, and the documents' approval status all live in the same database. Retrieval filtering on `approved = true` is a plain SQL `JOIN` rather than an index-synchronisation problem. With a separate vector service, approval state must be mirrored into the index and kept consistent — a real source of bugs, and directly safety-relevant here, since a stale index could serve a revoked document.

**Cost.** Free tier, $0. Azure AI Search Basic is ~$75/month, which would consume most of the project budget (`cost-strategy.md` §5).

**Sufficient at this scale.** 2,000 chunks is small. An HNSW index in pgvector returns results in single-digit milliseconds at this size; the scale where a dedicated vector service earns its cost is orders of magnitude larger.

**Hybrid search is achievable.** Postgres provides full-text search via `tsvector`. Combining it with vector results through Reciprocal Rank Fusion is a modest amount of SQL — and implementing it explicitly is *pedagogically useful* for an academic project, since the mechanism is visible and explainable rather than hidden behind a managed service.

**Transactional consistency.** Ingesting a document and indexing its chunks happen in one transaction. A failure cannot leave chunks indexed but unrecorded.

## Consequences

**Positive:** zero marginal cost; no index/database synchronisation; simpler local development; approval filtering is trivially correct.

**Negative:** no built-in semantic reranker (Azure AI Search offers one), so hybrid fusion must be implemented and tuned by us. Free-tier storage (500 MB) bounds corpus growth — ample at ~12 MB of vectors, but it would need revisiting past ~50,000 chunks. Free-tier projects also pause when idle, which is a demo-day hazard already noted in `cost-strategy.md` §7.

**Upgrade path:** retrieval lives behind an interface in `backend/retrieval/`. If measured recall@5 at M2 falls short and tuning does not fix it, swapping the backing store to Azure AI Search is a contained change. The decision to do so should be driven by a measurement, not a preference.

## Alternatives Considered

- **Azure AI Search** — better hybrid search and a semantic reranker out of the box, and it keeps more of the stack on Azure. Rejected on cost and on the index-synchronisation concern. This is the closest alternative and remains the documented upgrade path if measured recall@5 at M2 falls short.
- **Pinecone / Weaviate managed** — rejected: added cost and a second datastore for no benefit at this scale.
- **In-memory / FAISS on disk** — rejected: no persistence story, and it would not survive a scale-to-zero backend restart.
