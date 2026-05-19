# Research: Milkdown v7 Plugin Ecosystem

- **Query**: Code syntax highlighting, KaTeX/Math, Mermaid diagrams, Read-only mode in Milkdown v7
- **Scope**: External (npm registry, package source analysis)
- **Date**: 2026-05-19

## Current Project State

| Package | Installed Version |
|---|---|
| `@milkdown/kit` | ^7.21.1 |
| `@milkdown/plugin-slash` | ^7.21.1 |
| `@milkdown/preset-gfm` | ^7.21.1 |
| `@milkdown/react` | ^7.21.1 |
| `@milkdown/theme-nord` | ^7.21.1 |
| `@milkdown/transformer` | ^7.21.1 |
| `shiki` | ^4.1.0 |
| `@shikijs/rehype` | ^4.1.0 |
| `katex` | ^0.16.47 |
| `mermaid` | ^11.15.0 |
| `remark-math` | ^6.0.0 |
| `rehype-katex` | ^7.0.1 |

The project uses Milkdown v7 for the WYSIWYG editor (`NoteEditor.tsx`) and react-markdown with `@shikijs/rehype` + `rehype-katex` for the read-only preview (`NotePreview.tsx`). The goal is to unify rendering so the editor and preview share the same rendering stack.

---

## 1. Code Syntax Highlighting in Milkdown

### Option A: `@milkdown/plugin-prism` (Official, v7 compatible)

- **npm**: `@milkdown/plugin-prism@7.21.1` -- tracks @milkdown/kit version exactly
- **Dependencies**: `refractor@^5.0.0` (syntax highlighting via Refractor/Prism), `@milkdown/ctx@7.21.1`, `@milkdown/utils@7.21.1`, `@milkdown/prose@7.21.1`
- **How it works**: Uses ProseMirror `Decoration` API to add CSS classes to code block text. A `$prose` plugin watches for code_block changes and applies syntax highlighting via `refractor.highlight()`. The decorations add CSS class names (e.g., `token keyword`) to text ranges within code blocks.
- **Usage**:
  ```ts
  import { prism, prismConfig } from "@milkdown/plugin-prism";

  Editor.make()
    .use(commonmark)
    .use(prism)
    .config((ctx) => {
      ctx.set(prismConfig.key, {
        configureRefractor: (refractor) => {
          // Optional: register additional languages
          return refractor;
        },
      });
    });
  ```
- **Limitations**:
  - Only works with the default `code_block` node from `@milkdown/preset-commonmark`
  - Requires a Prism CSS theme stylesheet (e.g., `prismjs/themes/prism.css`) for the token classes to have colors
  - Highlighting is applied via ProseMirror decorations -- lightweight but does not provide a rich editing experience inside code blocks
  - `refractor` supports a limited set of languages compared to Shiki

### Option B: `@milkdown/kit/component/code-block` + `@milkdown/components` (CodeMirror-based)

- **npm**: Both are included in `@milkdown/kit@7.21.1` (re-exported from `@milkdown/components@7.21.1`)
- **How it works**: Replaces the default `code_block` node view with a **CodeMirror 6** editor. Each code block becomes a full CodeMirror instance with:
  - Language-aware syntax highlighting via `@codemirror/language-data`
  - Language picker dropdown
  - Copy button
  - Preview panel (configurable via `renderPreview` callback)
  - Lazy initialization (IntersectionObserver-based, teardown after 5s off-screen)
- **Dependencies**: `@codemirror/commands`, `@codemirror/language`, `@codemirror/language-data`, `@codemirror/state`, `@codemirror/theme-one-dark`, `@codemirror/view`, `codemirror`, `vue` (for node view rendering)
- **Usage**:
  ```ts
  import { codeBlockComponent, codeBlockConfig } from "@milkdown/kit/component/code-block";

  Editor.make()
    .use(commonmark)
    .use(codeBlockComponent)
    .config((ctx) => {
      ctx.update(codeBlockConfig.key, (prev) => ({
        ...prev,
        renderPreview: (language, content, applyPreview) => {
          // Custom preview rendering (e.g., render LaTeX via KaTeX)
          return null; // or return HTML string / HTMLElement
        },
      }));
    });
  ```
