# Directory Structure

> How frontend code is organized in this project.

---

## Directory Layout

```
frontend/
├── src/
│   ├── main.tsx              # React entry point
│   ├── App.tsx               # Root component (step flow: input → progress → note)
│   ├── index.css             # Tailwind CSS v4 base + custom theme
│   ├── vite-env.d.ts         # Vite type declarations
│   ├── components/
│   │   ├── VideoInput.tsx     # URL input + file upload (react-dropzone)
│   │   ├── ProgressBar.tsx    # SSE-driven progress display
│   │   ├── NoteView.tsx       # Markdown note renderer (react-markdown)
│   │   └── ui/               # shadcn/ui primitives (Button, Card, etc.)
│   ├── hooks/
│   │   ├── useSSE.ts         # EventSource hook for progress updates
│   │   └── useVideoUpload.ts # XHR upload hook with progress tracking
│   ├── api/
│   │   └── client.ts         # API client functions
│   ├── types/
│   │   └── index.ts          # Shared TypeScript types
│   └── lib/
│       └── utils.ts           # cn() utility (clsx + tailwind-merge)
├── public/
│   └── vite.svg
├── index.html
├── package.json
├── vite.config.ts            # Vite + React + Tailwind v4 + proxy /api → :8000
├── tsconfig.json
├── eslint.config.js
└── tailwind.config.js        # (or in vite.config.ts for v4)
```

---

## Module Organization

- **`components/`**: React components, one per file. Feature components (VideoInput, ProgressBar, NoteView) alongside shadcn/ui primitives in `ui/`.
- **`hooks/`**: Custom hooks. One hook per concern (SSE, upload). No global state hooks.
- **`api/`**: API client. Thin wrapper over fetch, returns typed responses.
- **`types/`**: TypeScript interfaces/types shared across components and hooks.
- **`lib/`**: Utility functions (cn, formatters).

---

## Naming Conventions

- Files: `PascalCase.tsx` for components, `camelCase.ts` for hooks/utilities
- Components: named exports (`export function VideoInput()`)
- Hooks: `use` prefix (`useSSE`, `useVideoUpload`)
- Types: `PascalCase` interfaces (`TaskProgress`, `NoteResult`)
- CSS: Tailwind utility classes only, no separate CSS files except `index.css`

---

## Adding a New Component

1. Create `src/components/<Name>.tsx`
2. If it uses shadcn/ui primitives, import from `@/components/ui/`
3. Import types from `@/types/`
4. Use `cn()` from `@/lib/utils` for conditional classes
