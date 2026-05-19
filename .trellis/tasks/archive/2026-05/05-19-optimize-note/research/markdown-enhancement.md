# Research: Markdown Rendering Enhancement Plugins

- **Query**: Best rehype/remark plugins for enhancing Markdown rendering in a React app (react-markdown base, Vite CSR)
- **Scope**: Mixed (internal codebase analysis + external package research)
- **Date**: 2026-05-19

## Current Project Setup

| Item | Value |
|---|---|
| Base renderer | `react-markdown@^10.1.0` |
| Current plugins | `remark-gfm@^4.0.0` |
| Build tool | Vite 6 (CSR only, no SSR) |
| Styling | Tailwind CSS 4, `prose prose-sm` class (no `@tailwindcss/typography` installed) |
| CSS variables | Already defined in `src/index.css` via `@theme` block |
| React version | 19.1.0 |
| MD component | `NoteView.tsx` — minimal setup, custom `TimestampBadge` component |

### Key Files

| File Path | Description |
|---|---|
| `frontend/src/components/NoteView.tsx` | Markdown rendering component |
| `frontend/src/pages/NoteDetailPage.tsx` | Page consuming NoteView |
| `frontend/src/index.css` | Global styles + CSS variable definitions |
| `frontend/package.json` | Dependencies |

---

## 1. Code Syntax Highlighting

### Comparison Table

| Plugin | Version | Last Updated | Unpacked Size | Dependencies | Peer Deps | CSR Compatible |
|---|---|---|---|---|---|---|
| `rehype-highlight` | 7.0.2 | 2025-02-03 | ~26 KB | `lowlight`, `highlight.js` (~5.4 MB full, tree-shakeable to ~200-400 KB for subset) | None | Yes |
| `rehype-pretty-code` | 0.14.3 | 2026-03-03 | ~29 KB | None (light) | `shiki@^1 \|\| ^2 \|\| ^3 \|\| ^4` | Yes |
| `@shikijs/rehype` | 4.0.2 | 2026-03-09 | ~11 KB | `shiki@4.0.2` (bundled) | None | Yes |
| `shiki-twoslash` | 3.1.2 | — | ~342 KB | `shiki@0.10.1` (outdated), `@typescript/twoslash` | None | Yes but heavy |

### Detailed Analysis

#### `rehype-highlight`
- **How it works**: Uses `lowlight` (highlight.js virtual DOM wrapper) to add syntax classes to code blocks
- **Pros**: No peer deps, simple setup, highlight.js has 190+ languages, well-established
- **Cons**: Output is CSS class-based (requires loading a highlight.js theme CSS), highlight.js full bundle is large
- **CSR**: Fully compatible, no server APIs needed
- **Fallback**: If language is unrecognized, outputs plain text with no classes
- **Bundle impact**: With `highlight.js/lib/core` + selected languages: ~50-100 KB gzipped. Full bundle: ~5.4 MB unpacked
- **Maintenance**: Last updated 2025-02, part of unifiedjs ecosystem

#### `rehype-pretty-code`
- **How it works**: Delegates to Shiki for tokenization, outputs inline styles or CSS classes per token line
- **Pros**: Shiki uses VS Code TextMate grammars (more accurate highlighting), supports line highlighting/line numbers natively, line-level CSS class output
- **Cons**: Requires shiki as peer dep (shiki 4 is ~603 KB unpacked, heavy), more complex config
- **CSR**: Compatible but shiki needs to load WASM (oniguruma engine) at runtime. Shiki 4 also has a JS engine (`@shikijs/engine-javascript`) that avoids WASM
- **Fallback**: Falls back to unhighlighted code if shiki fails to load
- **Bundle impact**: shiki core ~600 KB unpacked, ~150-200 KB gzipped with themes/grammars. Can be reduced with lazy loading
- **Maintenance**: Actively maintained (2026-03), by Shiki team

#### `@shikijs/rehype`
- **How it works**: Official Shiki rehype plugin (shiki v4). Direct integration, latest shiki version bundled
- **Pros**: Official, always synced with latest shiki, simpler than rehype-pretty-code, supports dual themes (light/dark)
- **Cons**: Same shiki bundle size concern
- **CSR**: Same as rehype-pretty-code. WASM or JS engine required at runtime
- **Fallback**: Same as rehype-pretty-code
- **Bundle impact**: Same shiki core cost. Plugin itself is only ~11 KB
- **Maintenance**: Most actively maintained (2026-03-09), official Shiki package

#### `shiki-twoslash`
- **How it works**: TypeScript-focused syntax highlighting with hover types, error checking
- **Pros**: Rich TypeScript developer experience (hover types, errors)
- **Cons**: Very heavy, pins to outdated shiki 0.10.1, designed for documentation sites, overkill for note-taking
- **CSR**: Works but heavy
- **Bundle impact**: ~342 KB + old shiki
- **Recommendation**: Not suitable for this use case

### Theme Support for Code Highlighting

