import { useCallback, useEffect, useRef, useState } from "react";
import {
  approveDocument,
  listDocuments,
  revokeDocument,
  uploadDocument,
  type DocumentRow,
} from "../api";
import { Shell } from "../components/Shell";
import { StatusChip } from "../components/StatusChip";
import {
  IconAlert,
  IconCheck,
  IconDocuments,
  IconFile,
  IconShield,
  IconUpload,
} from "../components/icons";
import { navigate } from "../lib/router";

const PIPELINE = [
  "Validate the file",
  "Extract pages",
  "Split into passages",
  "Generate embeddings",
  "Store for review",
];

function useDocuments() {
  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      setDocuments(await listDocuments());
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load documents.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { documents, loading, error, refresh, setError };
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/* ────────────────────────────────────────────── Overview ── */

export function AdminOverview() {
  const { documents, loading } = useDocuments();

  const approved = documents.filter((d) => d.status === "approved");
  const pending = documents.filter((d) => d.status === "ready");
  const failed = documents.filter((d) => d.status === "failed");
  const passages = documents.reduce((total, d) => total + d.chunk_count, 0);

  return (
    <Shell title="Overview" subtitle="Knowledge base status">
      <div className="page-head">
        <h2>Knowledge base</h2>
        <p>
          Students can only be answered from documents you have approved. Nothing
          reaches them until it passes through this console.
        </p>
      </div>

      <div className="stat-grid stagger">
        <div className="stat">
          <div className="label">Approved</div>
          <div className="stat-value">{loading ? "--" : approved.length}</div>
          <div className="stat-note">Retrievable by students</div>
        </div>
        <div className="stat">
          <div className="label">Awaiting review</div>
          <div className="stat-value">{loading ? "--" : pending.length}</div>
          <div className="stat-note">Ingested, not yet approved</div>
        </div>
        <div className="stat">
          <div className="label">Passages indexed</div>
          <div className="stat-value">{loading ? "--" : passages}</div>
          <div className="stat-note">Across all documents</div>
        </div>
        <div className="stat">
          <div className="label">Failed</div>
          <div className="stat-value">{loading ? "--" : failed.length}</div>
          <div className="stat-note">Needs attention</div>
        </div>
      </div>

      <div className="grid-2" style={{ marginTop: "var(--s6)", alignItems: "start" }}>
        <section className="panel">
          <div className="panel-head">
            <h2>Awaiting your approval</h2>
            <button type="button" className="btn btn-ghost" onClick={() => navigate("admin/documents")}>
              Open library
            </button>
          </div>
          {pending.length === 0 ? (
            <div className="empty-state" style={{ padding: "var(--s10) var(--s5)" }}>
              <IconCheck size={24} />
              <div className="empty-state-title" style={{ marginTop: "var(--s3)" }}>
                Nothing pending
              </div>
              <p>Every ingested document has been reviewed.</p>
            </div>
          ) : (
            <table className="table">
              <tbody>
                {pending.map((doc) => (
                  <tr key={doc.id}>
                    <td>
                      <div className="doc-title">{doc.title}</div>
                      <div className="doc-file">
                        {doc.page_count} pages &middot; {doc.chunk_count} passages
                      </div>
                    </td>
                    <td>
                      <div className="row-actions">
                        <button
                          type="button"
                          className="btn btn-ghost"
                          onClick={() => navigate("admin/documents")}
                        >
                          Review
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>Add a document</h2>
          </div>
          <div className="panel-body stack stack-4">
            <p style={{ fontSize: "var(--text-sm)", color: "var(--ink-3)" }}>
              Upload a PDF to extract, split and embed it. It stays invisible to
              students until you approve it.
            </p>
            <button type="button" className="btn btn-primary" onClick={() => navigate("admin/upload")}>
              <IconUpload size={15} />
              Upload a PDF
            </button>
          </div>
        </section>
      </div>
    </Shell>
  );
}

/* ───────────────────────────────────────────── Documents ── */

export function AdminDocuments() {
  const { documents, loading, error, refresh, setError } = useDocuments();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notice, setNotice] = useState("");

  async function act(id: string, action: "approve" | "revoke") {
    setBusyId(id);
    setNotice("");
    try {
      if (action === "approve") await approveDocument(id);
      else await revokeDocument(id);
      await refresh();
      setNotice(
        action === "approve"
          ? "Document approved. Students can be answered from it now."
          : "Approval revoked. It stopped being retrievable immediately.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "The action failed.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Shell
      title="Documents"
      subtitle={`${documents.length} in the library`}
      actions={
        <button type="button" className="btn btn-secondary" onClick={() => navigate("admin/upload")}>
          <IconUpload size={15} />
          Upload
        </button>
      }
    >
      <div className="page-head">
        <h2>Document library</h2>
        <p>
          Approval is the gate between an ingested document and a student's answer.
          Revoking takes effect immediately, with no re-indexing.
        </p>
      </div>

      {error && (
        <div className="banner banner-error" style={{ marginBottom: "var(--s4)" }} role="alert">
          <IconAlert size={15} />
          <span>{error}</span>
        </div>
      )}
      {notice && (
        <div className="banner banner-success" style={{ marginBottom: "var(--s4)" }} role="status">
          <IconCheck size={15} />
          <span>{notice}</span>
        </div>
      )}

      <section className="panel">
        {loading ? (
          <div className="empty-state">
            <span className="spinner" />
          </div>
        ) : documents.length === 0 ? (
          <div className="empty-state">
            <IconDocuments size={26} />
            <div className="empty-state-title" style={{ marginTop: "var(--s3)" }}>
              The library is empty
            </div>
            <p>Upload a PDF to begin building the approved knowledge base.</p>
            <button
              type="button"
              className="btn btn-primary"
              style={{ marginTop: "var(--s5)" }}
              onClick={() => navigate("admin/upload")}
            >
              Upload a PDF
            </button>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Document</th>
                <th>Pages</th>
                <th>Passages</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id}>
                  <td>
                    <div className="doc-title">{doc.title}</div>
                    <div className="doc-file">{doc.original_filename}</div>
                    {doc.error_message && (
                      <div
                        style={{
                          marginTop: 6,
                          fontSize: "var(--text-xs)",
                          color: "var(--crimson)",
                        }}
                      >
                        {doc.error_message}
                      </div>
                    )}
                  </td>
                  <td className="num" data-label="Pages">{doc.page_count}</td>
                  <td className="num" data-label="Passages">{doc.chunk_count}</td>
                  <td data-label="Status">
                    <StatusChip status={doc.status} />
                  </td>
                  <td>
                    <div className="row-actions">
                      {doc.status === "ready" && (
                        <button
                          type="button"
                          className="btn btn-primary"
                          disabled={busyId === doc.id}
                          onClick={() => void act(doc.id, "approve")}
                        >
                          {busyId === doc.id ? "Working..." : "Approve"}
                        </button>
                      )}
                      {doc.status === "approved" && (
                        <button
                          type="button"
                          className="btn btn-danger"
                          disabled={busyId === doc.id}
                          onClick={() => void act(doc.id, "revoke")}
                        >
                          {busyId === doc.id ? "Working..." : "Revoke"}
                        </button>
                      )}
                    </div>
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

/* ──────────────────────────────────────────────── Upload ── */

export function AdminUpload() {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(-1);
  const [result, setResult] = useState<DocumentRow | null>(null);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!busy) return;
    setStep(0);
    const timers = PIPELINE.map((_, index) =>
      window.setTimeout(() => setStep(index), index * 900),
    );
    return () => timers.forEach(window.clearTimeout);
  }, [busy]);

  function pick(next: File | null) {
    setError("");
    setResult(null);
    if (!next) return;
    if (!next.name.toLowerCase().endsWith(".pdf")) {
      setError("StudentOS accepts PDF files only.");
      return;
    }
    setFile(next);
    if (!title.trim()) {
      setTitle(next.name.replace(/\.pdf$/i, "").replace(/[-_]+/g, " "));
    }
  }

  async function submit() {
    if (!file) {
      setError("Choose a PDF first.");
      return;
    }
    if (!title.trim()) {
      setError("Give the document a title — students see this in citations.");
      return;
    }

    setError("");
    setBusy(true);
    setResult(null);
    try {
      const uploaded = await uploadDocument(file, title.trim());
      setStep(PIPELINE.length);
      setResult(uploaded);
      if (uploaded.status === "failed") {
        setError(uploaded.error_message ?? "Ingestion failed.");
      } else {
        setFile(null);
        setTitle("");
        if (inputRef.current) inputRef.current.value = "";
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "The upload failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell title="Upload" subtitle="Add a document to the knowledge base">
      <div className="page-head">
        <h2>Ingest a document</h2>
        <p>
          The file is validated, split into passages and embedded. It will sit in the
          library as <em>ready for review</em> until you approve it.
        </p>
      </div>

      <div className="grid-2" style={{ alignItems: "start" }}>
        <div className="stack stack-4">
          <div
            className="dropzone"
            data-drag={dragging}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              pick(e.dataTransfer.files?.[0] ?? null);
            }}
          >
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,.pdf"
              onChange={(e) => pick(e.target.files?.[0] ?? null)}
              aria-label="Choose a PDF"
            />
            <IconUpload size={26} />
            <div className="dropzone-title">Drop a PDF here</div>
            <div className="dropzone-hint">or click to browse &middot; 20 MB maximum</div>
          </div>

          {file && (
            <div className="file-card enter">
              <span className="file-icon">
                <IconFile size={17} />
              </span>
              <span className="file-meta">
                <span className="file-name">{file.name}</span>
                <span className="file-size">{formatBytes(file.size)}</span>
              </span>
              {!busy && (
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => {
                    setFile(null);
                    if (inputRef.current) inputRef.current.value = "";
                  }}
                >
                  Remove
                </button>
              )}
            </div>
          )}

          <div className="field">
            <label htmlFor="doc-title">Document title</label>
            <input
              id="doc-title"
              className="input"
              placeholder="CS Department Student Handbook, Autumn 2026"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            <span style={{ fontSize: "var(--text-xs)", color: "var(--ink-4)" }}>
              Shown to students in every citation, so use the document's real name
              rather than the filename.
            </span>
          </div>

          {error && (
            <div className="banner banner-error" role="alert">
              <IconAlert size={15} />
              <span>{error}</span>
            </div>
          )}

          {result && result.status !== "failed" && (
            <div className="banner banner-success" role="status">
              <IconCheck size={15} />
              <span>
                <strong>{result.title}</strong> ingested — {result.page_count} pages,{" "}
                {result.chunk_count} passages. Approve it in the library to make it
                answerable.
              </span>
            </div>
          )}

          <div className="row row-3">
            <button type="button" className="btn btn-primary" onClick={submit} disabled={busy}>
              {busy ? "Ingesting..." : "Upload and ingest"}
            </button>
            {result && result.status !== "failed" && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => navigate("admin/documents")}
              >
                Go to library
              </button>
            )}
          </div>
        </div>

        <section className="panel">
          <div className="panel-head">
            <h2>Ingestion pipeline</h2>
          </div>
          <div className="panel-body">
            {busy && (
              <div className="progress" style={{ marginBottom: "var(--s5)" }}>
                <div
                  className="progress-bar"
                  style={{ width: `${Math.min(((step + 1) / PIPELINE.length) * 100, 96)}%` }}
                />
              </div>
            )}

            <div className="pipeline">
              {PIPELINE.map((label, index) => {
                const state =
                  step > index || (result && result.status !== "failed")
                    ? "done"
                    : step === index && busy
                      ? "active"
                      : "idle";
                return (
                  <div className="pipeline-step" key={label} data-state={state}>
                    <span className="pipeline-dot">
                      {state === "done" && <IconCheck size={11} />}
                      {state === "active" && <span className="spinner" style={{ width: 10, height: 10 }} />}
                    </span>
                    {label}
                  </div>
                );
              })}
            </div>

            <hr className="rule" style={{ margin: "var(--s5) 0" }} />

            <div className="row row-3" style={{ alignItems: "flex-start" }}>
              <IconShield size={17} />
              <p style={{ fontSize: "var(--text-sm)", color: "var(--ink-3)" }}>
                Ingestion never makes a document answerable on its own. Approval is a
                separate, deliberate step.
              </p>
            </div>
          </div>
        </section>
      </div>
    </Shell>
  );
}

/* ──────────────────────────────────────────────── Activity ── */

export function AdminActivity() {
  const { documents, loading } = useDocuments();

  const events = documents.map((doc) => ({
    id: doc.id,
    title: doc.title,
    status: doc.status,
    detail:
      doc.status === "approved"
        ? "Approved and retrievable by students"
        : doc.status === "ready"
          ? "Ingested, awaiting approval"
          : doc.status === "failed"
            ? (doc.error_message ?? "Ingestion failed")
            : "In progress",
  }));

  return (
    <Shell title="Activity" subtitle="Document lifecycle">
      <div className="page-head">
        <h2>Recent activity</h2>
        <p>The current state of every document in the knowledge base.</p>
      </div>

      <section className="panel">
        {loading ? (
          <div className="empty-state">
            <span className="spinner" />
          </div>
        ) : events.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-title">No activity yet</div>
            <p>Uploaded documents and their status changes will appear here.</p>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Document</th>
                <th>State</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.id}>
                  <td>
                    <div className="doc-title">{event.title}</div>
                  </td>
                  <td style={{ color: "var(--ink-3)" }} data-label="State">{event.detail}</td>
                  <td data-label="Status">
                    <StatusChip status={event.status} />
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

/* ──────────────────────────────────────────────── Settings ── */

export function AdminSettings() {
  return (
    <Shell title="Settings" subtitle="Retrieval configuration">
      <div className="page-head">
        <h2>Configuration</h2>
        <p>
          Retrieval and chunking values are version-controlled on the server so every
          evaluation run is reproducible. They are shown here read-only.
        </p>
      </div>

      <div className="grid-2" style={{ alignItems: "start" }}>
        <section className="panel">
          <div className="panel-head">
            <h2>Retrieval</h2>
            <span className="label">Read only</span>
          </div>
          <table className="table">
            <tbody>
              <tr>
                <td>Chunk size</td>
                <td className="num">800 tokens</td>
              </tr>
              <tr>
                <td>Chunk overlap</td>
                <td className="num">150 tokens</td>
              </tr>
              <tr>
                <td>Tokenizer</td>
                <td className="mono">tiktoken / cl100k_base</td>
              </tr>
              <tr>
                <td>Passages retrieved</td>
                <td className="num">8</td>
              </tr>
              <tr>
                <td>Passages sent to the model</td>
                <td className="num">5</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>Grounding thresholds</h2>
          </div>
          <table className="table">
            <tbody>
              <tr>
                <td>Gate 1 minimum similarity</td>
                <td className="num">0.35</td>
              </tr>
              <tr>
                <td>Supporting evidence threshold</td>
                <td className="num">0.30</td>
              </tr>
              <tr>
                <td>Calibration</td>
                <td>
                  <span className="chip chip-ready">Uncalibrated</span>
                </td>
              </tr>
            </tbody>
          </table>
          <div className="panel-body">
            <div className="banner banner-info">
              <IconAlert size={15} />
              <span>
                These thresholds are starting points, not measured findings. They must
                be calibrated against an evaluation set before any result is presented
                as validated.
              </span>
            </div>
          </div>
        </section>
      </div>
    </Shell>
  );
}
