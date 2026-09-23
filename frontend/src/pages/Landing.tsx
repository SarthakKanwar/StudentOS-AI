import { navigate } from "../lib/router";
import { Wordmark } from "../components/Logo";
import { IconArrowRight, IconShield } from "../components/icons";

const PRINCIPLES = [
  {
    num: "01",
    title: "Approved sources only",
    body: "An administrator reviews and approves each document before it can be retrieved. Revoking approval removes it from answers immediately, with no re-indexing.",
  },
  {
    num: "02",
    title: "Refusal is a feature",
    body: "When the approved corpus does not cover a question, StudentOS says so. A confidently wrong exam date is worse than no answer, because a student acts on it.",
  },
  {
    num: "03",
    title: "Every claim is traceable",
    body: "Answers carry the document and page they came from, with the supporting passage attached. A student can verify a citation in seconds.",
  },
  {
    num: "04",
    title: "Verified in code, not by trust",
    body: "Citations are checked deterministically against the passages actually retrieved. A fabricated reference cannot reach a student, because it will not resolve.",
  },
];

const FLOW = [
  { title: "Approved knowledge base", note: "Handbooks, schedules and regulations an administrator has signed off" },
  { title: "Passage retrieval", note: "Semantic search across approved documents only" },
  { title: "Three grounding gates", note: "Evidence check, model self-report, citation verification" },
  { title: "Grounded answer", note: "With document, page range and supporting excerpt" },
];

export function Landing() {
  return (
    <div className="landing">
      <header className="landing-nav">
        <a href="#/" onClick={(e) => { e.preventDefault(); navigate(""); }}>
          <Wordmark />
        </a>
        <nav className="landing-nav-links">
          <a href="#how">How it works</a>
          <a href="#principles">Principles</a>
        </nav>
        <div className="landing-nav-actions">
          <button type="button" className="btn btn-ghost" onClick={() => navigate("signin")}>
            Sign in
          </button>
          <button type="button" className="btn btn-primary" onClick={() => navigate("signup")}>
            Get started
          </button>
        </div>
      </header>

      <section className="hero">
        <div>
          <span className="hero-eyebrow">
            <IconShield size={13} />
            Retrieval-grounded
          </span>

          <h1>
            Answers a student can <em>verify</em>, from documents a university has
            approved.
          </h1>

          <p className="hero-lede">
            StudentOS answers questions about courses, examinations and regulations
            using only the documents your administrators have approved — and tells
            students plainly when the answer is not there.
          </p>

          <div className="hero-actions">
            <button type="button" className="btn btn-primary btn-lg" onClick={() => navigate("signup")}>
              Get started
              <IconArrowRight size={16} />
            </button>
            <button type="button" className="btn btn-secondary btn-lg" onClick={() => navigate("signin")}>
              Sign in
            </button>
          </div>

          <p className="hero-note">
            Demo accounts are provided on the sign-in page.
          </p>
        </div>

        <div className="preview" aria-hidden="true">
          <div className="preview-bar">
            <span className="preview-dot" />
            <span className="preview-dot" />
            <span className="preview-dot" />
            <span className="preview-label">studentos / ask</span>
          </div>

          <div className="preview-q">When is the CS-402 examination, and where is it held?</div>

          <div className="flow">
            {FLOW.map((step, index) => (
              <div className="flow-step" key={step.title}>
                <span className="flow-marker">
                  <span className="flow-dot" />
                  {index < FLOW.length - 1 && <span className="flow-line" />}
                </span>
                <span className="flow-body">
                  <span className="flow-title">{step.title}</span>
                  <span className="flow-note">{step.note}</span>
                </span>
              </div>
            ))}
          </div>

          <div className="verdict verdict-grounded" style={{ borderTop: "1px solid var(--forest-border)", borderBottom: 0 }}>
            <span className="verdict-mark">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                <path d="m5 12.5 4.5 4.5L19 7.5" />
              </svg>
            </span>
            <span className="verdict-text">Grounded</span>
          </div>

          <div className="citation" style={{ margin: "var(--s4) var(--s5) var(--s5)" }}>
            <div className="citation-summary" style={{ cursor: "default" }}>
              <span className="citation-main">
                <span className="citation-doc">CS Department Student Handbook</span>
                <span className="citation-locator">
                  <span className="page-ref">Pages 1-2</span>
                  <span className="citation-score">similarity 0.697</span>
                </span>
              </span>
            </div>
          </div>
        </div>
      </section>

      <section className="section section-bordered" id="how">
        <div className="section-head">
          <span className="label">How it works</span>
          <h2>Three independent gates stand between a question and an answer.</h2>
          <p>
            The first runs before the model is called, so an unanswerable question
            costs nothing and cannot be hallucinated. The last runs in ordinary code
            after the model replies, so an invented citation is caught even if
            everything before it fails.
          </p>
        </div>

        <div className="principles" id="principles">
          {PRINCIPLES.map((item) => (
            <article className="principle" key={item.num}>
              <span className="principle-num">{item.num}</span>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </article>
          ))}
        </div>
      </section>

      <footer className="landing-foot">
        <div className="landing-foot-inner">
          <Wordmark />
          <small>
            Academic prototype &middot; synthetic demonstration data only &middot; not a
            production system
          </small>
        </div>
      </footer>
    </div>
  );
}
