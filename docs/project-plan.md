# StudentOS — Project Plan

**Status:** Draft for review
**Last Updated:** 2026-09-23
**Project start:** 2026-09-23
**Replaces:** the initial project plan dated 2026-09-23, which was scoped to a generic course-management platform

---

## 1. Delivery Strategy

The plan is sequenced around one rule: **prove the hard part first.**

The hard part is not the chat interface. It is retrieval quality and the not-found decision. A beautiful UI over unreliable grounding is a failed project; a plain UI over provable grounding is a successful one. So the milestones build backend capability first and reach a *demonstrable vertical slice* — question in, grounded answer with citation out — by Milestone 3, before any polish.

Each milestone ends in something that can be shown, not just code that exists.

> Durations are working-week estimates for a small team. Calendar dates are deliberately omitted until the presentation deadline is confirmed (see §6).

---

## 2. Milestones

### M0 — Planning & Architecture ✅ *complete*

Requirements, architecture, grounding strategy, security model, evaluation strategy, cost strategy, ADRs.

**Exit criteria:** documentation reviewed and the two blocking decisions resolved (backend language, vector store).

---

### M1 — Foundations & Ingestion Pipeline · ~1.5 weeks

The ability to turn a PDF into retrievable, cited chunks. No UI, no model call yet.

> **Azure is already provisioned.** A Foundry resource (`stuos-resource`, `uaenorth`) with a `gpt-5-mini` chat deployment and a `text-embedding-3-small` embedding deployment already exists and has been capability-tested (`architecture.md` §10.1). M1 does **not** need to create Azure resources — the embedding work below connects to what is already there.

- Backend skeleton in the chosen language; config loading; health endpoint
- Supabase project, schema migrations, RLS policies
- PDF upload → Supabase Storage
- Text extraction with page numbers preserved
- Chunking with overlap and metadata
- Embedding generation via Foundry
- `pgvector` storage and index
- Ingestion status tracking and failure reporting
- Unit tests for chunking and metadata integrity

**Demonstrable:** a CLI command ingests a sample PDF; the database shows chunks with correct page numbers and embeddings.

**Risk:** PDF extraction quality varies more than expected. Mitigated by testing against varied sample documents early.

---

### M2 — Retrieval Layer · ~1 week

Finding the right passage, measurably.

- Question embedding
- Vector similarity search over approved chunks
- Keyword search + Reciprocal Rank Fusion
- Approved-only filtering
- Retrieval logging (chunk ids, scores)
- Retrieval-only evaluation harness measuring **recall@5**

**Demonstrable:** `recall@5 ≥ 90%` on the known-answer question set, reported as a number.

**This is the milestone that determines whether the project works.** If retrieval is weak here, everything downstream inherits it — so the gate is a measurement, not a feeling.

---

### M3 — Grounded Answering (Vertical Slice) · ~1.5 weeks

The core guarantee, end to end.

- Foundry client with strict role separation and JSON-constrained output
- Context assembly with delimiters and chunk labelling
- Gate 1 (retrieval sufficiency)
- Gate 2 (model self-report)
- Gate 3 (citation verification)
- Not-found response construction with reason codes
- `POST /api/chat/query` returning the `grounded` / `not_found` discriminated response
- Threshold calibration against the evaluation set

**Demonstrable:** a `curl` request returns a grounded answer with a valid citation; an out-of-KB question returns a not-found response. **The project is proven at this point** — everything after is interface and hardening.

---

### M4 — Student Chat Interface · ~1.5 weeks

- React + TypeScript + Vite scaffold
- Supabase Auth sign-in
- Chat view implementing the Stitch design
- Citation chips; click-to-expand passage viewer
- Distinct, well-designed not-found state
- Conversation history
- Loading, error, and empty states
- Accessibility pass (keyboard navigation, screen-reader labels)

**Demonstrable:** the reference interaction from `requirements.md` §1.2, in a browser.

---

### M5 — Admin Console & Approval Workflow · ~1 week

- Admin-only routes with server-side role checks
- Upload UI with ingestion progress
- Document list with status and `injection_risk_flag`
- Approve / revoke / delete
- Failure reasons surfaced readably

**Demonstrable:** the revoke-and-re-ask demo from `grounding-strategy.md` §10 step 3 — the centrepiece of the presentation.

---

### M6 — Evaluation, Security Hardening & Adversarial Testing · ~1.5 weeks

- Full evaluation set authored across all five categories
- `scripts/run_eval.py` producing JSON + Markdown reports
- Injection fixture documents and the adversarial suite
- Rate limiting, daily token budget guard, input validation
- RLS verification with a second account
- GitHub Actions CI running unit tests and the adversarial suite
- Baseline reports committed

**Demonstrable:** the full metric table, with the adversarial suite passing 100%.

---

### M7 — Deployment, Demo Preparation & Documentation · ~1 week

- Backend deployed (Container Apps / App Service)
- Frontend deployed (Static Web Apps)
- Environment configuration via platform secret stores
- Demo script rehearsed end to end
- Threshold calibration plot generated
- README and setup documentation completed
- Honest failure analysis written up

**Demonstrable:** the full presentation, rehearsed against the deployed system.

---

## 3. Timeline Summary

| Milestone | Estimate | Cumulative |
|---|---|---|
| M0 Planning | complete | — |
| M1 Ingestion | 1.5 wk | 1.5 |
| M2 Retrieval | 1.0 wk | 2.5 |
| M3 Grounded answering | 1.5 wk | 4.0 |
| M4 Chat UI | 1.5 wk | 5.5 |
| M5 Admin console | 1.0 wk | 6.5 |
| M6 Evaluation & hardening | 1.5 wk | 8.0 |
| M7 Deployment & demo | 1.0 wk | 9.0 |

