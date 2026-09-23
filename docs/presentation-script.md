# StudentOS — Presentation Script

**AI-Powered University Student Assistant**
Presenter: Sarthak Kanwar · Repository: `SarthakKanwar/StudentOS-AI`

---

## How to use this script

- **Bold lines** are what you say. Keep them conversational — don't read robotically.
- `[Bracketed lines]` are stage directions: what to click, what to point at.
- **Q&A** is at the end — rehearse that section, it's where marks are won or lost.
- Target: **9–11 minutes** presenting, then questions.
- **Every number in this script is verified against the codebase.** If you're unsure of a figure, say "approximately" rather than inventing precision.

**The one idea to land:** *StudentOS is judged on when it refuses, not just on what it answers.*

---

## Slide 1 — Title (30 seconds)

> **StudentOS — an AI-powered university student assistant.**
>
> **It answers student questions using only university documents that an administrator has approved. Every answer carries the page it came from. And when the answer isn't in those documents, it says so instead of guessing.**
>
> **That last part is the actual engineering problem, and it's what most of this presentation is about.**

`[Move on quickly. Don't linger on the title slide.]`

---

## Slide 2 — Problem Statement (1 minute)

> **Students already have the information they need. It's written down — in handbooks, circulars, datesheets, regulation documents. The problem is finding it. It's scattered across dozens of PDFs, and nobody reads a 40-page handbook to find one exam date.**
>
> **So the obvious idea is: put a chatbot on it.**
>
> **But a general-purpose chatbot fails here in a specific and dangerous way. Ask it when your exam is, and it will produce a confident, plausible, well-formatted answer — that it made up. It has no way to tell you it doesn't know.**

**Pause here. This is the line that frames the whole project:**

> **A confidently wrong exam date is worse than no answer at all — because a student will act on it. They'll show up on the wrong day.**
>
> **So the goal was never just to answer questions. It was to build a system that knows the boundary of what it knows.**

---

## Slide 3 — Objectives (45 seconds)

`[Read these briskly — don't dwell, the detail comes later.]`

> **Five objectives:**
>
> **One — answer only from an approved institutional document set.**
>
> **Two — attach a verifiable citation to every answer: document, page, and the actual supporting text.**
>
> **Three — return an explicit "not found" rather than an unsupported answer.**
>
> **Four — give administrators control over what is retrievable, through an approval step that's separate from upload.**
>
> **Five — and this is the important one — enforce all of that in deterministic code, not by trusting the language model to behave.**

---

## Slide 4 — Proposed Solution & Architecture (2 minutes)

`[Show the architecture diagram.]`

> **The approach is Retrieval-Augmented Generation — RAG. Instead of training a model on university data, we retrieve the relevant passages at question time and give them to the model as source material.**
>
> **We chose RAG over fine-tuning for three reasons: university data changes every semester, it's private, and — most importantly — fine-tuning cannot cite a page. RAG can.**

`[Trace the flow with your finger or cursor.]`

> **The flow: a student asks a question in the React frontend. It goes to the FastAPI backend. The question is embedded into a vector using Azure AI Foundry's text-embedding-3-small model — that's 1536 dimensions.**
>
> **We search the knowledge base using cosine similarity — but only across documents an administrator has approved. Unapproved documents are invisible to this search.**
>
> **Then the question hits three gates.**

**Slow down here. This is the core contribution.**

> **Gate 1 asks: did retrieval find anything similar enough to be worth answering? If not, we stop — and critically, we stop *before* calling the model. An unanswerable question costs nothing, and it's impossible to hallucinate an answer you never asked for.**
>
> **If Gate 1 passes, gpt-5-mini generates an answer from those passages, and returns structured JSON containing three things: the answer, a boolean saying whether it's grounded, and the IDs of the passages it used.**
>
> **Gate 2 reads that boolean. If the model itself says the evidence was insufficient, we refuse.**
>
> **Gate 3 then independently verifies every citation. A citation survives only if it names a passage that was actually retrieved for this specific query, from a document that is still approved right now, with valid page information.**

> **Here's the design principle: Gates 1 and 3 are ordinary Python code. They are not model calls. So even if the model completely misbehaves — invents a citation, ignores its instructions — the guarantee still holds. We don't ask the model to be trustworthy. We verify it.**

---

## Slide 5 — Workflow: Ingestion and Answering (1.5 minutes)

`[Show the workflow diagram.]`

**Admin side:**

