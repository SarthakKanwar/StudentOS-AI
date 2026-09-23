# ADR-008: Page-Level Citation Granularity

**Status:** Accepted
**Date:** 2026-09-23

## Context

Every grounded answer must show its source (FR-1.4). "Source" can mean several levels of precision:

1. Document only — `exam_dates.pdf`
2. Document + page — `exam_dates.pdf`, page 3
3. Document + page + excerpt — the above, plus the supporting sentence
4. Character-precise highlight inside the rendered PDF

More precision means more implementation effort and more that can break.

## Decision

**Cite at document + page level, and display a text excerpt of the supporting passage.** (Level 3.)

Chunks store character offsets so finer granularity remains possible later, but character-precise PDF highlighting is out of scope.

**Amendment 2026-09-23 — page ranges.** Chunks may span a page boundary, and store `page_start` and `page_end` rather than a single `page_number` (`architecture.md` §8.1). Where the two differ, the citation renders the **range** — *"Pages 3–4"* — rather than picking one. This does not change the granularity decision: citations remain page-level. It prevents a citation from pointing at a page that does not contain the quoted text, which would be worse than either alternative, because a student who checks and finds nothing loses trust in every other citation.

The document name shown is `documents.title` (the human-readable title), never `original_filename`. A filename reflects whoever saved the file and is often meaningless to a reader — "exam_dates_v2_FINAL.pdf" is not a verification aid.

`section_label` is optional and frequently NULL; it supplements the page reference when a heading is reliably detected, and is omitted otherwise rather than guessed.

## Rationale

**The test is verification time.** A citation is useful if a student can confirm it in seconds. `exam_dates.pdf · Page 3` plus the sentence `"CS-402 Computer Networks — 14 Dec 2026, 10:00"` achieves that immediately — often without opening the file at all.

**Document-only is too coarse.** "It's in exam_dates.pdf" leaves a student scanning 40 pages, which is the problem StudentOS exists to solve.

**Character-precise highlighting is disproportionate.** It requires a PDF rendering pipeline with coordinate mapping, degrades on documents whose text layer does not align with the visual layout, and adds meaningful frontend complexity — all to improve on an excerpt that already lets a student verify in seconds. That effort is better spent on retrieval quality, which determines whether the citation is *right*.

**Excerpts double as evidence.** Showing the passage lets a student judge whether the answer actually follows from it — a check on the system that a page number alone does not provide.

## Consequences

**Positive:** verification is fast; implementation is a text panel rather than a PDF viewer; excerpts make grounding visible and support the presentation demo.

**Negative:** on a dense page, a student may still scan to locate the exact line in the original. Documents without page structure (HTML, plain text, if ever supported) have a null page number and must fall back to a section label — the UI must handle this rather than rendering "Page null".

**Retained option:** `char_start` and `char_end` are stored on every chunk, so upgrading to highlighting later needs no re-ingestion.

## Alternatives Considered

- **Document-only** — rejected: too coarse to be useful.
- **Character-precise PDF highlighting** — rejected for scope; the option is preserved via stored offsets.
- **Section/heading-based citation instead of pages** — rejected as the primary anchor: heading extraction is unreliable across PDF layouts. Section labels are captured opportunistically and shown as a supplement when available.
