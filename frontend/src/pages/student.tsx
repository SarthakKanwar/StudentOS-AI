import { useCallback, useEffect, useRef, useState } from "react";
import {
  askQuestion,
  listDocuments,
  studentFileUrl,
  type ChatResponse,
  type DocumentRow,
} from "../api";
import { AnswerPanel } from "../components/AnswerPanel";
import { Shell } from "../components/Shell";
import { StatusChip } from "../components/StatusChip";
import {
  IconAlert,
  IconArrowRight,
  IconBook,
  IconSearch,
  IconTrash,
} from "../components/icons";
import { initials, useAuth } from "../lib/auth";
import {
  appendHistory,
  clearHistory,
  loadHistory,
  relativeTime,
  type HistoryEntry,
} from "../lib/history";
import { navigate } from "../lib/router";

const SUGGESTIONS = [
  "When is the CS-402 Computer Networks examination, and where is it held?",
  "What is the minimum attendance required to sit an end-term examination?",
  "How is the final grade split between internal assessment and the end-term exam?",
];

const STAGES = [
  "Embedding your question",
  "Searching approved documents",
  "Checking the grounding gates",
];

function useApprovedDocuments() {
  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    listDocuments()
      .then((rows) => {
        if (!cancelled) setDocuments(rows);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { documents, approved: documents.filter((d) => d.status === "approved"), loading };
}

/* ─────────────────────────────────────────────────── Ask ── */

export function StudentAsk() {
  const { session } = useAuth();
  const [question, setQuestion] = useState("");
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [asked, setAsked] = useState("");
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState(0);
  const [error, setError] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!loading) return;
    setStage(0);
    const timers = [
      window.setTimeout(() => setStage(1), 550),
      window.setTimeout(() => setStage(2), 1500),
    ];
    return () => timers.forEach(window.clearTimeout);
  }, [loading]);

  const ask = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) {
        setError("Type a question first.");
        textareaRef.current?.focus();
        return;
      }
      setError("");
      setLoading(true);
      setResponse(null);
      setAsked(trimmed);

      try {
        const result = await askQuestion(trimmed);
        setResponse(result);
        if (session) appendHistory(session.email, trimmed, result);
      } catch (err) {
        setError(err instanceof Error ? err.message : "The request failed.");
      } finally {
        setLoading(false);
      }
    },
    [session],
  );

  return (
    <Shell
      title="Ask StudentOS"
      subtitle="Answers are drawn only from approved documents"
    >
      <div className="page-head">
        <h2>What would you like to know?</h2>
        <p>
          Ask about courses, examinations, syllabus content or regulations. If the
          approved documents do not cover it, StudentOS will tell you rather than
          guess.
        </p>
      </div>

      <div className="composer">
        <textarea
          ref={textareaRef}
          rows={3}
          value={question}
          placeholder="When is the CS-402 Computer Networks examination?"
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey || !e.shiftKey)) {
              e.preventDefault();
              void ask(question);
            }
          }}
          aria-label="Your question"
        />
        <div className="composer-foot">
          <span className="composer-hint">
            Enter to ask &middot; Shift + Enter for a new line
          </span>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => void ask(question)}
            disabled={loading}
          >
            {loading ? "Working..." : "Ask"}
            {!loading && <IconArrowRight size={15} />}
          </button>
        </div>
      </div>

      {!response && !loading && (
        <div className="suggestions">
          {SUGGESTIONS.map((item) => (
            <button
              type="button"
              className="suggestion"
              key={item}
              onClick={() => {
                setQuestion(item);
                void ask(item);
              }}
            >
              {item}
            </button>
          ))}
        </div>
      )}

      {error && (
        <div className="banner banner-error" role="alert" style={{ marginTop: "var(--s5)" }}>
          <IconAlert size={15} />
          <span>{error}</span>
        </div>
      )}

      {(loading || response) && (
        <div style={{ marginTop: "var(--s6)" }}>
          {asked && (
            <p
              className="display"
              style={{
                fontSize: "var(--text-md)",
                color: "var(--ink-3)",
                marginBottom: "var(--s4)",
              }}
            >
              {asked}
            </p>
          )}

          {loading && (
            <section className="panel enter">
              <div className="processing">
                <span className="spinner" />
                <div className="processing-steps">
                  {STAGES.map((label, index) => (
                    <span
                      className="processing-step"
                      key={label}
                      data-active={index <= stage}
                    >
                      {label}
                    </span>
                  ))}
                </div>
              </div>
            </section>
          )}

          {response && !loading && <AnswerPanel response={response} />}
        </div>
      )}
    </Shell>
  );
}