- `rehype-highlight`: Uses highlight.js themes (CSS files, e.g., `github.css`, `monokai.css`). Can switch via CSS class on parent element
- `rehype-pretty-code` / `@shikijs/rehype`: Shiki themes are built-in JSON, can be swapped at runtime. Supports **dual themes** (light + dark simultaneously via CSS variables), which is ideal for dark/light toggle

---

## 2. Table of Contents (TOC)

### Comparison Table

| Plugin | Version | Last Updated | Size | Dependencies |
|---|---|---|---|---|
| `remark-toc` | 9.0.0 | 2023-09-20 | ~19 KB | `mdast-util-toc` |
| Custom heading extraction | — | — | ~0 KB | None |

### Detailed Analysis

#### `remark-toc`
- **How it works**: Inserts a TOC section into the markdown AST at a marker (e.g., `## TOC` or `{{TOC}}`)
- **Pros**: Standardized, configurable (max depth, tight, etc.), generates proper list structure
- **Cons**: Requires a marker in the markdown content (invasive), last updated 2023-09 (old), mainly designed for document-style markdown where you control the content
- **CSR**: Fully compatible
- **Fallback**: If no marker found, does nothing

#### Custom Heading Extraction
- **How it works**: Walk the AST after rendering, extract headings, build TOC component separately
- **Implementation options**:
  1. Use `rehype-slug` (v6.0.0) to add IDs to headings, then extract headings from the rendered DOM or AST
  2. Use `remark` plugin to extract headings into a separate data structure
  3. Parse headings from raw markdown string before rendering
- **Pros**: Non-invasive (no markdown marker needed), more flexible UI control, TOC can be a sidebar/floating component
- **Cons**: Requires custom code
- **CSR**: Fully compatible
- **Fallback**: Graceful — just show empty TOC if no headings

### For this project
Since the app renders user-generated video notes (not documentation), custom extraction with `rehype-slug` + `rehype-autolink-headings` (v7.1.0) is more appropriate. The TOC can be a separate component.

---

## 3. KaTeX Math Rendering

### Comparison Table

| Plugin | Version | Last Updated | Size | Role |
|---|---|---|---|---|
| `remark-math` | 6.0.0 | 2023-09-19 | ~13 KB | Parser (markdown AST) |
| `rehype-katex` | 7.0.1 | 2024-08-19 | ~16 KB | Renderer (HTML output) |
| `katex` (core) | — | — | ~4 MB unpacked | Rendering engine |

### How They Work Together
These two plugins form a pipeline — they are NOT alternatives:
1. `remark-math` parses `$...$` (inline) and `$$...$$` (block) math syntax into math AST nodes
2. `rehype-katex` transforms those math AST nodes into KaTeX-rendered HTML

You need **both** for math support.

### Detailed Analysis

#### `remark-math`
- **How it works**: Extends micromark with math syntax, produces `math` and `inlineMath` AST nodes
- **CSR**: Fully compatible
- **Fallback**: Unknown math syntax is left as plain text
- **Bundle impact**: ~13 KB unpacked, negligible

#### `rehype-katex`
- **How it works**: Takes math AST nodes and renders them via KaTeX into HTML with inline styles
- **CSR**: Fully compatible
- **Fallback**: If KaTeX fails to render a formula, it shows the raw LaTeX with an error message
- **Bundle impact**: ~16 KB plugin + ~4 MB KaTeX core (but ~200-300 KB gzipped). KaTeX CSS (~27 KB) must also be loaded
- **CSS requirement**: Must import `katex/dist/katex.min.css` for proper rendering

### Alternative: MathJax
- Heavier, slower, more feature-complete
- Not a remark/rehype plugin — requires custom integration
- Not recommended for this use case

---

## 4. Mermaid Diagrams

### Comparison Table

| Plugin | Version | Last Updated | Size | CSR Compatible |
|---|---|---|---|---|
| `rehype-mermaid` | 3.0.0 | 2024-10-08 | ~45 KB | **No** (requires Playwright) |
| Custom mermaid integration | — | — | — | Yes |

### Critical Finding: `rehype-mermaid` is NOT suitable for CSR

`rehype-mermaid` depends on `mermaid-isomorphic` which uses **Playwright** (headless browser) to render diagrams server-side. It has `playwright` as a peer dependency. This is designed for SSG/SSR pipelines, NOT for client-side rendering.

### Recommended Approach: Custom Client-Side Mermaid

For a CSR-only Vite app, the correct approach is:

1. **Parse phase**: Use a custom remark/rehype plugin to identify ````mermaid` code blocks
2. **Render phase**: Use the `mermaid` npm package (v11.15.0) directly in the browser
3. **Integration pattern**:
   - Custom `components` prop on `react-markdown` to override the `code` component
   - When `className` is `language-mermaid`, render a `MermaidDiagram` component instead
   - The `MermaidDiagram` component calls `mermaid.render()` on mount

**Example pattern** (for reference, not implementation):
```tsx
// In react-markdown components override:
code({ className, children }) {
  if (className === 'language-mermaid') {
    return <MermaidDiagram code={String(children)} />;
  }
  // ... normal code rendering
}

