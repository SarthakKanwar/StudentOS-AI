# ADR-010: Synthetic Sample Documents First, Real Documents Validated at M6

**Status:** Accepted
**Date:** 2026-09-23

## Context

The knowledge base needs documents. Two sources are available: synthetic PDFs we author ourselves, or real university documents supplied later.

Both matter for different reasons. The evaluation set (`evaluation.md` §4) must be written against documents whose contents we know exactly, or "expected answer" is guesswork. But real PDFs are messier than anything we would author — inconsistent layouts, multi-column tables, scanned pages, headers that confuse extraction — and a system tuned only on clean synthetic documents may fall over on the first real one.

## Decision

**Build against synthetic documents from M1, then validate against real university documents at M6.**

Synthetic documents are authored in `sample-data/`, clearly labelled as synthetic, and committed to the repository. Real documents, when supplied, stay local and gitignored.

## Rationale

**Nothing blocks on document supply.** M1 and M2 can start immediately. Waiting for real documents would idle the critical path.

**Known ground truth makes evaluation possible.** We author `exam_dates.pdf` knowing the Computer Networks exam is on 14 December 2026 at 10:00, so the expected answer is a fact rather than an assumption. Out-of-KB questions can be verified as genuinely absent, which is otherwise tedious and error-prone.

**Committable.** Synthetic documents in the repository make the project reproducible — a reviewer can clone, ingest, and run the evaluation. Real university documents could not be committed.

**Real documents still get tested.** Deferring validation is not skipping it. M6 adds a real-document pass, and extraction failures found there are exactly the kind of finding worth reporting in the presentation.

## Consequences

**Positive:** the critical path is unblocked; evaluation has reliable ground truth; the repository is self-contained and reproducible.

**Negative:** synthetic documents risk being unrealistically clean, which would make M2's recall@5 optimistic. Two mitigations: deliberately introduce realistic messiness when authoring (multi-column tables, headers and footers, inconsistent date formats, a page of dense prose), and treat M2's recall figure as provisional until the M6 real-document pass confirms it.

**Re-calibration cost:** when real documents land, retrieval thresholds must be re-calibrated against them (`grounding-strategy.md` §7), and the evaluation set extended with questions written from the real corpus. This is budgeted work at M6, not a surprise.

**Requirement on authoring:** every synthetic document carries a visible label marking it as sample data, so it can never be mistaken for a real university record. No real student names, staff names, or institutional identifiers.

## Alternatives Considered

- **Synthetic only** — rejected: leaves the "does this work on real PDFs?" question permanently unanswered, which is the first thing an examiner would ask.
- **Wait for real documents** — rejected: blocks M1 and M2 on an external dependency, and real documents cannot be committed, harming reproducibility.
- **Real documents only, gitignored** — rejected: the repository would not be runnable by anyone else, and the evaluation set could not be shared or verified.
