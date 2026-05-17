# Research: Frontend Setup for VideoNote

- **Query**: Best React setup for a video note application (Vite vs Next.js, Markdown rendering, file upload, SSE client, monorepo structure)
- **Scope**: External
- **Date**: 2026-05-17

## Findings

### 1. React Project Scaffolding: Vite vs Next.js vs CRA

| Aspect | Vite + React | Next.js | CRA (create-react-app) |
|---|---|---|---|
| **Status** | Active, recommended | Active | Deprecated (React docs removed CRA recommendation) |
| **Latest Version** | Vite 8.0.13 | Next.js 16.2.6 | CRA 5.1.0 (last release 2022) |
| **Weekly Downloads** | 126M+ | 36M+ | 71K (declining) |
| **Dev Server Start** | < 300ms (native ES modules) | ~1-3s | ~5-10s (Webpack) |
| **HMR Speed** | Near-instant | Fast (Fast Refresh) | Slow on large apps |
| **Build Tool** | Rollup (via esbuild pre-bundle) | Turbopack/SWC | Webpack + Babel |
| **SSR/SSG** | None (SPA only) | Built-in (SSR, SSG, ISR) | None |
| **API Routes** | None (separate backend) | Built-in API routes | None |
| **Config Complexity** | Minimal (vite.config.ts) | Moderate to high | Hidden/ejected |
| **TypeScript** | Official template, zero config | Built-in | Requires manual setup |
| **React Version** | React 19 (template) | React 19 | React 18 (stuck) |

**Key Analysis for VideoNote (SPA + FastAPI backend):**

- **Vite + React is the clear choice.** VideoNote is a pure SPA that talks to a separate FastAPI backend. Next.js's SSR, API routes, and file-based routing add complexity with no benefit when there is no SEO requirement (the app is behind auth/interaction, not content pages).
- Vite provides a `vite.config.ts` with a `server.proxy` option that can proxy `/api/*` to the FastAPI backend during development, eliminating CORS issues.
- CRA is effectively dead -- last release 2022, no React 19 support, Webpack-based builds are 10-20x slower than Vite.
- Next.js would be justified only if the app needed SEO (public video note pages), ISR for cached content, or server components for heavy rendering. None of these apply to the MVP.

**Vite React Template Dependencies (official):**
```
react: ^19.2.6
react-dom: ^19.2.6
@vitejs/plugin-react: ^6.0.1
vite: ^8.0.12
eslint + plugins
```

**Vite proxy config for FastAPI:**
```ts
// vite.config.ts
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    }
  }
})
```

---

### 2. Markdown Rendering in React

| Aspect | react-markdown | marked | @uiw/react-md-editor |
|---|---|---|---|
| **Latest Version** | 10.1.0 | 18.0.3 | 4.1.0 |
| **Weekly Downloads** | 22.9M | 42.7M | 600K |
| **Type** | React component (virtual DOM) | Low-level parser/renderer | Full editor + preview component |
| **Rendering Approach** | Builds React virtual DOM from AST (remark/rehype) | Returns HTML string | Wraps marked + CodeMirror |
| **Custom Components** | First-class `components` prop -- map any HTML element to a React component | `marked.use({ renderer: {...} })` -- custom renderer functions | Limited -- built on marked, exposes some override |
| **XSS Safety** | Safe by default (no dangerouslySetInnerHTML) | Unsafe by default (returns raw HTML) | Depends on marked config |
| **Plugin Ecosystem** | Full remark/rehype plugin system (100+ plugins) | Custom extensions via marked.use() | Limited to marked plugins |
| **Bundle Size** | ~30KB gzip (with unified/remark/rehype) | ~10KB gzip | ~200KB+ gzip (includes CodeMirror) |
| **GFM Support** | Via remark-gfm plugin | Built-in | Built-in |
| **Syntax Highlighting** | Via rehype-highlight or rehype-prism-plus | Manual integration | Built-in (CodeMirror) |

**Key Analysis for VideoNote (clickable timestamps in Markdown notes):**