> **An administrator uploads a PDF. We validate it — and we check the actual file contents for the PDF signature, not the file extension, because an extension is trivially faked. We reject encrypted files. If a PDF has no text layer at all — a scan — it falls back to OCR rather than being rejected.**
>
> **We extract text page by page, so page numbers survive. That's what makes page-level citations possible later.**
>
> **We split the text into chunks of 800 tokens with 150 tokens of overlap. The overlap matters: without it, a sentence that straddles a chunk boundary becomes unfindable.**
>
> **Each chunk is embedded and stored. Then — and this is a deliberate design choice — the document sits in "ready" status. It is not searchable. A human has to approve it.**

**Student side:**

> **A student asks a question. It's embedded with the same model, searched against approved chunks, and passed through the three gates I described.**
>
> **One detail worth mentioning: the pipeline is transactional. A document only reaches "ready" after *all* its chunks and embeddings are stored. If anything fails partway through, we delete the partial chunks and mark the document failed with a readable reason — so a half-ingested document can never appear complete.**

---

## Slide 6 — Technology Stack (1 minute)

`[Show the stack table. Go quickly — this slide is reference material.]`

> **Frontend is React 18 with TypeScript and Vite.**
>
> **Backend is Python 3.13 with FastAPI.**
>
> **AI runtime is Azure AI Foundry — gpt-5-mini for answers, text-embedding-3-small for embeddings.**
>
> **Storage is SQLite for this prototype, sitting behind a storage interface so it can be swapped.**
>
> **Supporting libraries: pypdf for extraction, tiktoken for tokenization, pytest for tests.**

**One point worth making explicitly — examiners tend to ask about this:**

> **Authentication to Azure uses Microsoft Entra ID, not an API key. There is no API key anywhere in this codebase. Access comes from the signed-in identity. That means there is no secret to accidentally commit.**
>
> **And to be clear about tooling: I used Claude Code as a coding assistant during development. It is not part of the runtime. It is never called when a student asks a question. All runtime AI is Azure AI Foundry. That boundary is documented as a formal architecture decision in the repository.**

---

## Slide 7 — Live Demo / Screenshots (2 minutes)

`[If demoing live: have the backend and frontend already running. Have a document already approved. Do NOT upload a document live — ingestion takes time and a failure on stage is unrecoverable.]`

`[If using screenshots: walk through the four in the README.]`

**Demo 1 — the grounded answer:**

> **I'll ask: "When is the CS-402 Computer Networks examination, and where is it held?"**

`[Ask it. While it thinks — and it takes 15 to 25 seconds — narrate:]`

> **While that runs: it's embedding the question, searching approved passages, and running the gates. The delay is the model reasoning before it answers. I'll come back to that as a known limitation.**

`[When the answer appears, point at the citation card.]`

> **There's the answer — 14 December 2026, Examination Hall 1. And there's the evidence: the document name, the page range, the actual supporting text, and the similarity score. A student can verify this in seconds. That's the point.**

**Demo 2 — the refusal:**

> **Now something the documents don't cover: "What is the campus parking fee for electric motorcycles?"**

`[It returns almost instantly.]`

> **Notice how fast that was. The model was never called — Gate 1 stopped it. The top similarity was about 0.22, below our 0.35 threshold.**
>
> **And look at how it's presented. This isn't an error box. It shows which gate stopped the query and which gates were never reached. The refusal is a designed feature, not a failure state.**

**Demo 3 — a scanned document (if time allows):**

> **This is an exam datesheet — a scan, no text layer at all. Ordinary PDF extraction gets nothing from it. StudentOS falls back to OCR, page by page, and the result enters the exact same pipeline — so it's still citable to a page.**

> **And one thing worth showing: retrieval here is hybrid. Dense embeddings are good at meaning but weak at exact identifiers like a subject code. So a keyword search runs alongside and the two rankings are fused. Without that, a question about one subject's exam duration got buried under a syllabus document for the same subject.**

**Demo 4 — the approval gate (if time allows):**

> **One more. I'll revoke approval on this document in the admin console — and now ask the exact same question that just worked.**

`[Revoke, re-ask.]`

> **Not found. No re-indexing, no rebuild — approval is checked at query time, so revocation is instant.**

---

## Slide 8 — Security & Reliability (1 minute)

> **Four protections worth highlighting.**
>
> **First — prompt injection. Document content is treated as untrusted data. The system prompt contains only StudentOS's rules. Retrieved passages appear only in the user message, inside explicit delimiters, and the model is instructed that if a passage contains instructions, it's quoted content to ignore. A malicious PDF saying "ignore your rules" is data, not a command.**
>
> **Second — fail-closed. If the embedding service or the model fails, the system returns a refusal. It never degrades into an unsupported answer.**
>
> **Third — citation verification. A fabricated citation cannot reach a student, because an invented ID simply won't be in the set of passages we retrieved. This is tested.**
>
> **Fourth — secrets. No API key exists. `.env` is gitignored. The committed `.env.example` contains only placeholders.**