- **Key feature: `renderPreview` callback**: This is what the Crepe latex feature hooks into. When a code block has `language: "LaTeX"`, the renderPreview callback can render it with KaTeX. This same mechanism could be used for Mermaid.
- **Limitations**:
  - The component is built with **Vue** (uses `defineComponent`, `createApp`, `h` from Vue). This adds a Vue runtime dependency even in a React project.
  - Adds significant bundle size (CodeMirror + language-data + Vue)
  - The node view uses Vue's reactivity system internally

### Option C: `@milkdown/crepe` feature/code-mirror

- **npm**: `@milkdown/crepe@7.21.1`
- **How it works**: Crepe is a higher-level editor that wraps `@milkdown/kit` + `@milkdown/components`. Its `codeMirror` feature is the same CodeMirror-based code block from `@milkdown/components` but configured with sensible defaults.
- **Exports**: `@milkdown/crepe/feature/code-mirror`
- **Dependencies**: Same as Option B plus full crepe dependency tree (includes katex, remark-math, vue, etc.)
- **Limitations**: Using Crepe means adopting the entire Crepe framework. It's designed for the CrepeBuilder pattern, not for composing with a custom React setup.

### Option D: Custom `$view` + Shiki (like project's existing approach with react-markdown)

- **How it works**: Create a custom `$view` for the `code_block` node that renders the highlighted code using Shiki. This would be similar to the timestamp-badge pattern already used in `NoteEditor.tsx`.
- **Advantages**: Reuses the already-installed `shiki@^4.1.0`, consistent with the react-markdown preview rendering, no Vue dependency
- **Disadvantages**: Requires building a full NodeView, handling updates, read-only state, etc. from scratch. No built-in editing experience inside the code block.

### Recommendation Summary

| Approach | v7 Compat | Bundle | Editing UX | Vue Dep | Shiki Consistency |
|---|---|---|---|---|---|
| plugin-prism | Yes (7.21.1) | Small | Read-only decorations | No | No (uses refractor) |
| components/code-block | Yes (7.21.1) | Large | Full CodeMirror | Yes | No |
| Crepe code-mirror | Yes (7.21.1) | Largest | Full CodeMirror | Yes | No |
| Custom $view + Shiki | Manual | Medium | Read-only | No | Yes |

---

## 2. KaTeX/Math Rendering in Milkdown

### Official: `@milkdown/plugin-math` (STALE, NOT v7 compatible)

- **npm**: `@milkdown/plugin-math@7.5.9` -- **latest version is 7.5.9, last updated at v7.5.x cycle**
- **Dependencies**: `katex@^0.16.0`, `remark-math@^6.0.0`, `@milkdown/exception@7.5.9`, `@milkdown/utils@7.5.9`
- **Status**: **INCOMPATIBLE** with `@milkdown/kit@7.21.1`. The internal `@milkdown/utils` and `@milkdown/exception` versions are pinned to 7.5.9 and will not work with 7.21.1. The package has not been updated since the 7.5.x release.
- **Version history**: Only goes up to 7.5.9, while kit goes to 7.21.1. Development on this package appears abandoned.

### Recommended: `@milkdown/crepe/feature/latex` (v7 compatible, production-ready)

- **npm**: `@milkdown/crepe@7.21.1` -- export `@milkdown/crepe/feature/latex`
- **How it works** (analyzed from source code):

  1. **Block math**: Extends the existing `codeBlockSchema` (from commonmark). When a code block has `language: "LaTeX"`, the markdown serializer outputs `$$...$$` math blocks. The remark plugin `remarkMathBlockPlugin` converts `math` mdast nodes into `code` nodes with `lang: "LaTeX"`.

  2. **Inline math**: Defines a custom `math_inline` node (`$nodeSchema("math_inline", ...)`):
     - Atom, inline, draggable
     - `toDOM`: renders via `katex.render(code, dom, { throwOnError: false })`
     - `parseMarkdown`: matches `inlineMath` type (from remark-math)
     - `toMarkdown`: outputs `inlineMath`

  3. **Input rules**:
     - Inline: `$...$` input rule triggers `mathInlineInputRule`
     - Block: `$$ ` input rule creates a code block with `language: "LaTeX"`

  4. **Inline tooltip**: When selecting an inline math node, a tooltip appears with a mini ProseMirror editor for editing the LaTeX source. Uses `tooltipFactory` + `TooltipProvider` from `@milkdown/kit/plugin/tooltip`.

  5. **CodeMirror integration**: The latex feature **requires** the CodeMirror feature to be enabled (`@milkdown/crepe/feature/code-mirror`). It hooks into `codeBlockConfig.renderPreview` to render LaTeX preview via `katex.renderToString()`.

  6. **Remark plugins**: Uses `remarkMathPlugin` ($remark wrapping `remark-math`) and `remarkMathBlockPlugin` (custom visitor converting `math` mdast nodes to `code[lang=LaTeX]`).