**react-markdown is the best fit.** Here's why:

1. **Custom timestamp components:** react-markdown's `components` prop allows mapping any HTML element to a custom React component. For timestamps embedded as `[00:01:30](#t=90)` or custom syntax, you can override the `a` (link) component to detect timestamp URLs and render a clickable timestamp badge:

```tsx
<Markdown
  components={{
    a({ node, href, children, ...rest }) {
      if (href?.startsWith('#t=')) {
        const seconds = parseInt(href.slice(3));
        return <TimestampBadge seconds={seconds} onClick={() => seekTo(seconds)} />;
      }
      return <a href={href} {...rest}>{children}</a>;
    }
  }}
>
  {markdownContent}
</Markdown>
```

2. **Alternative approach with marked:** marked's `renderer` allows overriding link rendering too, but it returns an HTML string, requiring `dangerouslySetInnerHTML` to render in React. This is less safe and loses React's virtual DOM diffing benefits. Custom extensions in marked v18+ require writing tokenizer + renderer pairs:

```js
marked.use({
  extensions: [{
    name: 'timestamp',
    level: 'inline',
    start(src) { return src.indexOf('['); },
    tokenizer(src) { /* regex to match [00:01:30] */ },
    renderer(token) { return `<button onclick="seekTo(${token.seconds})">${token.text}</button>`; }
  }]
});
```

3. **@uiw/react-md-editor** is an editor component, not just a renderer. If VideoNote wants users to edit notes, it could be useful, but it's heavy (~200KB) and the editor use case is secondary. A better approach is react-markdown for display + a separate lightweight editor (or textarea with markdown preview) if editing is needed.

**Timestamp embedding conventions for Markdown:**
- Option A: Standard Markdown links -- `[00:01:30](#t=90)` -- override `a` component in react-markdown
- Option B: Custom inline syntax -- `[00:01:30]` -- requires a remark plugin or marked custom tokenizer
- Option A is simpler and more portable (the Markdown remains valid outside the app).

---

### 3. File Upload UX Patterns

| Aspect | react-dropzone | Uppy | Manual (fetch + input[type=file]) |
|---|---|---|---|
| **Latest Version** | 15.0.0 | @uppy/core 5.2.0 | N/A |
| **Weekly Downloads** | 10.9M | 909K | N/A |
| **Type** | Drag-and-drop hook only | Full upload framework | Basic |
| **Bundle Size** | ~6KB gzip (core) | ~100KB+ gzip (with plugins) | 0 |
| **Progress Indication** | None built-in (just provides drop zone) | Built-in progress bar, thumbnails | Must implement manually |
| **File Type Restriction** | `accept` prop (MIME types) | `restrictions` option | `accept` attribute |
| **Multiple Files** | Yes | Yes | Yes |
| **Previews** | No built-in (expose File objects) | Built-in thumbnail preview | Must implement |
| **Resume/Retry** | No | Via tus plugin | Must implement |
| **React Integration** | Hook-based (`useDropzone`) | Official `@uppy/react` package | Direct |
| **Upload Protocol** | None (provides File objects, you upload) | XHR upload, tus, S3, custom | fetch/XHR |
| **Companion Backend** | None | Uppy Companion (for Google Drive, etc.) | None |

**Key Analysis for VideoNote:**

**react-dropzone is the pragmatic choice for MVP.** Here's why:

1. VideoNote uploads single video files (not batch uploads of mixed types). The UX is: drop/select a video file -> show upload progress -> done. react-dropzone handles the drag-and-drop + file selection part (6KB), and progress is handled by the upload function itself.

2. Uppy is over-engineered for this case. It provides a full dashboard UI, Google Drive/Dropbox integration, image editor, tus resumable uploads -- features VideoNote doesn't need. The 100KB+ bundle and 5+ plugin imports add complexity for a single-video-upload flow.

3. **Upload progress pattern with react-dropzone + fetch:**

