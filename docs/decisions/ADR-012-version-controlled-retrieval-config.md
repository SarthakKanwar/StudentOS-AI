# ADR-012: Version-Controlled Retrieval Configuration

**Status:** Accepted
**Date:** 2026-09-23

## Context

The Phase 0 readiness review found a second contradiction. `requirements.md` NFR-13 required that thresholds and chunking parameters live in version-controlled configuration rather than being hardcoded. `grounding-strategy.md` §7 and `project-plan.md` issue 24 both instructed that calibrated values be recorded in `config/retrieval.yaml`. But `.env.example` declared those same six parameters — `TAU_MIN`, `TAU_SUPPORT`, `RETRIEVAL_TOP_K`, `MAX_CONTEXT_CHUNKS`, `CHUNK_SIZE_TOKENS`, `CHUNK_OVERLAP_TOKENS` — as environment variables.

`.env` is gitignored. Configuration placed there is by definition *not* version-controlled, so the `.env` approach directly violated NFR-13 and broke the reproducibility promise in `evaluation.md` §5, which states that every evaluation run records a config snapshot so a score is attributable to a specific system state. A score cannot be attributed to a configuration that exists only in one developer's untracked local file.

## Decision

**Retrieval thresholds and chunking parameters live in committed `config/retrieval.yaml`. Secrets and deployment-specific values remain in `.env`.**

`config/retrieval.yaml` holds:

```yaml
chunking:    chunk_size_tokens · chunk_overlap_tokens
retrieval:   top_k · max_context_chunks
grounding:   tau_min · tau_support
calibration: status · calibrated_on · corpus · embedding_model · notes
```

`.env` holds credentials (Foundry, Supabase), deployment values (`APP_ENV`, `PORT`, `LOG_LEVEL`, `CORS_ALLOWED_ORIGINS`), and operational limits (`DAILY_TOKEN_BUDGET`, `RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_PER_DAY`, `MAX_UPLOAD_SIZE_MB`, `MAX_QUESTION_LENGTH`).

**The dividing line:** if changing the value changes *what answer the system produces*, it belongs in `config/retrieval.yaml` and must be reproducible from a git checkout. If it is a credential, or an operational limit that legitimately differs between a laptop and production, it belongs in `.env`.

## Rationale

**Reproducibility is the whole point.** `evaluation.md` §5 promises that a reviewer can check out a commit and reproduce a reported metric. That only works if the parameters that determine the metric are *in* the commit. This matters more here than in a typical project, because the thresholds are not incidental tuning — `tau_min` is the value that decides whether a student gets an answer or a refusal.

**Threshold changes deserve review.** Lowering `tau_min` makes the system answer more often *and* hallucinate more often. As a tracked file, that change appears in a pull-request diff where someone can question it. As an environment variable it is invisible, and it could differ silently between a developer's machine and the demo.

**Calibration provenance needs somewhere to live.** `grounding-strategy.md` §7 requires recording the date, corpus, and embedding model a calibration was performed against — a threshold is only valid for the corpus and embedding model it was measured on. The `calibration:` block carries that, and currently reads `status: uncalibrated`, which is an honest signal that the numbers are starting points rather than findings. An env var has nowhere to put that context.

**Secrets stay isolated.** Keeping `.env` to credentials and deployment values keeps the security-sensitive file short and easy to audit (`security.md` §4). Mixing tuning knobs into it makes the genuinely dangerous lines harder to spot.

**Operational limits are genuinely deployment-specific.** Rate limits and upload caps reasonably differ between local development and a deployed demo, and changing them does not change which answer a given question receives. They are also a cost and abuse control rather than a retrieval parameter, so they stay in `.env`.

## Consequences

**Positive:** evaluation runs are reproducible from a git checkout; threshold changes are reviewable in diffs; calibration provenance is recorded alongside the values it describes; `.env` stays short and auditable; NFR-13 is satisfied in fact and not only in intent.

**Negative:** the backend must load configuration from two places rather than one, so the settings loader is slightly more complex and needs a clear precedence rule. Changing a threshold now requires a commit and redeploy rather than an environment-variable edit — deliberate friction for values that alter system behaviour, but friction nonetheless. The boundary also requires judgement for any future parameter, which is why the dividing line is stated explicitly above.

**Follow-up applied:** `config/retrieval.yaml` created; the six parameters removed from `.env.example` and replaced with a pointer; `requirements.md` NFR-13, `grounding-strategy.md` §3 and §7, `evaluation.md` §5, and `security.md` §4 updated; `README.md` structure block now shows `config/`.

## Alternatives Considered

- **All configuration in `.env`** — rejected: violates NFR-13, breaks evaluation reproducibility, and hides behaviour-changing values from code review.
- **All configuration in `config/retrieval.yaml`, including secrets** — rejected outright: committing credentials is the failure this project's security posture exists to prevent (`security.md` §4).
- **Configuration in the database, editable from the admin console** — attractive for live tuning during a demo, and worth revisiting later. Rejected now: it makes an evaluation score unreproducible from a git checkout, which is the exact property this ADR is protecting, and it would let a threshold change bypass review entirely.
- **Hardcoded constants in Python** — rejected: violates NFR-13 and makes calibration a code change rather than a config change.
