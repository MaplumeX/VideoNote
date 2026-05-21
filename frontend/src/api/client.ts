import type {
  NoteResult,
  ProcessResponse,
  ProvidersResponse,
  SettingsResponse,
  SettingsRequest,
  TaskItem,
  TaskListResponse,
  Tag,
  TagWithCount,
  Folder,
  FolderTreeNode,
  NoteTagAddRequest,
  NoteFolderUpdateRequest,
  FavoriteToggleRequest,
  BatchTagRequest,
  BatchMoveRequest,
  BatchFavoriteRequest,
  BatchDeleteRequest,
  ModelsResponse,
} from "../types";
import { authFetch } from "../auth/api";

const API_BASE = "/api";

async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await authFetch(url, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  const text = await res.text();
  if (!text) return undefined as T;
  return JSON.parse(text);
}

// --- Existing endpoints ---

export async function submitUrl(url: string, language: string): Promise<ProcessResponse> {
  return apiFetch<ProcessResponse>(`${API_BASE}/process`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, language }),
  });
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

export async function fetchProviders(): Promise<ProvidersResponse> {
  return apiFetch<ProvidersResponse>(`${API_BASE}/providers`);
}

export async function fetchSettings(): Promise<SettingsResponse> {
  return apiFetch<SettingsResponse>(`${API_BASE}/settings`);
}

export async function saveSettings(settings: SettingsRequest): Promise<void> {
  const res = await authFetch(`${API_BASE}/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
}

export async function fetchModels(
  apiKey: string,
  apiBase: string,
  category: "asr" | "llm"
): Promise<ModelsResponse> {
  return apiFetch<ModelsResponse>(`${API_BASE}/models`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey, api_base: apiBase, category }),
  });
}

// --- Task listing with filters ---

export async function fetchTaskById(jobId: string): Promise<TaskItem> {
  return apiFetch<TaskItem>(`${API_BASE}/tasks/${jobId}`);
}

export async function fetchTasks(params: {
  page?: number;
  limit?: number;
  folder?: string;
  tag?: string;
  is_favorite?: boolean;
  search?: string;
  sort_by?: string;
  sort_order?: string;
}): Promise<TaskListResponse> {
  const qs = new URLSearchParams();
  if (params.page) qs.set("page", String(params.page));
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.folder) qs.set("folder", params.folder);
  if (params.tag) qs.set("tag", params.tag);
  if (params.is_favorite !== undefined) qs.set("is_favorite", String(params.is_favorite));
  if (params.search) qs.set("search", params.search);
  if (params.sort_by) qs.set("sort_by", params.sort_by);
  if (params.sort_order) qs.set("sort_order", params.sort_order);
  return apiFetch<TaskListResponse>(`${API_BASE}/tasks?${qs.toString()}`);
}

// --- Tag endpoints ---

export async function fetchTags(): Promise<TagWithCount[]> {
  return apiFetch<TagWithCount[]>(`${API_BASE}/tags`);
}

export async function createTag(name: string, color?: string): Promise<Tag> {
  return apiFetch<Tag>(`${API_BASE}/tags`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, color: color || "" }),
  });
}

export async function updateTag(tagId: string, data: { name?: string; color?: string }): Promise<Tag> {
  return apiFetch<Tag>(`${API_BASE}/tags/${tagId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deleteTag(tagId: string): Promise<void> {
  await apiFetch(`${API_BASE}/tags/${tagId}`, { method: "DELETE" });
}

// --- Folder endpoints ---

export async function fetchFolders(): Promise<Folder[]> {
  return apiFetch<Folder[]>(`${API_BASE}/folders`);
}

export async function fetchFolderTree(): Promise<FolderTreeNode[]> {
  return apiFetch<FolderTreeNode[]>(`${API_BASE}/folders/tree`);
}

export async function createFolder(name: string, parentId?: string): Promise<Folder> {
  return apiFetch<Folder>(`${API_BASE}/folders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, parent_id: parentId || null }),
  });
}

export async function updateFolder(
  folderId: string,
  data: { name?: string; parent_id?: string | null },
): Promise<Folder> {
  return apiFetch<Folder>(`${API_BASE}/folders/${folderId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deleteFolder(folderId: string): Promise<void> {
  await apiFetch(`${API_BASE}/folders/${folderId}`, { method: "DELETE" });
}

// --- Note-tag association ---

export async function fetchNoteTags(jobId: string): Promise<Tag[]> {
  const data = await apiFetch<{ tags: Tag[] }>(`${API_BASE}/tasks/${jobId}/tags`);
  return data.tags;
}

export async function addTagsToNote(jobId: string, req: NoteTagAddRequest): Promise<{ tags: Tag[] }> {
  return apiFetch<{ tags: Tag[] }>(`${API_BASE}/tasks/${jobId}/tags`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function removeTagFromNote(jobId: string, tagId: string): Promise<void> {
  await apiFetch(`${API_BASE}/tasks/${jobId}/tags/${tagId}`, { method: "DELETE" });
}

// --- Note folder/favorite ---

export async function moveNoteToFolder(jobId: string, req: NoteFolderUpdateRequest): Promise<void> {
  await apiFetch(`${API_BASE}/tasks/${jobId}/folder`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function toggleFavorite(jobId: string, req: FavoriteToggleRequest): Promise<void> {
  await apiFetch(`${API_BASE}/tasks/${jobId}/favorite`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

// --- Note content editing ---

export async function updateNoteContent(jobId: string, data: { markdown: string }): Promise<NoteResult> {
  return apiFetch<NoteResult>(`${API_BASE}/tasks/${jobId}/content`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

// --- Batch operations ---

export async function batchAddTag(req: BatchTagRequest): Promise<void> {
  await apiFetch(`${API_BASE}/tasks/batch/tag`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function batchMoveToFolder(req: BatchMoveRequest): Promise<void> {
  await apiFetch(`${API_BASE}/tasks/batch/move`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function batchSetFavorite(req: BatchFavoriteRequest): Promise<void> {
  await apiFetch(`${API_BASE}/tasks/batch/favorite`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function batchDelete(req: BatchDeleteRequest): Promise<{ deleted: number }> {
  return apiFetch<{ deleted: number }>(`${API_BASE}/tasks/batch/delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}
