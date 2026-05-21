# Type Safety

> Type safety patterns in this project.

---

## Type Organization

All shared types in `src/types/index.ts`:

```ts
export type TaskStage =
  | "pending"
  | "downloading"
  | "extracting_subtitles"
  | "transcribing"
  | "generating_notes"
  | "complete"
  | "failed";

export interface TaskProgress {
  stage: TaskStage;
  progress: number;
  message: string;
  result?: NoteResult;
  error?: string;
}

export interface NoteResult {
  markdown: string;
  title: string;
}
```

---

## Backend ↔ Frontend Type Sync

Manually keep TypeScript types in sync with backend Pydantic schemas (`backend/app/schemas.py`).

| Backend (Pydantic) | Frontend (TypeScript) |
|---|---|
| `TaskStage` (StrEnum) | `TaskStage` (union type) |
| `TaskProgress` (BaseModel) | `TaskProgress` (interface) |
| `NoteResponse` (BaseModel) | `NoteResult` (interface) |

| `TaskListItem.thumbnail_url` (str \| None) | `TaskItem.thumbnail_url` (string \| null) |

Future: can auto-generate from FastAPI's OpenAPI schema if sync becomes painful.

---

## Nullable Fields: `string | null` vs `?: string`

Backend Pydantic `str | None` serializes to JSON `null` (not missing key). Frontend must use `string | null`, not `?: string`:

```ts
// Wrong — field will always be present (as null), never undefined
interface TaskItem {
  thumbnail_url?: string;
}

// Correct — matches JSON null from backend
interface TaskItem {
  thumbnail_url: string | null;
}
```

**Why**: `?: string` means the field may be absent or `undefined`. But FastAPI always includes the key in JSON (value is `null`). Using `?: string` misrepresents the actual contract and can cause subtle type errors when code assumes `undefined` vs `null`.

---

## Common Patterns

### Discriminated union for task state

```ts
const stageLabels: Record<TaskStage, string> = {
  pending: "Waiting to start...",
  downloading: "Downloading video...",
  extracting_subtitles: "Extracting subtitles...",
  // ...
};
```

### API response typing

```ts
export async function fetchResult(taskId: string): Promise<NoteResult> {
  const res = await fetch(`/api/tasks/${taskId}/result`);
  if (!res.ok) throw new Error(`Failed to fetch result: ${res.status}`);
  return res.json();
}
```

---

## Forbidden Patterns

- No `any` in shared types
- No type assertions (`as`) on API responses — validate shape instead
- No implicit `any` on callback parameters — always type them explicitly
