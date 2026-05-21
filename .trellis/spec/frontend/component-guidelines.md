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

When dynamic values are needed (e.g., tag color, folder indentation depth), use **CSS custom properties** + Tailwind arbitrary value syntax instead of inline styles:

```tsx
// BAD — inline style violates "Tailwind only" rule
<span style={{ backgroundColor: tag.color }} />
<div style={{ paddingLeft: `${depth * 16 + 8}px` }} />

// GOOD — CSS variable + Tailwind arbitrary value
<span className="bg-[var(--tag-color)]" style={{ "--tag-color": tag.color } as React.CSSProperties} />
<div className="pl-[var(--depth-pad)]" style={{ "--depth-pad": `${depth * 16 + 8}px` } as React.CSSProperties} />
```

The `style` prop is used only to set the CSS variable value, not to apply the visual style directly. The `as React.CSSProperties` cast is required because custom properties aren't in the CSSProperties type.

Use `cn()` for conditional class merging:

```tsx
import { cn } from "@/lib/utils";

<div className={cn("rounded-lg border p-4", isActive && "border-blue-500")} />
```

shadcn/ui components in `components/ui/` — install via CLI, don't hand-write. Available: `Button`, `Input`, `Select`, `Card`, `Badge`, `Separator`, `DropdownMenu`, `ContextMenu`, `Sheet`, `Pagination`, `Tooltip`.

> **Warning**: This project uses **@base-ui/react** (not Radix) as the headless primitive layer for shadcn. `@base-ui` components use `render` prop instead of `asChild`. When a shadcn component needs to wrap a custom element (e.g., `TooltipTrigger` wrapping a `Button`), use `render` prop:
>
> ```tsx
> // BAD — asChild doesn't exist on @base-ui components
> <TooltipTrigger asChild><Button>...</Button></TooltipTrigger>
>
> // GOOD — use render prop with a function that receives trigger props
> <TooltipTrigger render={(props) => <Button {...props}>...</Button>} />
> ```
>
> Similarly, when installing new shadcn components via CLI, check for `asChild` usage in the generated code and replace with `render` prop where needed.

Use shadcn/ui components for all interactive elements:
- Buttons → `<Button variant="...">` (default, outline, ghost, destructive)
- Inputs → `<Input>` (replaces raw `<input>`)
- Selects → `<Select>/<SelectTrigger>/<SelectContent>/<SelectItem>` (replaces raw `<select>`)
- Cards → `<Card>/<CardHeader>/<CardTitle>/<CardContent>`
- Badges → `<Badge variant="...">` (default, secondary, destructive)

**Dark mode**: Toggle `document.documentElement.classList.toggle("dark")`. Use MutationObserver on `<html>` class attribute for reactive state.

---

## Note Rendering (Milkdown-only)

All note rendering goes through Milkdown WYSIWYG — there is no separate HTML preview pipeline. The editor IS the view. No `react-markdown`, `rehype-*`, or `shiki` dependencies.

### Pattern: Custom Milkdown node + NodeView + $remark

For content types not handled by commonmark/gfm (math, diagrams, timestamps), use this pattern:

1. `$remark` — transform mdast nodes into a custom type before ProseMirror parsing
2. `$node` — define the ProseMirror node schema with `parseMarkdown`/`toMarkdown` for roundtrip
3. `$view` — register a custom `NodeView` for DOM rendering
4. `$inputRule` — (optional) add typing shortcuts

```tsx
// Example: KaTeX inline math ($...$)
const mathInline = $node("math_inline", () => ({
  inline: true, group: "inline", atom: true,
  attrs: { value: { default: "" } },
  parseMarkdown: { match: (node) => node.type === "inlineMath", runner: ... },
  toMarkdown: { match: (node) => node.type.name === "math_inline", runner: ... },
}));

class MathInlineView implements NodeView {
  // Renders KaTeX normally, shows raw LaTeX when selected
}

const mathInlineView = $view(mathInline, () => (node, view) => new MathInlineView(node, view));
```

> **Warning**: When exporting `$remark` results for `.use()`, pass `.plugin` not the tuple: `remarkMermaidDiagramPlugin.plugin`, not `remarkMermaidDiagramPlugin`.

> **Warning**: Do NOT hijack `codeBlockSchema.extendSchema` to implement block math — it conflicts with `@milkdown/plugin-prism`. Use a standalone `$node("math_block")` instead.

### Pattern: Milkdown plugin arrays

Group related plugins into exported arrays for clean `.use()` calls:

```tsx
// milkdown-katex.ts
export const katexPlugins = [
  mathInline, mathInlineView,
  mathBlock, mathBlockView,
  mathInlineInputRule, mathBlockInputRule,
  remarkMathPlugin.plugin,
];

// NoteEditor.tsx
import { katexPlugins } from "./milkdown-katex";
// ...
.use(katexPlugins)
```

### Code Highlighting: @milkdown/plugin-prism

Use `@milkdown/plugin-prism` with `refractor` (named export, no default):

```tsx
import { prism, prismConfig } from "@milkdown/plugin-prism";
import { refractor } from "refractor";

.use(prism)
.config((ctx) => {
  ctx.set(prismConfig.key, { configureRefractor: () => refractor });
})
```

