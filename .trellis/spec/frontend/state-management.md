# State Management

> How state is managed in this project.

---

## Overview

No global state library (no Redux, Zustand, Jotai, etc.). All state is local via `useState` and `useRef`, or URL-driven via react-router.

---

## State Categories

### Local component state (`useState`)

Most state lives in the component that uses it. No lifting unless two siblings need the same data.

| Component | State | Type |
|-----------|-------|------|
| `VideoNoteApp` | `step`, `jobId`, `noteMarkdown`, `error` | string/enum |
| `VideoInput` | `url`, `tab` | string |
| `SettingsPage` | `providers`, `asrForm`, `llmForm`, `loading`, `saving`, `message` | mixed |
| `HistoryPage` | `tasks`, `loading`, `error` | list/bool |

### Module-level state (in-memory singleton)

Used only for auth tokens — no React context needed since `authFetch` reads it directly:

```ts
// auth/token.ts
let accessToken: string | null = null;

export function getAccessToken(): string | null { return accessToken; }
export function setAccessToken(token: string | null): void { accessToken = token; }
export function clearAuth(): void { accessToken = null; }
```

### App bootstrap: silent refresh

Access token is in-memory only (lost on page refresh). A `silentRefresh()` call in the `bootstrap()` function (before router creation) uses the httpOnly refresh cookie to restore the access token on app startup. Do NOT use top-level await — Vite's esbuild target (es2020) doesn't support it; wrap in an async function instead.

```ts
// main.tsx
async function bootstrap() {
  await silentRefresh();  // uses /api/auth/refresh cookie
  const router = createBrowserRouter([...]);
  createRoot(...).render(<RouterProvider router={router} />);
}
void bootstrap();
```

### URL state (`useSearchParams`)

- `?task=<job_id>` loads an existing task result on `/app`
- `?redirect=<path>` preserves post-login redirect target on `/auth/login`
- `?search=<query>&folder=<id>&tag=<id>&is_favorite=true&sort_by=created_at&sort_order=desc&view=card|list` drives HistoryPage filter/sort/view state

When a page has multiple filter dimensions, store them all in URL params so the state is shareable and survives page refresh. Use `setSearchParams(params, { replace: true })` to avoid polluting browser history on every filter change.

For search debounce: use `useRef<ReturnType<typeof setTimeout>>()` + `setTimeout(fn, 300)` — update the local input state immediately, but sync to URL params after the delay.

### Ref state (`useRef`)

Used to avoid stale closures in async callbacks:

```ts
// useSSE.ts — tracks current stage to decide if onerror is real
const stageRef = useRef<TaskStage | null>(null);
```

---

## Server State

No caching library (no React Query, SWR, etc.). Each component fetches its own data on mount:

```tsx
// SettingsPage.tsx
const loadData = useCallback(async () => {
  const [providersRes, settingsRes] = await Promise.all([
    fetchProviders(),
    fetchSettings(),
  ]);
  setProviders(providersRes);
  setAsrForm(buildConfigForm(settingsRes.asr, providersRes.asr));
  setLlmForm(buildConfigForm(settingsRes.llm, providersRes.llm));
}, [t]);

useEffect(() => { void loadData(); }, [loadData]);
```

No background revalidation — data is fetched on mount and on explicit user action (e.g., save settings triggers reload).

---

## When to Use Global State

Currently: never. The app is small enough that local state + module-level auth token covers all cases.

Add a global state library only when:
- Three or more components need the same mutable data
- Prop drilling exceeds 2 levels for a single piece of state

---

## Common Mistakes

### Don't: Use React Context for auth tokens

The `authFetch` pattern (module-level variable + 401 auto-refresh) avoids the need for an AuthContext. Don't add one — it would require wrapping the entire app in a provider for no benefit.

### Don't: Store SSE/upload state in a parent that doesn't use it

`useSSE` and `useVideoUpload` return their own state objects. Only consume them in components that render the results.

### Don't: Fetch in render body

Always use `useEffect` + `useCallback` or route `loader`/`action` for data fetching. Never call `fetch()` during component render.

### Don't: Keep selection state when the data view changes

When a list/table component tracks user selection (e.g., `selectedIds`), clear it whenever the visible items change — filter, search, or page change. Otherwise the UI shows "N selected" but no visible items are highlighted, confusing users.

```tsx
// BAD — page change keeps stale selections from previous page
const handlePageChange = (p: number) => {
  setPage(p);
  loadTasks(p);
};

// GOOD — clear selection when visible items change
const loadTasks = useCallback(async (p: number) => {
  setSelectedIds(new Set());
  // ... fetch data
}, [...]);

const handleFilterChange = (f: Filter) => {
  setSelectedIds(new Set());
  // ... apply filter
};
```