```tsx
function useVideoUpload() {
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);

  const upload = useCallback(async (file: File) => {
    setUploading(true);
    const formData = new FormData();
    formData.append('video', file);

    const xhr = new XMLHttpRequest();
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) setProgress(e.loaded / e.total * 100);
    };
    // Or use fetch with ReadableStream for newer browsers
    xhr.open('POST', '/api/upload');
    xhr.send(formData);
  }, []);

  return { upload, progress, uploading };
}
```

4. **XHR vs fetch for progress:** The Fetch API does not natively support upload progress (only download progress via ReadableStream). For upload progress, XHR's `upload.onprogress` event is the standard approach. This is a known limitation of fetch.

---

### 4. SSE/WebSocket Client in React

**Backend context:** FastAPI supports SSE via `sse-starlette` (v3.4.4) package. WebSocket is built into Starlette/FastAPI natively.

| Aspect | Native EventSource (SSE) | Native WebSocket | Libraries |
|---|---|---|---|
| **Browser API** | `EventSource` (built-in) | `WebSocket` (built-in) | Various |
| **Auto-reconnect** | Yes (built-in) | No (manual) | Yes |
| **Direction** | Server -> Client only | Bidirectional | Varies |
| **Proxy/Firewall** | Works over HTTP | May be blocked by proxies | Varies |
| **Content Type** | text/event-stream only | Any (binary + text) | Varies |
| **POST with body** | No (GET only with native EventSource) | N/A | fetch-based SSE allows POST |
| **Binary data** | No | Yes | Varies |

**Key Analysis for VideoNote:**

**Use native EventSource for SSE progress updates.** Here's why:

1. VideoNote's real-time need is simple: the server sends progress events (e.g., "downloading video", "transcribing", "generating notes at 45%"). This is pure Server -> Client. SSE is the correct protocol -- it's simpler than WebSocket, auto-reconnects, and works over standard HTTP.

2. FastAPI + sse-starlette makes SSE trivial on the backend:

```python
from sse_starlette.sse import EventSourceResponse

async def progress_stream(task_id: str):
    async def event_generator():
        while True:
            progress = get_task_progress(task_id)
            yield {"event": "progress", "data": json.dumps(progress)}
            if progress["status"] == "complete":
                break
            await asyncio.sleep(1)
    return EventSourceResponse(event_generator())
```

3. **React hook for SSE (no library needed):**

```tsx
function useEventSource(url: string) {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    const source = new EventSource(url);
    source.onmessage = (e) => setData(JSON.parse(e.data));
    source.onerror = () => source.close(); // EventSource auto-reconnects by default
    return () => source.close();
  }, [url]);

  return data;
}
```

4. **When WebSocket would be needed:** If VideoNote adds features like real-time collaborative editing of notes, or if the client needs to send data during the streaming connection. For MVP progress updates, SSE is sufficient.

5. **Library consideration:** The Vercel AI SDK (v6.0.184) provides `useChat` / `useCompletion` hooks that handle SSE streaming for AI responses. If VideoNote's AI note generation uses a similar streaming pattern (tokens arriving incrementally), the AI SDK's hooks could simplify the client code. However, for custom SSE events (progress percentages, status messages), native EventSource is simpler and has zero dependencies.

6. **Native EventSource limitation:** Only supports GET requests. If you need to send a request body (e.g., POST with video URL to start processing and get a stream back), use `fetch` with `ReadableStream` to consume SSE manually:

```tsx
async function startProcessing(url: string) {
  const res = await fetch('/api/process', {
    method: 'POST',
    body: JSON.stringify({ video_url: url }),
    headers: { 'Content-Type': 'application/json' },
  });
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const text = decoder.decode(value);
    // Parse SSE format: "data: {...}\n\n"
    parseSSE(text);
  }
}
```

---

### 5. Project Monorepo Structure