- **Key code from Crepe latex feature**:
  ```ts
  // Inline math node schema
  const mathInlineSchema = $nodeSchema("math_inline", () => ({
    group: "inline",
    inline: true,
    draggable: true,
    atom: true,
    attrs: { value: { default: "" } },
    parseMarkdown: {
      match: (node) => node.type === "inlineMath",
      runner: (state, node, type) => {
        state.addNode(type, { value: node.value });
      },
    },
    toMarkdown: {
      match: (node) => node.type.name === "math_inline",
      runner: (state, node) => {
        state.addNode("inlineMath", undefined, node.attrs.value);
      },
    },
    // ... toDOM uses katex.render(), parseDOM uses data-type attribute
  }));

  // Block math via code block extension
  const blockLatexSchema = codeBlockSchema.extendSchema((prev) => {
    return (ctx) => {
      const baseSchema = prev(ctx);
      return {
        ...baseSchema,
        toMarkdown: {
          match: baseSchema.toMarkdown.match,
          runner: (state, node) => {
            const language = node.attrs.language ?? "";
            if (language.toLowerCase() === "latex") {
              state.addNode("math", undefined, node.content.firstChild?.text || "");
            } else {
              return baseSchema.toMarkdown.runner(state, node);
            }
          },
        },
      };
    };
  });

  // The latex feature function
  const latex = (editor, config) => {
    editor.config(crepeFeatureConfig(CrepeFeature.Latex))
      .config((ctx) => {
        // Hook into codeBlockConfig.renderPreview for LaTeX blocks
        ctx.update(codeBlockConfig.key, (prev) => ({
          ...prev,
          renderPreview: (language, content, applyPreview) => {
            if (language.toLowerCase() === "latex" && content.length > 0) {
              return renderLatex(content, config?.katexOptions);
            }
            return prev.renderPreview(language, content, applyPreview);
          },
        }));
      })
      .use(remarkMathPlugin)
      .use(remarkMathBlockPlugin)
      .use(mathInlineSchema)
      .use(inlineLatexTooltip)
      .use(mathInlineInputRule)
      .use(mathBlockInputRule)
      .use(blockLatexSchema)
      .use(toggleLatexCommand);
  };
  ```

- **Limitations**:
  - Requires CodeMirror feature (brings Vue + CodeMirror dependency)
  - Built as a Crepe feature, uses Vue for the inline tooltip component
  - The `DefineFeature` signature expects to be called with a `CrepeBuilder` editor instance

### Custom Approach: Port the Crepe latex pattern without Vue

The core logic from Crepe's latex feature can be extracted and reimplemented without the Vue dependency:

1. **Block math**: Use `$nodeSchema` to extend `codeBlockSchema` with LaTeX markdown serialization (same as Crepe)
2. **Inline math**: Use `$nodeSchema("math_inline", ...)` with `katex.render()` in `toDOM` (same as Crepe)
3. **Remark**: Use `$remark` to wrap `remark-math` (already installed) and convert math blocks to LaTeX code blocks
4. **Input rules**: Same `$inputRule` patterns
5. **Editing**: Instead of Vue tooltip, either use the `@milkdown/kit/plugin/tooltip` with a React component or skip the inline editing tooltip

This approach avoids Vue and CodeMirror dependencies while achieving the same markdown roundtrip behavior.

---

## 3. Mermaid Diagram Rendering in Milkdown

### Official: `@milkdown/plugin-diagram` (STALE, NOT v7.21.1 compatible)

