export interface DocumentRow {
  id: string;
  title: string;
  original_filename: string;
  status: string;
  page_count: number;
  chunk_count: number;
  error_message: string | null;
}

export interface Citation {
  chunk_id: string;
  document_title: string;
  page_start: number | null;
  page_end: number | null;
  excerpt: string;
  score: number;
}

export interface ChatResponse {
  response_type: "grounded" | "not_found";
  answer: string;
  citations: Citation[];
  gate_outcome: string;
  top_score: number;
  retrieved: number;
}

async function unwrap<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${response.status})`);
  }
  return response.json();
}

export async function listDocuments(): Promise<DocumentRow[]> {
  const response = await fetch("/api/documents");
  const body = await unwrap<{ documents: DocumentRow[] }>(response);
  return body.documents;
}

export async function uploadDocument(file: File, title: string) {
  const form = new FormData();
  form.append("file", file);
  form.append("title", title);
  return unwrap<DocumentRow>(await fetch("/api/admin/upload", { method: "POST", body: form }));
}

export async function approveDocument(documentId: string) {
  return unwrap(await fetch(`/api/admin/approve/${documentId}`, { method: "POST" }));
}

export async function revokeDocument(documentId: string) {
  return unwrap(await fetch(`/api/admin/revoke/${documentId}`, { method: "POST" }));
}

export async function deleteDocument(documentId: string) {
  return unwrap(
    await fetch(`/api/admin/documents/${documentId}`, { method: "DELETE" }),
  );
}

/* Admin sees the original at any status; students only through the
   approved-only route, which the backend enforces. */
export function adminFileUrl(documentId: string): string {
  return `/api/admin/documents/${encodeURIComponent(documentId)}/file`;
}

export function studentFileUrl(documentId: string): string {
  return `/api/documents/${encodeURIComponent(documentId)}/file`;
}

export async function askQuestion(question: string): Promise<ChatResponse> {
  return unwrap<ChatResponse>(
    await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    }),
  );
}

export function formatPages(citation: Citation): string {
  if (citation.page_start === null) return "no page";
  if (citation.page_start === citation.page_end) return `Page ${citation.page_start}`;
  return `Pages ${citation.page_start}-${citation.page_end}`;
}
