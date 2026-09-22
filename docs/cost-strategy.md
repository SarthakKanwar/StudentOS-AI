# StudentOS — Cost Strategy

**Status:** Draft for review
**Last Updated:** 2026-09-23
**Budget ceiling:** $100 · **Target spend:** ≤ $50

> **Pricing caveat:** the figures below are order-of-magnitude estimates based on published rates for small chat and embedding models. Cloud pricing changes and varies by region. **Every number here must be confirmed against the Azure pricing calculator for the chosen region before provisioning.** The estimates are used to prove the architecture is affordable by a wide margin — they are not quotations.

---

## 1. Cost Principles

1. **Pay per request, never per hour.** No always-on compute, no reserved capacity.
2. **Use free tiers deliberately**, and design within their limits rather than discovering them at demo time.
3. **Spend tokens only when they can change the outcome.** Gate 1 rejects unanswerable questions before any chat model call — a correctness feature that is also the largest cost saving.
4. **No GPUs, no fine-tuning, no dedicated vector service.** None is technically justified at this scale.
5. **Cap spend in code**, not just in intention.

---

## 2. Where the Money Goes

| Component | Choice | Billing | Estimated project cost |
|---|---|---|---|
| Chat model | Foundry small chat model (GPT-4o-mini class) | Per token | **$5 – 15** |
| Embedding model | `text-embedding-3-small` class | Per token | **< $1** |
| Database + vector | Supabase free tier (Postgres + pgvector) | Free | **$0** |
| Auth | Supabase Auth free tier | Free | **$0** |
| File storage | Supabase Storage free tier (1 GB) | Free | **$0** |
| Backend hosting | Azure Container Apps (scale-to-zero) | Per vCPU-second, monthly free grant | **$0 – 5** |
| Frontend hosting | Azure Static Web Apps free tier | Free | **$0** |
| CI | GitHub Actions (public/free minutes) | Free | **$0** |
| Monitoring | Application logs, free tier | Free | **$0** |
| | | **Estimated total** | **$6 – 21** |

Comfortably inside the ceiling, with room for re-indexing and repeated evaluation runs.

---

## 3. Per-Query Cost

The dominant recurring cost. Typical grounded query:

| Item | Tokens | Rate (approx.) | Cost |
|---|---|---|---|
| Question embedding | ~20 | $0.02 / 1M | ~$0.0000004 |
| System prompt | ~300 | $0.15 / 1M input | ~$0.000045 |
| Retrieved context (5 × ~800) | ~4,000 | $0.15 / 1M input | ~$0.0006 |
| Answer output | ~150 | $0.60 / 1M output | ~$0.00009 |
| **Total** | | | **≈ $0.0008** |

**≈ $0.001 per question** — an order of magnitude under the $0.01 NFR target.

A **not-found at Gate 1 costs ~$0.0000004** — the embedding only. Questions outside the knowledge base are effectively free, which is a pleasing alignment: the safest path is also the cheapest.

**Volume projections:**

| Scenario | Queries | Cost |
|---|---|---|
| Development and manual testing | ~2,000 | ~$2 |
| Full evaluation run (~90 questions) | 90 | ~$0.10 |
| 30 evaluation runs over the project | 2,700 | ~$3 |
| Live demo | ~50 | ~$0.05 |
| Contingency ×2 | | ~$10 |

---

## 4. Ingestion Cost

One-off per document, dominated by embeddings:

- 50 documents × ~20 pages × ~500 tokens ≈ 500,000 tokens
- At ~$0.02 / 1M → **~$0.01 total**

Re-indexing the entire corpus after a chunking change costs about a cent. This is worth noting: **it means we can afford to experiment with chunking parameters freely**, which directly benefits retrieval quality. A design where re-indexing was expensive would discourage the tuning the project needs.

---

## 5. Why Not the Expensive Options