- **npm**: `@milkdown/plugin-diagram@7.7.0` -- **latest version is 7.7.0, stopped updating after v7.7.0**
- **Dependencies**: `mermaid@^10.9.0`, `nanoid@^5.0.9`, `unist-util-visit@^5.0.0`, `@milkdown/exception@7.7.0`, `@milkdown/utils@7.7.0`
- **Status**: **INCOMPATIBLE** with `@milkdown/kit@7.21.1`. Same issue as plugin-math -- pinned to old internal dependencies.
- **How it works** (analyzed from source):
  1. **Custom node**: `diagramSchema` = `$nodeSchema("diagram", ...)` -- an atom block node with `value` and `identity` attrs, `content: "text*"`, `isolating: true`
  2. **Remark**: `remarkDiagramPlugin` = `$remark` that visits `code` mdast nodes with `lang === "mermaid"` and converts them to `diagram` type
  3. **Input rule**: `/^```mermaid$/` creates a diagram node
  4. **Markdown roundtrip**: `toMarkdown` outputs `` ```mermaid\n{value}\n``` ``
  5. **Rendering**: The `toDOM` creates a `div[data-type="diagram"]` with the raw code text. **No actual Mermaid rendering is built into the plugin** -- it only creates the DOM container. Rendering must be done externally (likely via a `$view` that was not included in the published code or via client-side mermaid.initialize + mermaid.run)
  6. **Mermaid init**: The plugin calls `mermaid.initialize(config)` during schema setup

- **Mermaid version mismatch**: The plugin depends on `mermaid@^10.9.0`, but the project has `mermaid@^11.15.0` installed. Mermaid v11 has API changes from v10.

### Community: `@xz-summer/milkdown-mermaid@0.1.2`

- **npm**: `@xz-summer/milkdown-mermaid@0.1.2`
- **Dependencies**: `mermaid@^11.12.2`, `codemirror-lang-mermaid@^0.5.0`
- **Peer dependencies**: `@codemirror/language@^6.0.0`, `@milkdown/kit@^7.0.0`, `@milkdown/preset-commonmark@^7.0.0`
- **Status**: Compatible with Mermaid v11 and Milkdown v7. Small community package (v0.1.2).
- **Note**: Requires `@codemirror/language` as a peer dependency, implying it may use CodeMirror for editing mermaid source code.

### Custom Approach: `$node` + `$view` + `$remark` (similar to timestamp-badge pattern)

This is the most practical approach, following the pattern already established in `NoteEditor.tsx`:

1. **Remark plugin**: A `$remark` that visits `code` mdast nodes with `lang === "mermaid"` and converts them to a custom `mermaid-diagram` type
2. **Custom node**: `$nodeSchema("mermaid-diagram", ...)` -- atom block node with `value` attr
3. **Custom view**: `$view` that renders the diagram using `mermaid.render()` or `mermaid.run()`
4. **Markdown roundtrip**: `toMarkdown` outputs `` ```mermaid\n{value}\n``` ``

Key considerations:
- Mermaid rendering is **async** (`mermaid.render()` returns a Promise). The NodeView must handle async rendering.
- Mermaid requires re-initialization when theme changes (already documented in spec: "Always re-initialize mermaid when theme changes")
- Need to handle the `identity` attribute for Mermaid's internal ID tracking (each diagram needs a unique ID)
- The project already has `mermaid@^11.15.0` installed

---

## 4. Read-only Mode in Milkdown

### Approach: `editorViewOptionsCtx` with `editable` callback

Milkdown uses ProseMirror's `EditorView` under the hood. The `editable` prop on `EditorView` controls whether the editor accepts input.

**From CrepeBuilder source code** (definitive reference):
```ts
// In constructor:
ctx.set(editorViewOptionsCtx, {
  editable: () => this.#editable,
});

// setReadonly method:
this.setReadonly = (value) => {
  this.#editable = !value;
  this.editor.action((ctx) => {
    if (this.editor.status === EditorStatus.Created) {
      const view = ctx.get(editorViewCtx);
      view.setProps({
        editable: () => !value,
      });
    }
  });
  return this;
};
```

**How to implement in the project's NoteEditor.tsx**:

```ts
import { editorViewOptionsCtx, editorViewCtx, EditorStatus } from "@milkdown/kit/core";

// Option 1: Set at editor creation time (static readonly)
useEditor((container) => {
  return Editor.make()
    .config((ctx) => {
      ctx.set(rootCtx, container);
      ctx.set(defaultValueCtx, markdown);
      ctx.set(editorViewOptionsCtx, {
        editable: () => !readOnly, // readOnly is a prop/state
      });
    })
    // ...
}, [markdown, readOnly]);

