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