**~9 working weeks.** If the deadline is shorter, §5 gives the cut order.

---

## 4. Initial GitHub Issues

To be created as issues, grouped by milestone, labelled `milestone:M1`…`M7` plus `backend` / `frontend` / `infra` / `docs` / `eval` / `security`.

**M1 — Ingestion**
1. Set up backend project skeleton with config loading and `/api/health`
2. Create Supabase project and author schema migrations
3. Write RLS policies for conversations, messages, and documents
4. Implement PDF upload to Supabase Storage with validation
5. Implement page-preserving PDF text extraction
6. Implement paragraph-aware chunking with overlap and metadata
7. Implement Foundry embedding client with batching
8. Store embeddings in pgvector and create the index
9. Implement ingestion status tracking and failure reporting
10. Unit tests: chunk boundaries, page attribution, metadata integrity

**M2 — Retrieval**
11. Implement question embedding and vector similarity search
12. Implement Postgres full-text keyword search
13. Implement Reciprocal Rank Fusion over both result sets
14. Filter retrieval to approved documents only
15. Implement retrieval logging
16. Build retrieval-only evaluation harness measuring recall@5

**M3 — Grounded answering**
17. Implement Foundry chat client with JSON-constrained output
18. Implement context assembly with delimiters and chunk labelling
19. Implement Gate 1 — retrieval sufficiency
20. Implement Gate 2 — model self-report parsing
21. Implement Gate 3 — citation verification
22. Implement not-found response construction with reason codes
23. Implement `POST /api/chat/query`
24. Calibrate retrieval thresholds and record in `config/retrieval.yaml`
25. Unit tests for all three gates (no model calls)

**M4 — Chat UI**
26. Scaffold React + TypeScript + Vite frontend
27. Integrate Supabase Auth sign-in/sign-out
28. Build chat view per the Stitch design
29. Build citation chips and passage viewer
30. Build the not-found response state
31. Implement conversation history
32. Accessibility pass on the chat view

**M5 — Admin console**
33. Implement admin role checks on all admin routes
34. Build document upload UI with progress
35. Build document list with status and risk flag
36. Implement approve / revoke / delete endpoints and UI

**M6 — Evaluation & security**
37. Author known-answer and cross-document question sets
38. Author out-of-KB and ambiguous question sets
39. Create injection fixture documents and the adversarial suite
40. Implement `scripts/run_eval.py` with JSON + Markdown reports
41. Implement rate limiting and the daily token budget guard
42. Verify RLS isolation with a second student account
43. Set up GitHub Actions CI for unit tests and the adversarial suite
44. Commit baseline evaluation reports

**M7 — Deployment & demo**
45. Deploy backend with platform secret configuration
46. Deploy frontend
47. Generate the threshold calibration plot
48. Write the demo script and rehearse
49. Complete README and setup documentation
50. Write the honest failure analysis

---

## 5. Scope Reduction Order

If time runs short, cut in this order — the guarantee is never the thing that gets cut:

1. Conversation history UI (keep the API)
2. Admin console polish — approve via a script instead
3. Cross-document question support (narrow to single-source)
4. Accessibility pass beyond keyboard navigation
5. Deployment — demo locally

**Never cut:** Gates 1–3, citation display, the not-found path, or the adversarial test suite. Those *are* the project.

---

## 6. Risks

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Retrieval quality insufficient | High | Medium | M2 gates on measured recall@5 before building on top |
| ~~Foundry SDK differs from assumptions~~ | — | **Resolved** | Verified 2026-09-23 by live test: v1 Responses API with strict JSON schema, and v1 Embeddings returning 1536 dims, both working against the existing deployment (`architecture.md` §10.1) |
| Sample documents unrepresentative | High | Medium | Confirm whether real PDFs will be supplied (§7) |
| Scanned PDFs with no extractable text | Medium | Medium | Detect and reject clearly at ingestion; OCR is out of scope |
| Supabase free-tier project pauses before demo | High | Low | Wake and verify the day before; on the demo-day checklist |
| Threshold tuned to the eval set (overfitting) | Medium | Medium | Hold out a portion of questions; report on held-out data |
| Scope creep toward a general chatbot | High | Medium | `requirements.md` §7 is explicit; refusal is a feature |

---

## 7. Decisions

**Resolved 2026-09-23:**

| # | Decision | Outcome | ADR |
|---|---|---|---|
| 1 | Backend language and framework | Python + FastAPI | ADR-007 |
| 2 | Vector store | Supabase pgvector | ADR-004 |
| 3 | Source of sample documents | Synthetic first, real documents validated at M6 | ADR-010 |

**Still outstanding — these affect scheduling, not architecture, so they do not block M1:**

| # | Decision | Why it is needed |
|---|---|---|
| 4 | Presentation deadline | Fixes the timeline and determines whether the §5 scope reductions apply |
| 5 | Team size and roles | Determines whether M4 (frontend) can run in parallel with M2/M3, which would compress the schedule by ~2 weeks |

---

## 8. Success Criteria

- [ ] A student asks a question and receives a grounded answer with a working citation
- [ ] An out-of-KB question produces an explicit not-found response
- [ ] Revoking a document changes the answer to not-found — demonstrated live
- [ ] Adversarial suite passes 100%
- [ ] Hallucination rate 0% on the evaluation set
- [ ] Answer accuracy ≥ 90%, refusal correctness ≥ 95%
- [ ] Total spend ≤ $50
- [ ] Architecture, grounding strategy, and measured results presentable in full
