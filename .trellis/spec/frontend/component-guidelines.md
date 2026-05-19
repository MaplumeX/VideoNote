# Component Guidelines

> How components are built in this project.

---

## Component Structure

Named exports, no default exports. Props interface above the component.

```tsx
interface VideoInputProps {
  onSubmit: (data: { url?: string; file?: File }) => void;
  disabled?: boolean;
}

export function VideoInput({ onSubmit, disabled }: VideoInputProps) {
  // ...
}
```

---

## Styling Patterns

**Tailwind CSS only.** No CSS modules, no styled-components, no inline styles.

Use `cn()` for conditional class merging:

```tsx
import { cn } from "@/lib/utils";

<div className={cn("rounded-lg border p-4", isActive && "border-blue-500")} />
```

shadcn/ui components in `components/ui/` — install via CLI, don't hand-write.

---

## react-markdown with Custom Components

### Pattern: TimestampBadge for video timestamps

The LLM generates Markdown with `[HH:MM:SS](#t=SECONDS)` links. Override `a` component in react-markdown to render these as clickable badges:

```tsx
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

<Markdown
  remarkPlugins={[remarkGfm]}
  components={{
    a({ href, children }) {
      if (href?.startsWith("#t=")) {
        const seconds = parseInt(href.slice(3));
        return <TimestampBadge seconds={seconds}>{children}</TimestampBadge>;
      }
      return <a href={href}>{children}</a>;
    },
  }}
>
  {markdownContent}
</Markdown>
```

> **Warning**: Do NOT spread `...rest` from react-markdown's component props to native elements. react-markdown passes extra props (`node`, `index`, etc.) that are not valid HTML attributes and cause React warnings.

---

## Markdown Preview (NotePreview)

### Pattern: MarkdownHooks with async rehype plugins

Use `MarkdownHooks` (not `Markdown`) from react-markdown when async rehype plugins like `@shikijs/rehype` are needed. `Markdown` silently skips async rehype; `MarkdownHooks` handles them correctly.

```tsx
import { MarkdownHooks } from "react-markdown";
import rehypeShiki from "@shikijs/rehype";

<MarkdownHooks
  remarkPlugins={[remarkGfm, remarkMath]}
  rehypePlugins={[rehypeSlug, [rehypeShiki, { themes: { light: "github-light", dark: "github-dark" } }], rehypeKatex]}
  components={components}
>
  {markdown}
</MarkdownHooks>
```

**Hook ordering**: All hooks (including `useMemo` for components) must be called before any conditional returns. React's Rules of Hooks require consistent call order.

```tsx
// BAD — useMemo called after conditional return, violates Rules of Hooks
if (!markdown) return null;
const components = useMemo(() => ({...}), []);

// GOOD — all hooks before conditional logic
const components = useMemo(() => ({...}), []);
if (!markdown) return null;
```

### Shiki Dual-Theme Highlighting

Configure `@shikijs/rehype` with dual themes. CSS handles the switching via `[data-theme="dark"]`:

```css
.shiki { /* light theme colors by default */ }
[data-theme="dark"] .shiki { /* dark theme overrides */ }
```

### Mermaid Diagrams

Lazy-load mermaid via dynamic `import()` to avoid bloating the main bundle:

```tsx
const mermaid = await import("mermaid");
```

Always re-initialize `mermaid` when theme changes (call `mermaid.initialize()` with the new theme config).

---

## WYSIWYG Editor (Milkdown)

### Pattern: Milkdown v7 with ProseMirror

Milkdown is a Markdown-first WYSIWYG editor built on ProseMirror. Key APIs:

- `$node` — define custom ProseMirror node types with `parseMarkdown`/`toMarkdown` for roundtrip
- `$view` — register custom NodeView for rendering
- `$remark` — inject custom remark plugins (e.g., to transform mdast before ProseMirror parsing)
- `slashFactory` + `SlashProvider` — slash command menu triggered by `/`

```tsx
import { Editor, rootCtx, defaultValueCtx } from "@milkdown/kit/core";
import { commonmark, gfm } from "@milkdown/kit/preset";
import { Milkdown, MilkdownProvider, useEditor } from "@milkdown/react";
```

**Key convention**: Milkdown editor instances are keyed for reset. When external markdown changes (e.g., switching notes), remount via a `key` prop rather than imperatively updating the editor.

### Custom TimestampBadge Node

The video timestamp `[HH:MM:SS](#t=SECONDS)` format is handled as a custom ProseMirror inline atom node:

1. `$remark("remark-timestamp-badge")` mutates `#t=` link mdast nodes into a `timestamp-badge` type
2. `$node("timestamp-badge")` parses/serializes the custom type
3. `$view` registers a `NodeView` that renders the styled badge button

This ensures WYSIWYG editing preserves timestamp links in standard Markdown format.

---

## Table of Contents (TOC)

### Pattern: IntersectionObserver for active heading tracking

The TOC component scans the preview container for headings, tracks which is visible using `IntersectionObserver`, and provides click-to-scroll navigation.

```tsx
// Active heading tracking via IntersectionObserver
const observer = new IntersectionObserver(callback, {
  rootMargin: "-80px 0px -80% 0px",
});
```

- Use `rehype-slug` to generate heading IDs
- Use `scrollIntoView({ behavior: "smooth" })` for click navigation
- Sidebar is sticky and hidden on small screens (`hidden lg:block`)

---

## Theme System (ThemeProvider)

### Pattern: React Context for global theme

`ThemeProvider` wraps `AppLayout` and provides theme via React Context. Components consume `useTheme()` hook. No local theme toggles in individual pages.

```tsx
// AppLayout wraps children in ThemeProvider
<ThemeProvider>
  <div className="min-h-screen bg-background flex">
    {/* ... */}
  </div>
</ThemeProvider>
```

Theme state syncs to `document.documentElement.dataset.theme` and `localStorage`. Components that need theme-dependent rendering (Shiki, Mermaid) read from `useTheme()`.

For DOM-based theme reactivity (when React doesn't control the DOM), use `MutationObserver` on `document.documentElement` to detect `data-theme` attribute changes.

---

## Common Mistakes

### Don't: Call setState during render

```tsx
// BAD — causes infinite re-renders in StrictMode
function App() {
  if (progress?.stage === "complete") {
    setNoteMarkdown(progress.result); // called during render!
  }
}

// GOOD — use useEffect
useEffect(() => {
  if (progress?.stage === "complete") {
    setNoteMarkdown(progress.result);
  }
}, [progress?.stage, progress?.result]);
```

### Don't: Spread unknown props to native elements

```tsx
// BAD — react-markdown passes node, index, etc.
a({ node, href, children, ...rest }) {
  return <a href={href} {...rest}>{children}</a>; // React warning
}

// GOOD — only pass what's needed
a({ href, children }) {
  return <a href={href}>{children}</a>;
}
```