// Option 2: Toggle readonly dynamically after creation
function setReadonly(editor: Editor, readOnly: boolean) {
  editor.action((ctx) => {
    const view = ctx.get(editorViewCtx);
    view.setProps({
      editable: () => !readOnly,
    });
  });
}
```

**Key details**:
- `editorViewOptionsCtx` is of type `SliceType<Partial<EditorOptions>>` where `EditorOptions = Omit<DirectEditorProps, 'state'>`
- `DirectEditorProps` is from `prosemirror-view` and includes `editable?: (editor: EditorView) => boolean`
- When `editable()` returns `false`, ProseMirror sets `contenteditable="false"` on the editor DOM
- The `@milkdown/components` code-block component already checks `this.view.editable` to sync CodeMirror's read-only state
- The crepe latex tooltip's `shouldShow` checks `if (!view.editable) return false`

**Important**: When setting readonly via `editorViewOptionsCtx` at creation time, the value is captured once. For dynamic toggling, you must use `view.setProps()` as shown in Option 2. The `editorViewOptionsCtx` approach only applies at initial creation; subsequent calls to `ctx.set(editorViewOptionsCtx, ...)` won't retroactively update the existing EditorView.

### Effect on existing custom nodes

The `TimestampBadgeView` already sets `contentEditable = "false"` on its button element, so it works correctly in both edit and read-only modes. The `editable` flag on the view mainly affects text editing and selection behavior.

---

## Summary: Package Compatibility Matrix

| Package | Latest Version | Compatible with @milkdown/kit@7.21.1 | Notes |
|---|---|---|---|
| `@milkdown/plugin-prism` | 7.21.1 | YES | Official, actively maintained |
| `@milkdown/plugin-math` | 7.5.9 | **NO** | Abandoned, pinned to old deps |
| `@milkdown/plugin-diagram` | 7.7.0 | **NO** | Abandoned, pinned to old deps, uses mermaid v10 |
| `@milkdown/components` | 7.21.1 | YES | CodeMirror code-block, but requires Vue |
| `@milkdown/crepe` | 7.21.1 | YES | Full framework with latex + code-mirror, requires Vue |
| `@xz-summer/milkdown-mermaid` | 0.1.2 | Partially | Small community package, mermaid v11 compat |

## Key Imports from @milkdown/kit@7.21.1

The `@milkdown/kit` package re-exports everything needed:

```
@milkdown/kit/core          → Editor, rootCtx, defaultValueCtx, editorViewOptionsCtx, editorViewCtx, EditorStatus
@milkdown/kit/preset/commonmark → commonmark, codeBlockSchema
@milkdown/kit/preset/gfm    → gfm
@milkdown/kit/utils         → $nodeSchema, $command, $inputRule, $remark, $view, $prose, $ctx
@milkdown/kit/plugin/tooltip → tooltipFactory, TooltipProvider
@milkdown/kit/plugin/listener → listener, listenerCtx
@milkdown/kit/plugin/slash  → slashFactory
@milkdown/kit/component/code-block → codeBlockComponent, codeBlockConfig
@milkdown/kit/prose         → ProseMirror types (view, state, model, etc.)
```

## Caveats / Not Found

- **No official v7-compatible math or diagram plugin exists**. The last published versions (`plugin-math@7.5.9`, `plugin-diagram@7.7.0`) are stale and incompatible with the current kit.
- **@milkdown/shiki does NOT exist** on npm (404). There is no official Shiki integration for Milkdown.
- **Crepe components use Vue internally** even when consumed from React. This is a significant dependency concern. The Vue runtime adds ~30KB to the bundle.
- **Mermaid v11 API differs from v10** which `@milkdown/plugin-diagram` targets. The project has `mermaid@^11.15.0` installed, so any solution must use the v11 API.
- The `editable` read-only approach works at the ProseMirror level but custom node views must individually respect `view.editable` (the Crepe components do, the project's TimestampBadgeView already does via `contentEditable = "false"`).
- The `@milkdown/kit/component/code-block` export is the same as `@milkdown/components/code-block` -- just a re-export for convenience.
