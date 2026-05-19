# Research: WYSIWYG Markdown Editor Libraries for React

- **Query**: Best WYSIWYG Markdown editor libraries for React (2025-2026), for note-taking app with Markdown-first content model, Notion-like UX, CJK support
- **Scope**: Mixed (internal codebase analysis + external library comparison)
- **Date**: 2026-05-19

## Findings

### Current Project Context

The project currently uses **react-markdown + remark-gfm** for read-only Markdown rendering. The timestamp format is `[HH:MM:SS](#t=SECONDS)` rendered as clickable `TimestampBadge` components via react-markdown's `components` override.

| File Path | Description |
|---|---|
| `frontend/src/components/NoteView.tsx` | Current read-only Markdown renderer with TimestampBadge |
| `frontend/package.json` | Uses react@19.1.0, react-markdown@10.1.0, remark-gfm@4.0.0 |
| `.trellis/spec/frontend/component-guidelines.md` | Documents TimestampBadge pattern and react-markdown usage |

Key constraint: The app stores Markdown text (not JSON/HTML), so any editor must support **Markdown roundtrip** -- load existing `.md`, edit WYSIWYG, save back as Markdown without data loss.

---

### 1. Milkdown (ProseMirror-based, Markdown-first)

| Attribute | Detail |
|---|---|
| **GitHub** | [Milkdown/milkdown](https://github.com/Milkdown/milkdown) -- 11,485 stars |
| **npm** | `@milkdown/kit` v7.21.1, `@milkdown/react` v7.21.1 |
| **License** | MIT |
| **Last Release** | v7.21.1 (2026-05-13) -- very active |
| **Content Model** | **Markdown-first** -- uses remark/unified pipeline internally; stores/outputs Markdown natively |
| **Bundle Size** | `@milkdown/kit` 121KB unpacked; `@milkdown/react` 93KB; `@milkdown/transformer` 131KB; `@milkdown/plugin-slash` 132KB; `@milkdown/plugin-block` 175KB; `@milkdown/preset-gfm` 241KB. Total core ~700KB unpacked. |
| **React 19** | Peer deps: `react: *`, `react-dom: *` -- compatible (no version constraint) |
| **CJK/IME** | ProseMirror has native composition event handling. Only 1 closed IME issue found (#1568 -- list-item selection). No open CJK bugs. |
| **Extensibility** | Plugin-based architecture. Custom nodes via ProseMirror schema + Milkdown plugin API. Can add custom inline nodes (e.g., timestamp badges). `@milkdown/plugin-slash` and `@milkdown/plugin-block` provide Notion-like UI building blocks. |
| **GFM Support** | `@milkdown/preset-gfm` -- tables, strikethrough, task lists |
| **Notion-like UX** | `@milkdown/crepe` package provides a "Crepe editor" with Notion-like editing experience. **Caveat**: Crepe has `vue` as a dependency (v3.5.20), which adds ~200KB to bundle. This is for the Crepe UI layer, not the core editor. The core `@milkdown/kit` + `@milkdown/react` does NOT include Vue. |
| **Markdown Roundtrip** | **Excellent** -- this is Milkdown's core design principle. Uses remark/unified for parsing and serialization. Markdown is the source of truth, not ProseMirror doc. The `@milkdown/transformer` module handles conversion. |

**Key Architecture**: Milkdown treats Markdown as the primary content model. It parses Markdown via remark, edits in ProseMirror, and serializes back via remark. This means zero-loss roundtrip for standard Markdown + GFM.

**Timestamp Badge Viability**: Can define a custom ProseMirror node or mark for `[#t=SECONDS]` links, or use the link schema override approach similar to current react-markdown implementation.

---

### 2. Tiptap (ProseMirror-based, most popular)

| Attribute | Detail |
|---|---|
| **GitHub** | [ueberdosis/tiptap](https://github.com/ueberdosis/tiptap) -- 36,829 stars |
| **npm** | `@tiptap/react` v3.23.4, `@tiptap/core` v3.23.4 |
| **License** | MIT |
| **Last Release** | v3.23.4 (2026-05-13) -- very active, frequent releases |
| **Content Model** | **JSON-first** -- uses ProseMirror document (JSON) as the content model. Markdown is a secondary format. |
| **Bundle Size** | `@tiptap/react` 466KB unpacked. With `@tiptap/starter-kit` (24 extensions) adds more. Full ProseMirror stack (~200KB gzipped total). |
| **React 19** | Peer deps: `react: ^17 \|\| ^18 \|\| ^19`, `react-dom: ^17 \|\| ^18 \|\| ^19` -- **explicitly compatible** |
| **CJK/IME** | **Known issues** -- multiple open bugs: #7186 (IME in table cells leaves raw pinyin on Safari), #7271 (duplicate text with Chinese IME in headings on WebKit), #4108 (CJK last character disappears on newline), #7414 (text selection not replaced during composition), #7626 (cursor jump during IME composition in colored text). These are ProseMirror-level issues, not Tiptap-specific. |
| **Extensibility** | Excellent -- extension API is Tiptap's strength. Custom nodes, marks, plugins via `Node.create()`, `Mark.create()`. Huge ecosystem of community extensions. |
| **GFM Support** | Available via `@tiptap/extension-table`, `@tiptap/extension-task-list`, `@tiptap/extension-strike`, etc. Must install individually. |
| **Notion-like UX** | No built-in Notion-like UI. Must build slash commands, drag-handle blocks, hover toolbars from scratch, or use BlockNote which sits on top. |
| **Markdown Roundtrip** | **Problematic** -- Tiptap's `@tiptap/extension-markdown` (in pro tier) or third-party `tiptap-markdown` extension handles conversion, but it's not the primary content model. Loading Markdown -> JSON -> editing -> JSON -> Markdown can lose formatting. No built-in markdown support in the open-source version; requires pro subscription or third-party extension. |

**Critical Issue for This Project**: Tiptap's JSON content model means every save/load cycle goes through Markdown<->JSON conversion. This introduces roundtrip fidelity risk. Also, the open-source version does NOT include markdown serialization -- you need `tiptap-markdown` (third-party) or the Tiptap Pro plan.

**CJK Concern**: 5+ open IME/CJK bugs as of 2026-05. This is a significant risk for a Chinese-first note-taking app.

---

### 3. BlockNote (built on Tiptap, Notion-like UX out of box)

| Attribute | Detail |
|---|---|
| **GitHub** | [TypeCellOS/BlockNote](https://github.com/TypeCellOS/BlockNote) -- 9,716 stars |
| **npm** | `@blocknote/core` v0.51.1, `@blocknote/react` v0.51.1 |
| **License** | NOASSERTION (MPL-2.0 based on repo) |
| **Last Release** | v0.51.1 (2026-05-18) -- very active |
| **Content Model** | **Block-based JSON** -- built on Tiptap, uses block-style JSON content model. Has markdown import/export but JSON is primary. |
| **Bundle Size** | `@blocknote/core` 7.6MB unpacked (!), `@blocknote/react` 1.75MB unpacked. Very large -- includes yjs, emoji-mart, shiki, prosemirror-tables, etc. **This is the heaviest option by far.** |
| **React 19** | Peer deps: `react: ^18 \|\| ^19 \|\| >=19.0.0-rc` -- **explicitly compatible** |
| **CJK/IME** | Inherits Tiptap's ProseMirror IME issues. No specific CJK issues found in BlockNote's tracker, but the underlying Tiptap/ProseMirror layer has known problems. |
| **Extensibility** | Good -- custom block types, custom schemas, custom toolbars. But the block model is opinionated (every block has `type`, `props`, `content`). Custom inline elements like timestamp badges may be awkward in the block model. |
| **GFM Support** | Tables (recently fixed in #2720 for stable roundtrip), task lists, strikethrough supported. |
| **Notion-like UX** | **Best in class** -- this is BlockNote's primary value proposition. Slash menu, drag handles, side menu, formatting toolbar all included out of the box. Notion-like block editing is the default experience. |
| **Markdown Roundtrip** | **Improving** -- recent fix (#2720, 2026-05-07) improved round-trip stability for tables, captions, and audio. However, roundtrip is still not guaranteed lossless because the block JSON model doesn't map 1:1 to all Markdown constructs. |

**Critical Issues**: 
1. Bundle size is enormous (7.6MB + 1.75MB unpacked). This includes yjs (collaboration), emoji-mart (emoji picker), shiki (syntax highlighting) -- many features the project may not need.
2. Markdown is not the primary content model; it's a second-class export format.
3. Custom inline elements (timestamp badges) don't fit naturally in the block model -- BlockNote's custom elements are block-level, not inline-level.

---

### 4. ByteMD (Svelte-based, React wrapper available)

| Attribute | Detail |
|---|---|
| **GitHub** | [pd4d10/bytemd](https://github.com/pd4d10/bytemd) (formerly bytedance/ByteMD) -- 1,334 stars |
| **npm** | `bytemd` v1.22.0, `@bytemd/react` v1.22.0 |
| **License** | MIT |
| **Last Release** | v1.22.0 -- **stale** (last meaningful update was mid-2023; repo moved from bytedance to personal account) |
| **Content Model** | **Markdown-first** -- split-pane editor (CodeMirror on left, preview on right). Not WYSIWYG; it's a traditional split-view editor. |
| **Bundle Size** | `bytemd` 3.2MB unpacked (includes codemirror-ssr, remark/rehype pipeline, tippy.js, popper.js). `@bytemd/react` 630KB unpacked. |
| **React 19** | Peer deps: `react: *` -- compatible (no version constraint). But package hasn't been tested against React 19. |
| **CJK/IME** | CodeMirror has excellent CJK/IME support. Preview pane renders via remark, so no IME issues there. |
| **Extensibility** | Plugin system via `bytemd` plugin API. Can add remark/rehype plugins, toolbar items, custom themes. But limited to the split-pane model -- no WYSIWYG customization. |
| **GFM Support** | Via `@bytemd/plugin-gfm` |
| **Notion-like UX** | **No** -- this is a split-pane (code + preview) editor, not WYSIWYG. No slash commands, no block editing. |
| **Markdown Roundtrip** | **Perfect** -- the source is always Markdown text. No conversion needed. What you type in CodeMirror is what gets saved. |

**Critical Issue**: ByteMD is **not WYSIWYG**. It's a split-pane code editor with preview. The task explicitly requests "WYSIWYG Markdown editor" and "Notion-like editing experience." ByteMD does not meet these requirements. Additionally, the project appears to be minimally maintained (moved from ByteDance org to personal account, no recent meaningful updates).

---

### 5. Cherry Markdown (Tencent, Chinese-friendly, WYSIWYG)

| Attribute | Detail |
|---|---|
| **GitHub** | [Tencent/cherry-markdown](https://github.com/Tencent/cherry-markdown) -- 4,690 stars |
| **npm** | `cherry-markdown` v0.11.1 |
| **License** | Apache-2.0 (no explicit npm license field) |
| **Last Release** | v0.11.1 (2026-04-24) -- active |
| **Content Model** | **Markdown-first** -- designed to work with Markdown as the primary format. WYSIWYG editing that outputs Markdown. |
| **Bundle Size** | `cherry-markdown` 58.4MB unpacked (!!) -- includes jsdom, codemirror, ws, crypto-js, DOMPurify. **Extremely heavy.** |
| **React 19** | **No React integration** -- Cherry Markdown is a vanilla JS library. No official React wrapper. Would require `useRef` + `useEffect` wrapper. No peer dependency for React listed. |
| **CJK/IME** | **Best** -- built by Tencent with Chinese users as primary audience. Full CJK input support, Chinese documentation, Chinese community. Designed from the ground up for Chinese text editing. |
| **Extensibility** | Plugin system with custom syntax, toolbar, and hooks. Can register custom syntax (e.g., for timestamp badges). Has `Cherry.createSyntaxHook` API. |
| **GFM Support** | Tables, task lists, strikethrough all supported. Also supports Mermaid diagrams, math formulas, and other advanced features. |
| **Notion-like UX** | **Partial** -- WYSIWYG editing, but the UX is more traditional (toolbar-based) than Notion-like (block-based with slash commands). No built-in slash command menu or block drag handles. |
| **Markdown Roundtrip** | **Good** -- Markdown is the primary content model. Uses a custom parser (not remark/unified), but roundtrip fidelity for standard Markdown + GFM is solid. |

**Critical Issues**:
1. **58.4MB unpacked** -- by far the heaviest option. Includes server-side dependencies like `jsdom` and `ws` that shouldn't be in a browser bundle. This may be a packaging issue rather than actual browser runtime cost, but it indicates poor tree-shaking and bundling practices.
2. **No React wrapper** -- must build a custom React integration layer.
3. **Not block-based** -- while WYSIWYG, it's not the Notion-like block editing experience requested.
4. **Notion-like**: Does not provide slash commands or block drag-and-drop out of the box.

---

## Comparative Summary

| Criterion | Milkdown | Tiptap | BlockNote | ByteMD | Cherry Markdown |
|---|---|---|---|---|---|
| **Markdown-first** | YES (core design) | NO (JSON-first) | NO (block JSON) | YES (source text) | YES (core design) |
| **WYSIWYG** | YES | YES | YES | NO (split-pane) | YES |
| **Notion-like UX** | Via Crepe (caveat: Vue dep) | Must build from scratch | Best out of box | N/A | Partial (toolbar-based) |
| **Markdown Roundtrip** | Excellent | Problematic (needs 3rd-party) | Improving (recent fixes) | Perfect | Good |
| **Bundle Size (unpacked)** | ~700KB (core) | ~466KB + ProseMirror | ~9.3MB (core+react) | ~3.8MB | ~58.4MB |
| **React 19 Compat** | YES | YES (explicit) | YES (explicit) | Untested | No wrapper |
| **CJK/IME** | Good (no open bugs) | Poor (5+ open bugs) | Inherits Tiptap issues | Excellent | Best (Chinese-first) |
| **GFM** | Yes (preset-gfm) | Yes (individual exts) | Yes | Yes (plugin) | Yes |
| **Custom Timestamp Badge** | Via custom ProseMirror node | Via custom Node/Mark | Awkward (block model) | Via remark plugin | Via custom syntax hook |
| **Maturity** | High (v7, active) | Highest (v3, most popular) | High (v0.51, active) | Low (stale, moved repo) | Medium (Chinese ecosystem) |
| **License** | MIT | MIT | MPL-2.0 | MIT | Apache-2.0 |

---

## CJK/IME Input Handling: Detailed Analysis

### The Problem
CJK (Chinese/Japanese/Korean) text input uses IME (Input Method Editor) composition events. During composition, a single character is built from multiple keystrokes. ProseMirror's transaction-based model can interfere with the composition lifecycle, causing:
- Duplicate text when composition ends
- Lost characters on newline
- Raw pinyin/kana leaking into the document
- Cursor jumping during composition

### Library Status

**Tiptap/ProseMirror**: Most affected. Multiple open issues as of 2026-05. ProseMirror v1.x has known composition handling gaps, especially in Safari/WebKit. Tiptap's architecture doesn't add composition handling beyond what ProseMirror provides.

**Milkdown**: Also ProseMirror-based, but fewer reported issues. Milkdown's v7 rewrite may have addressed some composition handling. The smaller issue count could also reflect a smaller user base in CJK markets.

**BlockNote**: Inherits Tiptap's ProseMirror layer, so same underlying issues apply.

**ByteMD**: Uses CodeMirror for editing, which has mature IME handling. Not affected.

**Cherry Markdown**: Built by Tencent specifically for Chinese users. Most tested for CJK scenarios. Uses contenteditable directly (not ProseMirror), which has its own IME handling but is well-tested in this context.

---

## Timestamp Badge Extensibility: Analysis for `[HH:MM:SS](#t=SECONDS)`

The current app uses react-markdown's component override to render timestamp links as clickable badges. A WYSIWYG editor needs to:

1. **Parse** the `[text](#t=seconds)` Markdown link syntax into a special node
2. **Render** it as a styled badge in the editor (not a regular link)
3. **Allow editing** (or at minimum, not break) the badge
4. **Serialize** it back to `[HH:MM:SS](#t=SECONDS)` Markdown

### Milkdown Approach
Define a custom ProseMirror `Mark` (for inline) or `Node` (for inline node) that:
- Matches `#t=` links during Markdown parsing (via remark plugin or custom parser)
- Renders as a styled `<span>` or `<button>` in the editor
- Serializes back to the link format via custom serializer

This is well-supported in Milkdown's plugin architecture.

### Tiptap Approach
Define a custom `Mark` extension via `Mark.create()` with `parseHTML`, `renderHTML`, and `addAttributes`. The `prosemirror-markdown` or `tiptap-markdown` serializer needs custom rules for the `#t=` pattern.

### BlockNote Approach
BlockNote's block model is primarily block-level. Inline custom elements are possible but awkward. Would likely need to use a custom ProseMirror mark at the Tiptap level, bypassing BlockNote's block abstraction.

---

## External References

- [Milkdown Documentation](https://milkdown.dev/) -- official docs, plugin guide
- [Milkdown GitHub](https://github.com/Milkdown/milkdown) -- 11,485 stars, MIT license
- [Tiptap Documentation](https://tiptap.dev/) -- official docs, extensive API reference
- [Tiptap GitHub](https://github.com/ueberdosis/tiptap) -- 36,829 stars, MIT license
- [BlockNote Documentation](https://www.blocknotejs.org/) -- official docs
- [BlockNote GitHub](https://github.com/TypeCellOS/BlockNote) -- 9,716 stars, MPL-2.0
- [ByteMD GitHub](https://github.com/pd4d10/bytemd) -- 1,334 stars, MIT (stale)
- [Cherry Markdown GitHub](https://github.com/Tencent/cherry-markdown) -- 4,690 stars, Apache-2.0
- [ProseMirror IME issues](https://github.com/ProseMirror/prosemirror-view/issues?q=IME+composition) -- upstream CJK handling

### Related Specs

- `.trellis/spec/frontend/component-guidelines.md` -- Documents current TimestampBadge pattern and react-markdown usage
- `.trellis/tasks/archive/2026-05/05-17-ai/research/frontend-and-structure.md` -- Original analysis of timestamp component patterns

## Caveats / Not Found

1. **Milkdown Crepe Vue dependency**: The `@milkdown/crepe` package (which provides the Notion-like UI) has `vue` as a regular dependency (v3.5.20). This adds ~200KB+ to the bundle for a React project. Need to verify if Crepe can be used without pulling Vue into the production bundle, or if the Vue dep is only for SSR/build tooling. The core editor + slash/block plugins do NOT require Vue.

2. **Bundle size figures are unpacked size** (not gzipped). Actual network transfer sizes will be significantly smaller after gzip/brotli compression. However, the relative proportions between libraries remain meaningful.

3. **Cherry Markdown 58.4MB unpacked**: This likely includes server-side dependencies (`jsdom`, `ws`, `crypto-js`) that should not be in a browser bundle. The actual browser runtime size is probably smaller, but this indicates poor packaging practices and potential tree-shaking problems. Was not able to determine actual browser-only size.

4. **Tiptap CJK issues**: The 5+ open IME/CJK bugs on Tiptap's GitHub are concerning but may not affect all users equally. Issues are primarily in Safari/WebKit. Chrome's IME handling is generally more robust. However, for a Chinese-primary app, Safari support on macOS is important.

5. **No hands-on testing performed**: All CJK/IME assessments are based on GitHub issue reports, not actual testing. Real-world IME behavior can vary by browser, OS, and input method.

6. **BlockNote version 0.x**: While actively maintained, the 0.x version indicates the API is not yet stable and may have breaking changes.

7. **ByteMD essentially disqualified**: Not WYSIWYG, not actively maintained. Included for completeness only.
