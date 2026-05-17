import type { NoteResult, ProcessResponse } from "../types";
import { authFetch } from "../auth/api";

const API_BASE = "/api";

export async function submitUrl(url: string, language: string): Promise<ProcessResponse> {
  const res = await authFetch(`${API_BASE}/process`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, language }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function fetchResult(jobId: string): Promise<NoteResult> {
  const res = await authFetch(`${API_BASE}/tasks/${jobId}/result`);
  if (!res.ok) {
    if (res.status === 202) throw new Error("Still processing");
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export function getProgressUrl(jobId: string): string {
  return `${API_BASE}/tasks/${jobId}/progress`;
}
