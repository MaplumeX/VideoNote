# Directory Structure

> How frontend code is organized in this project.

---

## Directory Layout

```
frontend/
├── src/
│   ├── main.tsx              # React entry point, router config
│   ├── App.tsx               # VideoNoteApp — step flow: input → progress → result
│   ├── index.css             # Tailwind CSS v4 base + custom theme
│   ├── vite-env.d.ts         # Vite type declarations
│   ├── components/
│   │   ├── AppLayout.tsx     # Header + outlet layout, auth loader
│   │   ├── VideoInput.tsx    # URL input + file upload (react-dropzone)
│   │   ├── ProgressBar.tsx   # SSE-driven progress display
│   │   ├── NoteView.tsx      # Markdown note renderer (react-markdown)
│   │   └── ui/               # shadcn/ui primitives (empty, reserved)
│   ├── hooks/
│   │   ├── useSSE.ts         # SSE hook for progress updates
│   │   └── useVideoUpload.ts # XHR upload hook with progress tracking
│   ├── pages/
│   │   ├── LoginPage.tsx     # Auth login form + action
│   │   ├── RegisterPage.tsx  # Auth register form + action
│   │   ├── HistoryPage.tsx   # Task history list
│   │   └── SettingsPage.tsx  # ASR/LLM provider + model settings
│   ├── api/
│   │   └── client.ts        # API client functions (typed, uses authFetch)
│   ├── auth/
│   │   ├── api.ts            # authFetch with 401 auto-refresh
│   │   └── token.ts          # In-memory access token storage
│   ├── i18n/
│   │   ├── index.ts          # i18next config (en + zh-CN)
│   │   └── locales/
│   │       ├── en.json       # English translations
│   │       └── zh-CN.json    # Chinese translations
│   ├── types/
│   │   └── index.ts          # Shared TypeScript types
│   └── lib/
│       └── utils.ts          # cn() utility (clsx + tailwind-merge)
├── public/
│   └── vite.svg
├── index.html
├── package.json
├── vite.config.ts            # Vite + React + Tailwind v4 + proxy /api → :8000
├── tsconfig.json
└── eslint.config.js
```

---

## Module Organization

- **`components/`**: React components, one per file. Feature components alongside shadcn/ui primitives in `ui/`. Layout component (`AppLayout`) provides header + `<Outlet>`.
- **`pages/`**: Route-level page components. Auth pages include route `action` functions for form handling.
- **`hooks/`**: Custom hooks. One hook per concern (SSE, upload). No global state hooks.
- **`auth/`**: Auth infrastructure. `token.ts` stores access token in memory; `api.ts` provides `authFetch` with automatic 401 refresh.
- **`api/`**: API client. Thin typed wrapper over `authFetch`, returns typed responses.
- **`types/`**: TypeScript interfaces/types shared across components and hooks.
- **`i18n/`**: i18next configuration and locale JSON files. Currently supports `en` and `zh-CN`.
- **`lib/`**: Utility functions (cn, formatters).

---

## Naming Conventions

- Files: `PascalCase.tsx` for components/pages, `camelCase.ts` for hooks/utilities
- Components: named exports (`export function VideoInput()`)
- Pages: named exports, action functions exported alongside (`export async function loginAction()`)
- Hooks: `use` prefix (`useSSE`, `useVideoUpload`)
- Types: `PascalCase` interfaces (`TaskProgress`, `NoteResult`)
- CSS: Tailwind utility classes only, no separate CSS files except `index.css`

---

## Adding a New Page

1. Create `src/pages/<Name>Page.tsx` with named export
2. Add route in `src/main.tsx` (under `/app` children for auth-protected, or top-level for public)
3. Add nav link in `AppLayout.tsx` if needed
4. Add i18n keys to both `en.json` and `zh-CN.json`