---

## Slide 9 — Testing & Results (1.5 minutes)

`[This slide is your evidence. Deliver it with confidence — these are real numbers.]`

> **209 backend tests, all passing. TypeScript compiles clean. The production build succeeds.**
>
> **External services are mocked in the tests, so the suite runs in about two seconds and costs nothing.**

**Then the part that actually matters:**

> **Beyond unit tests, I verified the whole system end-to-end against the live Azure deployment. Six checks, all passing:**
>
> **An answerable question returned a grounded, correct answer, cited to the right page, at similarity 0.697.**
>
> **An unanswerable question was refused at Gate 1, at similarity 0.223 — the model was never called.**
>
> **And I fed the system a deliberately fabricated citation. Gate 3 rejected it, and the fabricated answer text never reached the output.**
>
> **I also tested the approval gate directly: a question that worked returned "not found" after I revoked the document, and worked again after re-approving it.**
>
> **All three gates have now been observed firing on real traffic — including Gate 2, where the model itself declined to answer a live question.**

---

## Slide 10 — Limitations & Future Scope (1 minute)

**Be direct here. Owning limitations reads as competence, not weakness.**

> **Five honest limitations.**
>
> **One — storage is SQLite. A PostgreSQL and pgvector schema is written, including vector indexing and row-level security, but it has not been deployed.**
>
> **Two — OCR accuracy. Scanned PDFs are now read via OCR, but OCR output is inherently less reliable than an embedded text layer, and I haven't measured its accuracy against a labelled set.**
>
> **Three — the retrieval threshold, 0.35, is uncalibrated. It separated my demo questions cleanly, but two data points is an anecdote, not a calibration. The config file itself records it as uncalibrated, and I won't claim otherwise.**
>
> **Four — authentication is a browser-local prototype. The admin API endpoints are not access-controlled server-side. That needs fixing before any real deployment.**
>
> **Five — latency is 15 to 25 seconds on the answerable path.**

> **All five are documented in the README, and all five are tracked as GitHub issues on the repository, with problem statements and acceptance criteria. They're scoped next steps, not unknowns.**

---

## Slide 11 — Conclusion (30 seconds)

> **Three closing points.**
>
> **First — StudentOS demonstrates that a trustworthy assistant has to be judged on when it refuses, not only on what it answers. Three independent gates enforce that, and two of them are deterministic code rather than model trust.**
>
> **Second — the full pipeline is implemented and verified end-to-end: 209 tests passing, a correct cited answer, a correct refusal, and a fabricated citation successfully blocked.**
>
> **Third — the boundaries are documented rather than hidden. SQLite storage, uncalibrated thresholds, prototype auth — known, scoped, and tracked as GitHub issues.**
>
> **Thank you — happy to take questions.**

---

# Q&A Preparation

**Rehearse these. Answer honestly — if you don't know, say so.**

### "How is this different from ChatGPT?"

> **Two differences. ChatGPT answers from its training data; StudentOS answers only from documents this university has approved, and cites the page. And ChatGPT will always produce an answer — StudentOS is built to refuse. That refusal is the feature.**

### "Why not fine-tune a model on the university data?"

> **Three reasons. The data changes every semester and retraining each time is impractical. It's private, and fine-tuning bakes it into model weights. And most importantly, a fine-tuned model can't cite a page or have a document revoked — RAG can do both instantly.**

### "What stops the AI from hallucinating?"

> **Three layers. Gate 1 refuses before the model is ever called, so an unanswerable question can't be hallucinated. Gate 2 uses the model's own groundedness flag. Gate 3 is ordinary code that verifies every citation resolves to a passage we actually retrieved. Gates 1 and 3 don't depend on the model behaving — that's the point.**

### "What if the model invents a citation anyway?"

> **Gate 3 catches it, and I tested exactly this. I fed the system a fabricated chunk ID with a false answer. The citation didn't resolve, so the whole answer was discarded and replaced with "not found". The fabricated text never reached the output.**

### "Why is the threshold 0.35?"

**Do not oversell this one.**

> **It's a starting value, and it's explicitly marked uncalibrated in the config file. It separated my demo questions cleanly — 0.697 versus 0.223 — but that's two data points. Proper calibration needs a labelled evaluation set, and that's tracked as a GitHub issue.**

