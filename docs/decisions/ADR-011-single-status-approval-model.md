# ADR-011: Single-Status Document Approval Model

**Status:** Accepted
**Date:** 2026-09-23

## Context

The Phase 0 readiness review found the same fact represented two ways in the documentation. `architecture.md` §8 declared a `documents` table carrying both a `status` field **and** a separate `approved` boolean alongside `approved_by` / `approved_at`. Meanwhile `requirements.md` FR-2.8 defined a status enum that already *included* `approved` as a value, and ADR-004 described retrieval as filtering on `approved = true`.

So the single most safety-critical flag in the system — whether a document may be used to answer a student's question — had two possible sources of truth, and the relationship between them was undefined. Nothing specified whether `status = 'approved', approved = false` was a legal state, which field retrieval actually reads, or what `status` becomes after a revocation.

This had to be settled before the M1 schema migration, because Gate 3 check 4 re-reads approval state at validation time specifically to make revocation take effect immediately (`grounding-strategy.md` §5).

## Decision

**`documents.status` is the single source of truth for retrievability.** There is no `approved` boolean.

- `status` is an enum: `uploaded` · `processing` · `ready` · `approved` · `failed`
- `approved` is one **value** of `status`, not a separate column
- `approved_by` and `approved_at` are **audit metadata only** — they record who approved the document and when, and never determine whether it is retrievable
- **Retrieval requires `status = 'approved'`**, enforced both in the retrieval query and again at Gate 3
- **Approval:** `ready → approved`, also setting `approved_by` and `approved_at`
- **Revocation:** `approved → ready`. The document stays fully indexed; only its retrievability changes

The full status table and transition diagram live in `architecture.md` §6.1.

## Rationale

**One fact, one field.** Two representations of the same state must be kept in sync, and the cost of them drifting apart is not a cosmetic bug — it is a revoked document being served to a student as an approved source. Removing the second representation removes that failure mode entirely rather than mitigating it.

**Revocation semantics become obvious.** `approved → ready` reads naturally: the document is still fully processed and indexed, it simply no longer carries approval. Re-approval is a single field update with no re-indexing, which is what makes the revoke-and-re-ask demo (`grounding-strategy.md` §10 step 3) instant.

**A single filter condition.** Every retrieval query and Gate 3 check tests the same predicate, `status = 'approved'`. A reviewer auditing the approval gate has one condition to look for, not a conjunction whose two halves might disagree.

**It matches ADR-004's justification.** Choosing pgvector was partly justified by approval filtering being a plain SQL `JOIN` rather than an index-synchronisation problem. That argument only holds if there is one unambiguous column to join on.

## Consequences

**Positive:** no synchronisation bug is possible between two approval fields; revocation and re-approval are single-field updates requiring no re-indexing; the retrieval filter and Gate 3 share one predicate; the RLS policy restricting unapproved documents to admins has one condition to express.

**Negative:** the enum conflates *pipeline progress* with *authorization state*. A document sitting at `ready` is either awaiting its first approval or has been revoked, and the two are indistinguishable from `status` alone. `approved_by` / `approved_at` being non-null distinguishes them — a revoked document retains its prior approval metadata — and `audit_log` carries the full history. This is acceptable because nothing in the system needs to branch on that distinction; only the admin console displays it, and it can read the audit trail.

**Follow-up applied:** `architecture.md` (§6.1 added, §4.3, §5 diagram, §8 schema), `requirements.md` (FR-2.7, FR-2.8, FR-2.9), `grounding-strategy.md` (Gate 3 check 4, §5 race discussion), and ADR-004 have all been updated to the single-status model. No reference to an `approved` boolean remains.

## Alternatives Considered

- **Keep both `status` and an `approved` boolean** — rejected: this is the contradiction that prompted the ADR. Two sources of truth for a safety-critical flag, with no mechanism keeping them consistent.
- **Boolean only, no status enum** — rejected: loses the ingestion lifecycle (`processing`, `failed`) that FR-2.8 and FR-2.10 require for admins to see progress and read failure reasons.
- **A separate `document_approvals` table recording each approval/revocation event, with current state derived** — a cleaner audit model, and the right choice for a system with formal compliance requirements. Rejected for this project: it turns every retrieval query into an extra join against a derived state, for an auditability benefit that `audit_log` already provides at sufficient fidelity.