| Aspect | Separate Repos | Monorepo (/backend + /frontend) | Turborepo |
|---|---|---|---|
| **Complexity** | Low (each repo is simple) | Low (one repo, two dirs) | Medium (config, pipelines) |
| **Version Control** | Independent histories | Shared history | Shared history |
| **Cross-repo Changes** | Painful (2 PRs, version bumps) | Easy (one PR) | Easy (one PR) |
| **CI/CD** | Separate pipelines | Single pipeline or separate | Pipeline per package + top-level |
| **Dependency Sharing** | None | Can share .gitignore, scripts, docs | Can share packages via workspace |
| **Deployment** | Independent | Independent (deploy from subdirs) | Independent |
| **Initial Setup** | 2 repos | 1 repo | 1 repo + turbo.json |
| **Latest Version** | N/A | N/A | Turborepo 2.9.14 |
| **Best For** | Large orgs, microservices | Small teams, tight coupling | Multi-package libs, design systems |

**Key Analysis for VideoNote (2-person MVP):**

**Simple monorepo with /backend and /frontend is the right choice.** Here's why:

1. VideoNote's backend and frontend are tightly coupled -- API contract, shared types (task IDs, progress events), deployment coordination. Separate repos create friction for a 2-person team (two PRs for one API change, version sync issues).

2. Turborepo is designed for multi-package monorepos where packages have build dependencies on each other (e.g., shared UI lib + 3 apps). VideoNote has exactly 2 packages with no build-time dependency between them. Turborepo's `turbo.json` pipeline config, workspace protocol dependencies, and build caching add complexity without benefit.

3. **Recommended structure:**

```
VideoNote/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app
│   │   ├── api/             # Routes
│   │   ├── models/          # SQLAlchemy models
│   │   ├── services/        # Business logic
│   │   └── schemas/         # Pydantic schemas
│   ├── pyproject.toml       # uv/poetry
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── components/      # React components
│   │   ├── hooks/           # Custom hooks
│   │   ├── api/             # API client
│   │   ├── types/           # TypeScript types
│   │   └── App.tsx
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── .trellis/                # Project management
├── .github/                 # CI/CD workflows
├── .gitignore
└── README.md
```

4. **Shared types between backend and frontend:** Rather than a shared package, the simplest approach is to manually keep TypeScript types in `frontend/src/types/` in sync with Pydantic schemas in `backend/app/schemas/`. For MVP, tools like `pydantic-to-typescript` or OpenAPI generator can generate TypeScript types from FastAPI's auto-generated OpenAPI schema, but manual sync is acceptable for a small project.

5. **Development workflow:**
   - Terminal 1: `cd backend && uvicorn app.main:app --reload`
   - Terminal 2: `cd frontend && npm run dev`
   - Vite's `server.proxy` handles API requests during development

---

### Related Specs

| Spec File | Relevance |
|---|---|
| `.trellis/spec/frontend/directory-structure.md` | Empty -- should be filled with the monorepo layout |
| `.trellis/spec/frontend/component-guidelines.md` | Empty -- should document markdown rendering component patterns |
| `.trellis/spec/frontend/hook-guidelines.md` | Empty -- should document SSE hook pattern |
| `.trellis/spec/frontend/state-management.md` | Empty -- should document upload progress state handling |
| `.trellis/spec/frontend/type-safety.md` | Empty -- should document Pydantic <-> TypeScript type sync |

## Caveats / Not Found

- **Bundle size data:** PackagePhobia API returned errors; bundle sizes are estimated from known library characteristics rather than exact measurements. react-markdown ~30KB gzip, marked ~10KB gzip, @uiw/react-md-editor ~200KB+ gzip are well-documented figures.
- **Custom timestamp syntax in Markdown:** No existing library provides a "timestamp" Markdown extension out of the box. The recommended approach (overriding `a` component in react-markdown for `#t=` links) is a well-known pattern used by video transcript tools, but requires custom implementation.
- **SSE with fetch (POST-based):** The `ReadableStream` approach for consuming SSE via POST is well-supported in modern browsers but has no standard library. It requires manual SSE format parsing (`data: ...\n\n`).
- **No internal code found:** The project has zero source code currently -- all findings are based on external research.