Import `prismjs/themes/prism.css` for syntax highlighting styles.

### Mermaid Diagrams

Lazy-load mermaid via dynamic `import()` to avoid bloating the main bundle:

```tsx
const mermaid = await import("mermaid");
```

Re-initialize `mermaid` when theme changes — track `lastMermaidTheme` and call `m.initialize({ theme })` when it differs from the current mode.

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

**Key convention**: Milkdown editor instances are keyed for reset. Use an explicit `resetKey` prop from the parent to control when the editor remounts — never let the editor component internally diff `markdown` to decide when to rebuild.

> **Warning**: Milkdown v7's `useEditor((container) => {...}, [deps])` — changing `deps` triggers `editor.destroy()` + full ProseMirror `EditorView` teardown + rebuild. Focus, cursor, IME state, and undo history are all lost. Do NOT put `markdown` in the deps array; use `useRef(markdown)` for `defaultValueCtx` instead. Remounting is handled by the `MilkdownProvider key={resetKey}` mechanism.

**Don't: Put `markdown` in `useEditor` deps.** The editor will rebuild on every keystroke if `markdown` changes during editing. Use `useRef` to capture the initial value:

```tsx
// BAD — markdown changes on every keystroke → editor rebuilds → focus lost
useEditor((container) => {
  return Editor.make().config((ctx) => {
    ctx.set(defaultValueCtx, markdown);
  })// ...
}, [markdown]);

// GOOD — ref only reads the value at mount time; remount via resetKey
const initialMarkdownRef = useRef(markdown);
useEditor((container) => {
  return Editor.make().config((ctx) => {
    ctx.set(defaultValueCtx, initialMarkdownRef.current);
  })// ...
}, []);
```

**Don't: Let the editor component diff markdown to trigger remount.** When `onChange` updates the parent's state, the `markdown` prop changes, and an internal diff effect would fire on every keystroke. Use `resetKey` instead:

```tsx
// BAD — internal diff triggers remount during editing
function NoteEditor({ markdown, onChange }) {
  const [editorKey, setEditorKey] = useState(0);
  const prevRef = useRef(markdown);
  useEffect(() => {
    if (markdown !== prevRef.current) {
      prevRef.current = markdown;
      setEditorKey(k => k + 1); // fires on every keystroke!
    }
  }, [markdown]);
  return <MilkdownProvider key={editorKey}>...</MilkdownProvider>;
}

// GOOD — parent explicitly controls when to remount
function NoteEditor({ markdown, onChange, resetKey }) {
  return <MilkdownProvider key={resetKey}>...</MilkdownProvider>;
}

// Parent: only increment on external changes (note switch, SSE complete)
const [resetKey, setResetKey] = useState(0);
useEffect(() => { // note switch
  setResetKey(k => k + 1);
  fetchResult(jobId).then(...);
}, [jobId]);
```

**Don't: Write save responses back to the markdown state prop.** After auto-save completes, do NOT call `setMarkdown(savedMarkdown)` — that changes the prop and triggers an editor remount mid-edit, losing cursor position and focus. Instead, track "last saved content" in a ref (`lastSavedMarkdownRef`) for dirty-state comparison. Only let the `resetKey` increment on intentional content loads (note switch, initial load).

### Custom TimestampBadge Node

The video timestamp `[HH:MM:SS](#t=SECONDS)` format is handled as a custom ProseMirror inline atom node:

1. `$remark("remark-timestamp-badge")` mutates `#t=` link mdast nodes into a `timestamp-badge` type
2. `$node("timestamp-badge")` parses/serializes the custom type
3. `$view` registers a `NodeView` that renders the styled badge button

This ensures WYSIWYG editing preserves timestamp links in standard Markdown format.

---

## Table of Contents (TOC)

### Pattern: IntersectionObserver for active heading tracking

The TOC component scans the Milkdown editor container for headings, tracks which is visible using `IntersectionObserver`, and provides click-to-scroll navigation.

```tsx
// Active heading tracking via IntersectionObserver
const observer = new IntersectionObserver(callback, {
  rootMargin: "-80px 0px -80% 0px",
});
```

- Milkdown's GFM preset generates heading IDs automatically (no `rehype-slug` needed)
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

Theme state syncs to `document.documentElement.classList` (dark class) and `localStorage`. Components that need theme-dependent rendering (Mermaid) read from `useTheme()`.

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

### Don't: Use inline styles for visual styling

```tsx
// BAD — inline style violates "Tailwind only" rule
<span style={{ backgroundColor: tag.color }} />
<div style={{ paddingLeft: `${depth * 16 + 8}px` }} />

// GOOD — CSS variable + Tailwind arbitrary value
<span className="bg-[var(--tag-color)]" style={{ "--tag-color": tag.color } as React.CSSProperties} />
<div className="pl-[var(--depth-pad)]" style={{ "--depth-pad": `${depth * 16 + 8}px` } as React.CSSProperties} />
```

The `style` prop is only used to set the CSS variable value, not to apply visual styles directly. The `as React.CSSProperties` cast is required for custom properties.