### "Why SQLite and not a real database?"

> **Scope. It's a prototype and SQLite runs anywhere with no setup. But it sits behind a storage interface, and the PostgreSQL plus pgvector schema is already written — including HNSW vector indexing and row-level security. Swapping it is a store implementation, not a rewrite.**

### "Why does it take 20 seconds?"

> **gpt-5-mini reasons internally before producing its structured output. That's the dominant cost. Worth noting the refusal path is fast — Gate 1 refusals never call the model at all. Mitigations would be streaming or a faster model tier, but I haven't measured those yet, so I won't claim an improvement I don't have.**

### "Is it secure?"

**Answer this honestly — the honesty is the mark.**

> **Parts of it are. Prompt injection is defended by role separation and treating document text as untrusted data. There's no API key in the codebase — Azure auth is identity-based. The system fails closed.**
>
> **But one part is not: the admin API endpoints have no server-side authorization. Role separation is currently frontend-only, which is a UI convenience, not a security boundary. I know about it, it's documented, and it's tracked as an issue. It would need fixing before any real deployment.**

### "What happens if two chunks get the same ID?"

**A good question to get — you have a real answer.**

> **I ran the numbers. Chunk IDs are SHA-256 hashes truncated to hex. At six hex characters, the birthday paradox gives about an 11% collision chance at 2,000 chunks, and 53% at 5,000 — and since chunk ID is a primary key, a collision means ingestion fails partway through. So I widened it to 12 hex characters, which drops the probability below 1 in 100 million. IDs are also scoped per document.**

### "How do you know the page numbers are right?"

> **Extraction is page by page, so each chunk records the page range it came from. I tested attribution explicitly, including on text with non-ASCII characters where offset arithmetic could drift — zero misattributions across the test set. And Gate 3 rejects any citation without valid page information.**

### "Could someone upload a malicious PDF?"

> **Document content is never treated as instructions. The system prompt holds the rules; passages go in the user message inside delimiters, with an explicit instruction to ignore any commands found inside them. Uploads are also validated by file signature rather than extension, and encrypted files are rejected.**

### "How much does it cost to run?"

> **Per question: one embedding call and one chat completion — fractions of a cent with these model tiers. And Gate 1 refusals cost only the embedding, since the answer model is never called. The test suite costs nothing because external services are mocked.**

### "What would you do differently?"

> **Calibrate the threshold before building the UI — it's the value the entire refusal behaviour depends on, and it's still the least evidenced part of the system. I'd also have added server-side auth from the start rather than leaving it as prototype-only.**

### "Is this production ready?"

> **No, and I wouldn't present it as such. The architecture is sound and the grounding works, but it needs server-side authorization, a real database, and threshold calibration before it could handle actual student traffic. All three are documented and tracked.**

---

## Pre-Presentation Checklist

- [ ] `az login` is active — the Foundry calls will fail without it
- [ ] Backend running: `python -m uvicorn backend.main:app --port 8000`
- [ ] Frontend running: `cd frontend && npm run dev`
- [ ] At least one document is **approved** before you start
- [ ] Both demo questions tested in advance — know what the answers look like
- [ ] Screenshots open in a tab as a fallback if the live demo fails
- [ ] Know these five numbers cold: **120** tests · **0.697** grounded · **0.223** refused · **0.35** threshold · **1536** dimensions

---

## Fallback if the live demo fails

Don't troubleshoot on stage. Say:

> **The live system needs an active Azure session and it's not cooperating — let me show you the recorded result instead.**

`[Switch to the screenshots in the README. Walk through the same three demos using them. Nobody will mind.]`

---

## Timing Guide

| Slide | Content | Time |
|---|---|---|
| 1 | Title | 0:30 |
| 2 | Problem | 1:00 |
| 3 | Objectives | 0:45 |
| 4 | Solution & Architecture | 2:00 |
| 5 | Workflow | 1:30 |
| 6 | Technology Stack | 1:00 |
| 7 | Demo | 2:00 |
| 8 | Security | 1:00 |
| 9 | Testing & Results | 1:30 |
| 10 | Limitations | 1:00 |
| 11 | Conclusion | 0:30 |
| | **Total** | **~12:45** |

**If you're running short on time, cut in this order:** Slide 6 (stack — it's on the slide anyway), then Slide 3 (objectives), then Demo 3 (the revoke demo).

**Never cut:** the Gate explanation in Slide 4, the refusal demo in Slide 7, or the limitations in Slide 10.
