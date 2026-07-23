# Hook Guidelines

> How hooks are used in this project.

---

## Custom Hook Patterns

### Theme Hook (useTheme)

React Context-based theme management. `ThemeProvider` wraps `AppLayout`; components consume via `useTheme()`.

**Pattern**: Context + `dataset.theme` sync + `localStorage` persistence.

```tsx
const ThemeContext = createContext<{ theme: Theme; toggleTheme: () => void }>({
  theme: "light",
  toggleTheme: () => {},
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);
  const toggleTheme = useCallback(() => {
    setTheme((t) => (t === "light" ? "dark" : "light"));
  }, []);
  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
```

**File naming**: If the hook file contains JSX (e.g., `ThemeProvider`), use `.tsx` not `.ts`.

---

### SSE Hook (useSSE)

Consumes Server-Sent Events for real-time task progress via manual `ReadableStream` parsing (not `EventSource`, which doesn't support auth headers).

**Key gotcha**: `sse-starlette` uses `\r\n` as the default line separator. When parsing SSE with `buffer.split("\n")`, empty event-boundary lines become `"\r"` instead of `""`. Always use `line.trim() === ""` to detect event boundaries, not `line === ""`.

**Key gotcha**: EventSource callbacks capture stale closures. Use a ref to track the latest state.

```tsx
export function useSSE(url: string | null) {
  const [progress, setProgress] = useState<TaskProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const stageRef = useRef<string | null>(null);

  useEffect(() => {
    if (!url) return;
    const source = new EventSource(url);

    source.addEventListener("progress", (e) => {
      const data = JSON.parse(e.data);
      stageRef.current = data.stage;
      setProgress(data);
    });

    source.addEventListener("complete", (e) => {
      setProgress(JSON.parse(e.data));
      source.close();
    });

    source.onerror = () => {
      if (stageRef.current !== "complete") {
        setError("Connection lost. Task may still be processing.");
      }
      source.close();
    };

    return () => source.close();
  }, [url]);

  return { progress, error };
}
```

### Upload Hook (useVideoUpload)

Uploads files via XHR (not fetch) for progress tracking.

**Why XHR, not fetch**: The Fetch API does not support upload progress events. XHR's `upload.onprogress` is the only standard way.

```tsx
export function useVideoUpload() {
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);

  const upload = useCallback(async (file: File): Promise<string> => {
    setUploading(true);
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const formData = new FormData();
      formData.append("video", file);

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) setProgress((e.loaded / e.total) * 100);
      };

      xhr.onload = () => {
        const { task_id } = JSON.parse(xhr.responseText);
        resolve(task_id);
      };
      xhr.onerror = () => reject(new Error("Upload failed"));

      xhr.open("POST", "/api/upload");
      xhr.send(formData);
    });
  }, []);

  return { upload, progress, uploading };
}
```

### Confirm Hook (useConfirm)

Promise-based confirmation dialog. `ConfirmProvider` wraps `AppLayout`; components consume via `useConfirm()`.

**Pattern**: Context + `resolveRef` to prevent double-resolve when `@base-ui/react` Close fires both `onClick` and `onOpenChange`.

```tsx
interface ConfirmState {
  title: string;
  description?: string;
  destructive?: boolean;
  resolve: (value: boolean) => void;
}

const ConfirmContext = createContext<ConfirmContextValue>({
  confirm: () => Promise.resolve(false),
});

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ConfirmState | null>(null);
  const resolveRef = useRef<((value: boolean) => void) | null>(null);

  const confirm = useCallback((options) => {
    return new Promise<boolean>((resolve) => {
      resolveRef.current = resolve; // ref for double-resolve guard
      setState({ ...options, resolve });
    });
  }, []);

  const handleClose = useCallback((value: boolean) => {
    if (resolveRef.current) {  // guard: only resolve once
      resolveRef.current(value);
      resolveRef.current = null;
      setState(null);
    }
  }, []);

  return (
    <ConfirmContext.Provider value={{ confirm }}>
      {children}
      {state && (
        <AlertDialog open onOpenChange={(open) => { if (!open) handleClose(false); }}>
          {/* ... */}
          <AlertDialogAction
            variant={state.destructive ? "destructive" : "default"}
            onClick={() => handleClose(true)}
          >
            {t("confirm.ok")}
          </AlertDialogAction>
        </AlertDialog>
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  return useContext(ConfirmContext);
}
```

**Usage in components** (all handlers must be `async`):

```tsx
const { confirm } = useConfirm();

const handleDelete = async (id: string) => {
  if (!await confirm({ title: t("deleteConfirm"), destructive: true })) return;
  // proceed with delete
};
```

---

## Naming Conventions

- `use` prefix: `useSSE`, `useVideoUpload`
- Return object with named fields, not tuple
- State variables: `const [value, setValue] = useState()`

---

## Common Mistakes

### Don't: Read stale state in event callbacks

```tsx
// BAD — progress is captured at callback creation time
source.onerror = () => {
  if (progress?.stage !== "complete") { /* stale! */ }
};

// GOOD — use a ref
const stageRef = useRef<string | null>(null);
source.addEventListener("progress", (e) => {
  stageRef.current = JSON.parse(e.data).stage;
});
source.onerror = () => {
  if (stageRef.current !== "complete") { /* current value */ }
};
```

### Don't: Use fetch for file uploads with progress

```tsx
// BAD — no upload progress with fetch
await fetch("/api/upload", { method: "POST", body: formData });

// GOOD — XHR for upload progress
xhr.upload.onprogress = (e) => setProgress(e.loaded / e.total * 100);
```

### Don't: Use strict `===` for SSE empty-line detection

`sse-starlette` sends `\r\n` line endings. `split("\n")` produces `"\r"` for empty lines, not `""`.

```tsx
// BAD — never matches CRLF empty lines; events silently dropped → white screen
} else if (line === "" && currentData) {

// GOOD — handles \r\n, \n, and \r line endings
} else if (line.trim() === "" && currentData) {
```

### Don't: Let @base-ui Close double-fire resolve a Promise

`@base-ui/react` Close components (AlertDialogAction, AlertDialogCancel, SheetClose) fire `onClick` and then `onOpenChange(false)` in the same React batch. If both call a resolve function, the Promise resolves twice.

```tsx
// BAD — onClick resolves(true), then onOpenChange(false) resolves(false) again
const handleClose = useCallback((value: boolean) => {
  state.resolve(value); // called twice!
  setState(null);
}, [state]);

// GOOD — use a ref to guard, only the first call resolves
const resolveRef = useRef<((value: boolean) => void) | null>(null);
const handleClose = useCallback((value: boolean) => {
  if (resolveRef.current) {
    resolveRef.current(value);
    resolveRef.current = null;
    setState(null);
  }
}, []);
```

### Don't: Gate useEffect listener registration on a ref

Ref mutations do NOT trigger re-renders, so the effect won't re-execute and listeners won't be registered.

```tsx
// BAD — dragRef.current is set in mousedown, but ref change doesn't trigger effect re-run
const dragRef = useRef<{ startX: number } | null>(null);
useEffect(() => {
  if (!dragRef.current) return; // always null on mount → listeners never registered
  const onMove = (e: MouseEvent) => { /* ... */ };
  const onUp = () => { dragRef.current = null; };
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
  return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
}, [pos.x, pos.y]); // dependency doesn't change when dragRef is set

// GOOD — use state to drive effect re-execution
const [isDragging, setIsDragging] = useState(false);
const dragRef = useRef<{ startX: number } | null>(null);
const onDragStart = (e: React.MouseEvent) => {
  dragRef.current = { startX: e.clientX };
  setIsDragging(true); // triggers effect re-run
};
useEffect(() => {
  if (!isDragging) return;
  const onMove = (e: MouseEvent) => { /* ... */ };
  const onUp = () => { dragRef.current = null; setIsDragging(false); };
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
  return () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
}, [isDragging]); // re-runs when isDragging changes
```

---

## Authenticated Long-Running Flows

### 1. Scope / Trigger

Use this contract for authenticated requests that may refresh credentials, multipart video uploads, and SSE task progress streams.

### 2. Signatures

- `authFetch()` shares one module-level refresh promise and retries an original request at most once.
- Multipart upload sends `language` in `FormData`; an upload 401 may refresh credentials but must not automatically replay the file.
- SSE bytes pass through the incremental parser before hooks interpret progress, completion, failure, or cancellation events.
- Recovery error codes pass through the API translation layer, including codes nested in error parameters.

### 3. Contracts

- Concurrent 401 responses join the same refresh attempt; success releases all callers and failure rejects all callers.
- A late response for an old token uses a newer in-memory token when available and must not start a second refresh after authentication was cleared.
- The SSE parser retains partial fields across chunks, accepts CRLF/LF, joins multiple `data:` lines, and flushes a complete event at EOF.
- A stream disconnect checks the task REST state before bounded reconnection. Changing job id or unmounting aborts the old stream and timers.
- Upload progress is preserved, while an expired upload returns a localized retry instruction because automatic replay could duplicate work.

### 4. Validation & Error Matrix

| Condition | Required result |
| --- | --- |
| Concurrent 401, refresh succeeds | One refresh; each request retries once |
| Concurrent 401, refresh fails | Every caller rejects; auth state is cleared |
| Late old-token 401 after another refresh | Retry with current token, no extra refresh |
| SSE split at any character boundary | Each logical event dispatches exactly once |
| SSE disconnect and task completed | Fetch result and finish without reconnect |
| Upload receives 401 | Refresh session if possible, then ask user to retry upload |

### 5. Good / Base / Bad

- Good: several expired API calls recover through one refresh request.
- Base: a normal SSE event contained in one chunk behaves exactly as before.
- Bad: refresh failure or malformed/repeated disconnects terminate visibly instead of leaving a pending promise forever.

### 6. Tests Required

- Concurrent refresh success/failure, silent refresh joining, late old-token success/failure, and retry limit.
- Upload `FormData.language`, progress, and 401 behavior without automatic replay.
- SSE character-boundary splits, line endings, multiline data, EOF, terminal REST fallback, retry limit, and cleanup.
- Stable recovery-code translation in both top-level and nested API errors.

### 7. Wrong vs Correct

```ts
// WRONG — each waiter owns an unresolved callback queue on refresh failure.
if (isRefreshing) return new Promise((resolve) => waiters.push(resolve));

// CORRECT — every caller awaits the same settling promise.
refreshPromise ??= refreshAccessToken().finally(() => {
  refreshPromise = null;
});
await refreshPromise;
```

---

## Snapshot-Based Note Auto-Save

### 1. Scope / Trigger

Use this contract whenever editable note content is saved after a debounce or while another save is in flight.

### 2. Signatures

- The hook receives the current note identity/content and a save function.
- Every request captures an immutable content snapshot.
- The hook exposes dirty/saving/error state and an immediate-save action for Cmd/Ctrl+S.

### 3. Contracts

- The first edit, including a one-character edit, starts the 1.5-second debounce.
- Only one save request runs at a time.
- Success marks only the submitted snapshot as saved; edits made in flight stay dirty and trigger a catch-up save.
- Failure keeps content dirty so later edits or manual save can retry.
- A note-generation guard prevents an old note response from mutating the state of a newly opened note.
- Saving must not replace or recreate the editor document.

### 4. Validation & Error Matrix

| Condition | Required result |
| --- | --- |
| One edit then idle | Save after debounce |
| Edit during request | Old success leaves dirty; latest snapshot saves next |
| Save rejects | Dirty remains true and error is exposed |
| Cmd/Ctrl+S during debounce | Cancel timer and save current snapshot immediately |
| Navigate while save is in flight | Old response cannot update new note state |

### 5. Good / Base / Bad

- Good: rapid edits collapse into serialized snapshot saves with a final catch-up.
- Base: unchanged content produces no request.
- Bad: a stale response cannot mark newer unsaved content as clean.

### 6. Tests Required

- Single-character debounce, edit-during-save catch-up, failure retry, response ordering, manual save, and note-switch isolation.
- Use fake timers and controlled promises; assert no hidden pending promise remains.

### 7. Wrong vs Correct

```ts
// WRONG — the response marks whatever happens to be in the mutable ref as saved.
await save(contentRef.current);
savedRef.current = contentRef.current;

// CORRECT — success is tied to the exact submitted value.
const snapshot = contentRef.current;
await save(snapshot);
savedRef.current = snapshot;
if (contentRef.current !== snapshot) scheduleCatchUpSave();
```