// MermaidDiagram component:
// useEffect(() => { mermaid.render(id, code) }, [code])
```

### Mermaid Bundle Impact
- `mermaid` core: ~76 MB unpacked, ~2-3 MB gzipped — **very heavy**
- Consider lazy-loading: `const mermaid = await import('mermaid')` only when a mermaid code block is detected
- Alternative: Use a CDN-hosted mermaid and load via script tag

### Fallback Behavior
- If mermaid fails to parse/render a diagram, `mermaid.render()` throws — catch and show raw code with error message
- If mermaid JS fails to load, fall back to showing the raw mermaid code block

---

## 5. Custom Dark/Light Themes

### Current Project State
The project already uses CSS variables via Tailwind's `@theme` block in `src/index.css`:
```css
@theme {
  --color-background: #ffffff;
  --color-foreground: #0a0a0a;
  --color-border: #e5e5e5;
  --color-primary: #2563eb;
  --color-accent: #f0f9ff;
  /* etc. */
}
```

### Theme Implementation Approaches

#### Approach A: CSS Variables + `data-theme` attribute
1. Define two sets of CSS variables under `[data-theme="light"]` and `[data-theme="dark"]`
2. Toggle by setting `document.documentElement.dataset.theme`
3. All markdown components reference these variables
4. `prose` classes (Tailwind Typography) support dark mode via `dark:prose-invert`

#### Approach B: Shiki Dual Themes (for code highlighting)
- `rehype-pretty-code` and `@shikijs/rehype` support dual themes natively
- Generates both light and dark token colors, uses CSS variables to toggle
- Example config: `themes: { light: 'github-light', dark: 'github-dark' }`
- Output uses `.shiki` class with `--shiki-light` and `--shiki-dark` CSS custom properties

#### Approach C: KaTeX Theme
- KaTeX renders with inline styles — math text color follows the parent element's `color`
- No special dark mode handling needed if parent element's color is set via CSS variable

#### Approach D: Mermaid Theme
- Mermaid supports `theme` config: `'default'`, `'dark'`, `'forest'`, `'neutral'`
- Set via `mermaid.initialize({ theme: currentTheme })`
- Must re-render diagrams on theme change

### Tailwind Typography (`@tailwindcss/typography`)
- Currently NOT installed (the `prose` class is used but may not be fully functional without the plugin)
- Version available: 0.5.19
- Provides `prose`, `prose-sm`, `dark:prose-invert` classes
- **Important**: For Tailwind CSS 4, `@tailwindcss/typography` v1.0+ may be needed. The v0.5.x is for Tailwind 3. Need to verify compatibility.

---

## 6. Unified Solutions

### MDX / next-mdx-remote
- `mdx` (core): v0.3.1 — this is the old v0, not the current `@mdx-js/mdx`
- `next-mdx-remote`: v6.0.0 — **Next.js specific**, requires server-side compilation
- `@mdx-js/react`: v3.1.1 — React runtime for MDX
- `@next/mdx`: v16.2.6 — Next.js specific

**Verdict**: MDX is not suitable for this project. MDX requires compilation step (JSX in markdown), which is designed for static content or server-compiled content. This app renders dynamic user-generated markdown at runtime. `react-markdown` + plugins is the correct approach.

### No Single Unified Plugin Bundle Found
There is no single npm package that bundles code highlighting + math + mermaid + TOC. The standard approach in the unified/remark/rehype ecosystem is to compose individual plugins.

---

## Summary: Recommended Plugin Stack

| Feature | Plugin | Bundle Impact (gzipped) | Notes |
|---|---|---|---|
| Code highlighting | `@shikijs/rehype` | ~150-200 KB (shiki) | Dual theme support, most maintained |
| Code highlighting (lighter) | `rehype-highlight` | ~50-100 KB (subset) | Simpler, highlight.js CSS themes |
| TOC | `rehype-slug` + custom | ~5 KB | Non-invasive, separate component |
| Math | `remark-math` + `rehype-katex` | ~200-300 KB (katex) | Must import katex.min.css |
| Mermaid | Custom component + `mermaid` (lazy) | ~2-3 MB (lazy-loaded) | Not rehype-mermaid (SSR-only) |
| Heading anchors | `rehype-autolink-headings` | ~5 KB | Works with rehype-slug |

## Caveats / Not Found

1. **`@tailwindcss/typography` compatibility with Tailwind 4**: Need to verify. The `prose` class is used in NoteView.tsx but the plugin may not be installed or compatible. Tailwind 4 uses CSS-first config.
2. **Shiki WASM loading in Vite**: Shiki's oniguruma engine requires WASM. Vite handles WASM well, but the JS engine (`@shikijs/engine-javascript`) is an alternative that avoids WASM entirely.
3. **`rehype-mermaid` is SSR-only**: The npm page and peer dependencies confirm Playwright requirement. Not viable for CSR.
4. **Mermaid lazy loading**: Critical for bundle size. Should only load when a mermaid code block is detected in content.
5. **remark-math / rehype-katex last updated 2023/2024**: Still functional but not recently updated. No actively maintained alternatives exist.
6. **react-markdown v10 compatibility**: All plugins listed are compatible with unified v11+ ecosystem which react-markdown v10 uses.
