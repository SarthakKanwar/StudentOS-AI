import { useState } from "react";
import { formatPages, type ChatResponse, type Citation } from "../api";
import { IconAlert, IconCheck, IconChevronRight } from "./icons";

/* The three gates, rendered from the backend's gate_outcome. A refusal is a
   feature here, so the UI shows which gate decided rather than hiding it. */

type GateState = "pass" | "stop" | "skip";

const GATES = [
  { id: "Gate 1", name: "Retrieval evidence found in approved documents" },
  { id: "Gate 2", name: "Model confirmed the evidence supports an answer" },
  { id: "Gate 3", name: "Every citation verified against retrieved passages" },
] as const;

function gateStates(outcome: string): GateState[] {
  switch (outcome) {
    case "passed_all_gates":
      return ["pass", "pass", "pass"];
    case "gate1_insufficient_retrieval":
      return ["stop", "skip", "skip"];
    case "gate2_model_not_grounded":
      return ["pass", "stop", "skip"];
    case "gate3_no_valid_citations":
      return ["pass", "pass", "stop"];
    default:
      return ["skip", "skip", "skip"];
  }
}

const GATE_LABEL: Record<GateState, string> = {
  pass: "Passed",
  stop: "Stopped",
  skip: "Not reached",
};

function CitationCard({ citation, index }: { citation: Citation; index: number }) {
  const [open, setOpen] = useState(index === 0);

  return (
    <article className="citation" data-open={open}>
      <button
        type="button"
        className="citation-summary"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <IconChevronRight size={15} className="citation-chevron" />
        <span className="citation-main">
          <span className="citation-doc">{citation.document_title}</span>
          <span className="citation-locator">
            <span className="page-ref">{formatPages(citation)}</span>
            <span className="citation-score">
              similarity {citation.score.toFixed(3)}
            </span>
          </span>
        </span>
      </button>

      <div className="citation-detail">
        <div>
          <blockquote className="citation-excerpt">{citation.excerpt}</blockquote>
          <div className="citation-id">chunk {citation.chunk_id}</div>
        </div>
      </div>
    </article>
  );
}

export function AnswerPanel({ response }: { response: ChatResponse }) {
  const grounded = response.response_type === "grounded";
  const states = gateStates(response.gate_outcome);

  return (
    <section className="panel enter" aria-live="polite">
      <div className={`verdict ${grounded ? "verdict-grounded" : "verdict-notfound"}`}>
        <span className="verdict-mark">
          {grounded ? <IconCheck size={13} /> : <IconAlert size={13} />}
        </span>
        <span className="verdict-text">
          {grounded ? "Grounded in approved documents" : "No supporting evidence"}
        </span>
        <span className="verdict-meta">
          {response.retrieved} retrieved &middot; top {response.top_score.toFixed(3)}
        </span>
      </div>

      {grounded ? (
        <>
          <div className="answer-body">{response.answer}</div>
          <div className="evidence-head">
            <span className="label">
              Evidence &middot; {response.citations.length}{" "}
              {response.citations.length === 1 ? "source" : "sources"}
            </span>
          </div>
          {response.citations.map((citation, index) => (
            <CitationCard key={citation.chunk_id} citation={citation} index={index} />
          ))}
          <div style={{ padding: "var(--s3) var(--s5) var(--s5)" }}>
            <p className="mono muted">
              gate: {response.gate_outcome}
            </p>
          </div>
        </>
      ) : (
        <div className="no-evidence">
          <h3 className="no-evidence-title">{response.answer}</h3>
          <p className="no-evidence-copy">
            StudentOS only answers when approved university documents support the
            answer. Nothing in the current knowledge base covers this question, so no
            answer was generated rather than an uncertain one.
          </p>

          <div className="gate-rail">
            {GATES.map((gate, index) => (
              <div className="gate-row" key={gate.id} data-state={states[index]}>
                <span className="gate-row-num">{gate.id}</span>
                <span className="gate-row-name">{gate.name}</span>
                <span className={`gate-row-state gate-${states[index]}`}>
                  {GATE_LABEL[states[index]]}
                </span>
              </div>
            ))}
          </div>

          <p className="mono muted" style={{ marginTop: "var(--s4)" }}>
            gate: {response.gate_outcome} &middot; retrieved {response.retrieved} &middot;
            top similarity {response.top_score.toFixed(3)}
          </p>
        </div>
      )}
    </section>
  );
}