/* ────────────────────────────────────────────── Overview ── */

export function StudentOverview() {
  const { session } = useAuth();
  const { approved, loading } = useApprovedDocuments();
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  useEffect(() => {
    if (session) setHistory(loadHistory(session.email));
  }, [session]);

  const grounded = history.filter((h) => h.response.response_type === "grounded").length;
  const pages = approved.reduce((total, doc) => total + doc.page_count, 0);

  return (
    <Shell title="Overview" subtitle={session?.name}>
      <div className="page-head">
        <h2>Welcome back, {session?.name.split(" ")[0]}.</h2>
        <p>
          Your questions are answered from {approved.length}{" "}
          {approved.length === 1 ? "document" : "documents"} the university has
          approved.
        </p>
      </div>

      <div className="stat-grid stagger">
        <div className="stat">
          <div className="label">Approved sources</div>
          <div className="stat-value">{loading ? "--" : approved.length}</div>
          <div className="stat-note">{pages} pages available</div>
        </div>
        <div className="stat">
          <div className="label">Questions asked</div>
          <div className="stat-value">{history.length}</div>
          <div className="stat-note">In this browser</div>
        </div>
        <div className="stat">
          <div className="label">Grounded answers</div>
          <div className="stat-value">{grounded}</div>
          <div className="stat-note">Backed by a citation</div>
        </div>
        <div className="stat">
          <div className="label">Declined</div>
          <div className="stat-value">{history.length - grounded}</div>
          <div className="stat-note">No supporting evidence</div>
        </div>
      </div>

      <div className="grid-2" style={{ marginTop: "var(--s6)" }}>
        <section className="panel">
          <div className="panel-head">
            <h2>Start a question</h2>
          </div>
          <div className="panel-body stack stack-3">
            {SUGGESTIONS.slice(0, 2).map((item) => (
              <button
                type="button"
                className="suggestion"
                key={item}
                style={{ textAlign: "left", borderRadius: "var(--r-md)" }}
                onClick={() => navigate("app/ask")}
              >
                {item}
              </button>
            ))}
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => navigate("app/ask")}
              style={{ marginTop: "var(--s2)" }}
            >
              Open the assistant
              <IconArrowRight size={15} />
            </button>
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>Recent questions</h2>
            {history.length > 0 && (
              <button type="button" className="btn btn-ghost" onClick={() => navigate("app/history")}>
                View all
              </button>
            )}
          </div>
          {history.length === 0 ? (
            <div className="empty-state" style={{ padding: "var(--s10) var(--s5)" }}>
              <div className="empty-state-title">Nothing asked yet</div>
              <p>Your recent questions and their evidence will appear here.</p>
            </div>
          ) : (
            <div>
              {history.slice(0, 4).map((entry) => (
                <div className="history-item" key={entry.id} onClick={() => navigate("app/history")}>
                  <span
                    className={`history-marker history-marker-${
                      entry.response.response_type === "grounded" ? "grounded" : "notfound"
                    }`}
                  />
                  <span style={{ minWidth: 0 }}>
                    <span className="history-q">{entry.question}</span>
                    <span className="history-meta">
                      <span>{relativeTime(entry.askedAt)}</span>
                      <span>
                        {entry.response.response_type === "grounded"
                          ? `${entry.response.citations.length} source(s)`
                          : "No evidence"}
                      </span>
                    </span>
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </Shell>
  );
}

/* ─────────────────────────────────────────────── Sources ── */

export function StudentSources() {
  const { approved, loading } = useApprovedDocuments();

  return (
    <Shell title="Sources" subtitle="Documents your answers can draw on">
      <div className="page-head">
        <h2>Approved knowledge base</h2>
        <p>
          Only these documents can be retrieved. Anything an administrator has not
          approved is invisible to the assistant.
        </p>
      </div>

      <section className="panel">
        <div className="panel-head">
          <h2>{loading ? "Loading..." : `${approved.length} approved`}</h2>
          <span className="label">Read only</span>
        </div>

        {!loading && approved.length === 0 ? (
          <div className="empty-state">
            <IconBook size={26} />
            <div className="empty-state-title" style={{ marginTop: "var(--s3)" }}>
              No approved documents yet
            </div>
            <p>
              Until an administrator approves a document, StudentOS has nothing to
              answer from and will decline every question.
            </p>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Document</th>
                <th>Pages</th>
                <th>Passages</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {approved.map((doc) => (
                <tr key={doc.id}>
                  <td>
                    <a
                      className="doc-link"
                      href={studentFileUrl(doc.id)}
                      target="_blank"
                      rel="noopener noreferrer"
                      title="Open the original PDF"
                    >
                      <span className="doc-title">{doc.title}</span>
                      <span className="doc-file">{doc.original_filename}</span>
                    </a>
                  </td>
                  <td className="num" data-label="Pages">{doc.page_count}</td>
                  <td className="num" data-label="Passages">{doc.chunk_count}</td>
                  <td data-label="Status">
                    <StatusChip status={doc.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </Shell>
  );
}

/* ─────────────────────────────────────────────── History ── */

export function StudentHistory() {
  const { session } = useAuth();
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [selected, setSelected] = useState<HistoryEntry | null>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    if (session) setHistory(loadHistory(session.email));
  }, [session]);

  const visible = history.filter((entry) =>
    entry.question.toLowerCase().includes(filter.trim().toLowerCase()),
  );

  return (
    <Shell
      title="History"
      subtitle={`${history.length} question${history.length === 1 ? "" : "s"}`}
      actions={
        history.length > 0 && (
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => {
              if (!session) return;
              clearHistory(session.email);
              setHistory([]);
              setSelected(null);
            }}
          >
            <IconTrash size={15} />
            Clear
          </button>
        )
      }
    >
      <div className="page-head">
        <h2>Your questions</h2>
        <p>Stored in this browser only. Select a question to review its evidence.</p>
      </div>

      {history.length === 0 ? (
        <section className="panel">
          <div className="empty-state">
            <IconSearch size={26} />
            <div className="empty-state-title" style={{ marginTop: "var(--s3)" }}>
              No questions yet
            </div>
            <p>Ask something in the assistant and it will be recorded here.</p>
            <button
              type="button"
              className="btn btn-secondary"
              style={{ marginTop: "var(--s5)" }}
              onClick={() => navigate("app/ask")}
            >
              Open the assistant
            </button>
          </div>
        </section>
      ) : (
        <div className="grid-2" style={{ alignItems: "start" }}>
          <section className="panel">
            <div className="panel-head">
              <input
                className="input"
                placeholder="Filter questions"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                aria-label="Filter questions"
              />
            </div>
            {visible.length === 0 ? (
              <div className="empty-state" style={{ padding: "var(--s10) var(--s5)" }}>
                <p>No question matches that filter.</p>
              </div>
            ) : (
              visible.map((entry) => (
                <div
                  className="history-item"
                  key={entry.id}
                  onClick={() => setSelected(entry)}
                  style={
                    selected?.id === entry.id
                      ? { background: "var(--surface-sunken)" }
                      : undefined
                  }
                >
                  <span
                    className={`history-marker history-marker-${
                      entry.response.response_type === "grounded" ? "grounded" : "notfound"
                    }`}
                  />
                  <span style={{ minWidth: 0 }}>
                    <span className="history-q">{entry.question}</span>
                    <span className="history-meta">
                      <span>{relativeTime(entry.askedAt)}</span>
                      <span>
                        {entry.response.response_type === "grounded"
                          ? "Grounded"
                          : "No evidence"}
                      </span>
                    </span>
                  </span>
                </div>
              ))
            )}
          </section>

          <div>
            {selected ? (
              <AnswerPanel response={selected.response} />
            ) : (
              <section className="panel">
                <div className="empty-state" style={{ padding: "var(--s12) var(--s5)" }}>
                  <div className="empty-state-title">Select a question</div>
                  <p>Its answer and supporting evidence will appear here.</p>
                </div>
              </section>
            )}
          </div>
        </div>
      )}
    </Shell>
  );
}

/* ─────────────────────────────────────────────── Profile ── */

export function StudentProfile() {
  const { session, signOut } = useAuth();
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  useEffect(() => {
    if (session) setHistory(loadHistory(session.email));
  }, [session]);

  if (!session) return null;

  return (
    <Shell title="Profile">
      <div className="page-head">
        <h2>Account</h2>
        <p>Prototype account details, stored in this browser.</p>
      </div>

      <div className="grid-2" style={{ alignItems: "start" }}>
        <section className="panel">
          <div className="panel-body">
            <div className="row row-4">
              <span
                className="avatar"
                style={{
                  width: 52,
                  height: 52,
                  fontSize: "var(--text-md)",
                  background: "var(--ink)",
                  color: "var(--ink-inverse)",
                  borderRadius: "var(--r-md)",
                }}
              >
                {initials(session.name)}
              </span>
              <div>
                <div className="display" style={{ fontSize: "var(--text-lg)" }}>
                  {session.name}
                </div>
                <div className="muted" style={{ fontSize: "var(--text-sm)" }}>
                  {session.email}
                </div>
              </div>
            </div>

            <hr className="rule" style={{ margin: "var(--s5) 0" }} />

            <dl className="stack stack-4" style={{ margin: 0 }}>
              <div className="row spread">
                <dt className="label">Role</dt>
                <dd style={{ margin: 0 }}>
                  {session.role === "admin" ? "Administrator" : "Student"}
                </dd>
              </div>
              <div className="row spread">
                <dt className="label">Questions asked</dt>
                <dd style={{ margin: 0 }} className="num">
                  {history.length}
                </dd>
              </div>
              <div className="row spread">
                <dt className="label">Session</dt>
                <dd style={{ margin: 0 }}>Restored on refresh</dd>
              </div>
            </dl>

            <button
              type="button"
              className="btn btn-secondary"
              style={{ marginTop: "var(--s6)" }}
              onClick={() => {
                signOut();
                navigate("signin");
              }}
            >
              Sign out
            </button>
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>How your answers are produced</h2>
          </div>
          <div className="panel-body stack stack-4">
            <p style={{ fontSize: "var(--text-sm)", color: "var(--ink-3)" }}>
              Every question runs through the same three checks before you see an
              answer.
            </p>
            <div className="gate-rail">
              <div className="gate-row">
                <span className="gate-row-num">Gate 1</span>
                <span className="gate-row-name">Evidence exists in approved documents</span>
              </div>
              <div className="gate-row">
                <span className="gate-row-num">Gate 2</span>
                <span className="gate-row-name">The model confirms the evidence supports it</span>
              </div>
              <div className="gate-row">
                <span className="gate-row-num">Gate 3</span>
                <span className="gate-row-name">Each citation is verified in code</span>
              </div>
            </div>
          </div>
        </section>
      </div>
    </Shell>
  );
}
