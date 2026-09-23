import type { ChatResponse } from "../api";

export interface HistoryEntry {
  id: string;
  question: string;
  askedAt: number;
  response: ChatResponse;
}

const LIMIT = 40;

function key(email: string) {
  return `studentos.history.${email.toLowerCase()}`;
}

export function loadHistory(email: string): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(key(email));
    return raw ? (JSON.parse(raw) as HistoryEntry[]) : [];
  } catch {
    return [];
  }
}

export function appendHistory(
  email: string,
  question: string,
  response: ChatResponse,
): HistoryEntry[] {
  const entry: HistoryEntry = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    question,
    askedAt: Date.now(),
    response,
  };
  const next = [entry, ...loadHistory(email)].slice(0, LIMIT);
  localStorage.setItem(key(email), JSON.stringify(next));
  return next;
}

export function clearHistory(email: string) {
  localStorage.removeItem(key(email));
}

export function relativeTime(timestamp: number): string {
  const seconds = Math.round((Date.now() - timestamp) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days} d ago`;
  return new Date(timestamp).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
  });
}
