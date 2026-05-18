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

### URL state (`useSearchParams`)

- `?task=<job_id>` loads an existing task result on `/app`
- `?redirect=<path>` preserves post-login redirect target on `/auth/login`

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