| Rejected option | Cost | Why rejected |
|---|---|---|
| **Fine-tuning a model** | $100s + per-token premium | Cannot produce citations, expensive to update, and strictly worse than RAG for this goal (ADR-002). The single most common way a student project burns its budget with nothing to show. |
| **Azure AI Search (Basic)** | ~$75/month | Excellent hybrid search and semantic ranking, but it alone would consume most of the budget. pgvector is sufficient at 2,000 chunks (ADR-004). |
| **Dedicated vector DB (Pinecone/Weaviate managed)** | $70+/month | Same reasoning; we already have Postgres. |
| **GPU compute for local embeddings** | $1+/hour | Hosted embeddings cost under a dollar for the whole project. A GPU VM left running for a weekend would exceed the entire budget. |
| **Always-on App Service (B1)** | ~$13/month | Scale-to-zero costs nothing when idle, and a student demo is idle almost always. |
| **Large frontier chat model** | ~20× per token | Unjustified. The task is extraction and phrasing from supplied context, not reasoning under uncertainty. Model choice should be validated empirically via the evaluation set — and only upgraded if measurements demand it. |

The last row is the honest position: we choose the small model because it is likely sufficient, and we have an evaluation harness to check. If accuracy on known-answer questions falls short, the escalation path is (1) improve chunking and retrieval, (2) then consider a larger model — in that order, because retrieval is usually the real problem and is free to fix.

---

## 6. Cost Controls in Code

Budget discipline is enforced, not hoped for:

| Control | Implementation |
|---|---|
| **Gate 1 pre-filter** | No chat model call when retrieval finds nothing |
| **Context cap** | `MAX_CONTEXT_CHUNKS = 5`; hard token ceiling on assembled context |
| **Output cap** | `max_tokens` set on every completion |
| **Rate limits** | 20 queries/min, 200/day per user |
| **Daily token budget** | Backend tracks cumulative spend; refuses queries and alerts the admin past the ceiling |
| **Per-query accounting** | Token counts stored on every message row, so spend is queryable per user and per day |
| **Evaluation scheduling** | Full runs on relevant PRs and nightly, not on every push |
| **Embedding batching** | Chunks embedded in batches to minimise request overhead |

The daily budget guard is also a security control — it closes the denial-of-wallet vector described in `security.md` §5.

---

## 7. Free-Tier Limits to Design Within

| Service | Free tier limit | Our projected usage | Headroom |
|---|---|---|---|
| Supabase database | 500 MB | ~50 MB (2,000 chunks + embeddings) | Ample |
| Supabase storage | 1 GB | ~200 MB (50 PDFs) | Ample |
| Supabase MAU | 50,000 | < 50 | Ample |
| Azure Static Web Apps | 100 GB bandwidth/month | Negligible | Ample |
| Container Apps | Monthly free vCPU-second grant | Scale-to-zero, low traffic | Likely covered |
| GitHub Actions | Free minutes for the account tier | Modest | Ample |

**The binding constraint is the embedding storage in Postgres**, not compute. 2,000 chunks × 1,536 dimensions × 4 bytes ≈ 12 MB of raw vector data, plus index overhead — comfortable inside 500 MB. If the corpus grew past roughly 50,000 chunks, this assumption would need revisiting.

**Supabase free-tier projects pause after a period of inactivity.** The project must be woken and verified the day before the presentation — a demo failure caused by a paused database would be avoidable and embarrassing. This belongs on the demo-day checklist.

---

## 8. Monitoring

- Token usage per query recorded on `messages`
- A daily rollup query gives spend-to-date
- Azure Cost Management budget alert at 50% and 80% of the ceiling
- `/api/admin/metrics` surfaces query volume, not-found rate, and estimated spend

Cost is reviewed at each milestone, not just at the end.

---

## 9. Contingency

If spend approaches the ceiling:

1. Reduce `MAX_CONTEXT_CHUNKS` from 5 to 3 (≈40% input token reduction)
2. Tighten rate limits
3. Cache embeddings for repeated evaluation questions
4. Reduce evaluation frequency to milestone-only
5. Shorten chunk size

None of these degrade the core guarantee — they trade breadth of context for cost, which affects recall, not grounding. A cheaper system may refuse more often; it will not fabricate more often. That is the right direction to fail.
