import katex from "katex";
import remarkMath from "remark-math";
import { $node, $view, $remark, $inputRule } from "@milkdown/kit/utils";
import { InputRule } from "@milkdown/prose/inputrules";
import type { Node as ProseNode } from "@milkdown/prose/model";
import type { NodeView, EditorView } from "@milkdown/prose/view";
import type { MarkdownNode, RemarkPluginRaw } from "@milkdown/transformer";

// ---------------------------------------------------------------------------
// Inline math node ($...$)
// ---------------------------------------------------------------------------

const mathInline = $node("math_inline", () => ({
  inline: true,
  group: "inline",
  atom: true,
  draggable: true,
  attrs: {
    value: { default: "" },
  },
  parseMarkdown: {
    match: (node: MarkdownNode) => node.type === "inlineMath",
    runner: (state, node, type) => {
      state.addNode(type, { value: (node as unknown as { value: string }).value });
    },
  },
  toMarkdown: {
    match: (node) => node.type.name === "math_inline",
    runner: (state, node) => {
      state.addNode("inlineMath", undefined, node.attrs.value as string);
    },
  },
  toDOM: (node) => {
    const dom = document.createElement("span");
    dom.setAttribute("data-type", "math_inline");
    dom.setAttribute("data-value", node.attrs.value as string);
    dom.contentEditable = "false";
    try {
      katex.render(node.attrs.value as string, dom, {
        throwOnError: false,
        displayMode: false,
      });
    } catch {
      dom.textContent = node.attrs.value as string;
    }
    return dom;
  },
  parseDOM: [
    {
      tag: 'span[data-type="math_inline"]',
      getAttrs: (dom: string | Node) => {
        if (dom instanceof HTMLElement) {
          return { value: dom.getAttribute("data-value") ?? "" };
        }
        return false;
      },
    },
  ],
}));

// ---------------------------------------------------------------------------
// Block math node ($$...$$)
// ---------------------------------------------------------------------------

const mathBlock = $node("math_block", () => ({
  group: "block",
  atom: true,
  isolating: true,
  attrs: {
    value: { default: "" },
  },
  parseMarkdown: {
    match: (node: MarkdownNode) => node.type === "math",
    runner: (state, node, type) => {
      state.addNode(type, {
        value: (node as unknown as { value: string }).value ?? "",
      });
    },
  },
  toMarkdown: {
    match: (node) => node.type.name === "math_block",
    runner: (state, node) => {
      state.addNode("math", undefined, node.attrs.value as string);
    },
  },
  toDOM: (node) => {
    const dom = document.createElement("div");
    dom.setAttribute("data-type", "math_block");
    dom.setAttribute("data-value", node.attrs.value as string);
    return dom;
  },
  parseDOM: [
    {
      tag: 'div[data-type="math_block"]',
      getAttrs: (dom: string | Node) => {
        if (dom instanceof HTMLElement) {
          return { value: dom.getAttribute("data-value") ?? "" };
        }
        return false;
      },
    },
  ],
}));

// ---------------------------------------------------------------------------
// Inline math NodeView — renders KaTeX, shows raw LaTeX when selected
// ---------------------------------------------------------------------------

class MathInlineView implements NodeView {
  dom: HTMLElement;
  private node: ProseNode;
  private editorView: EditorView;
  private rendered: HTMLElement;
  private editor: HTMLElement;

  constructor(node: ProseNode, view: EditorView) {
    this.node = node;
    this.editorView = view;

    this.dom = document.createElement("span");
    this.dom.className = "inline-flex items-center";
    this.dom.setAttribute("data-type", "math_inline");

    this.rendered = document.createElement("span");
    this.rendered.className = "katex-inline-rendered";
    this.rendered.contentEditable = "false";
    this.renderKatex(node.attrs.value as string, this.rendered, false);
    this.dom.appendChild(this.rendered);

    this.editor = document.createElement("span");
    this.editor.className =
      "katex-inline-editor border border-primary rounded px-1 text-xs font-mono text-foreground bg-background";
    this.editor.contentEditable = "true";
    this.editor.textContent = node.attrs.value as string;
    this.editor.style.display = "none";
    this.dom.appendChild(this.editor);

    this.showRendered();
  }

  private renderKatex(value: string, container: HTMLElement, displayMode: boolean) {
    try {
      katex.render(value, container, { throwOnError: false, displayMode });
    } catch {
      container.textContent = value || "(empty)";
    }
  }

  private showRendered() {
    this.rendered.style.display = "";
    this.editor.style.display = "none";
  }

  private showEditor() {
    this.rendered.style.display = "none";
    this.editor.style.display = "";
    this.editor.textContent = this.node.attrs.value as string;
    this.editor.focus();
  }

  selectNode() {
    this.dom.classList.add("ring-1", "ring-primary", "rounded");
    if (this.editorView.editable) {
      this.showEditor();
    }
  }

  deselectNode() {
    this.dom.classList.remove("ring-1", "ring-primary", "rounded");
    this.showRendered();
  }

  update(node: ProseNode): boolean {
    if (node.type.name !== "math_inline") return false;
    this.node = node;
    this.renderKatex(node.attrs.value as string, this.rendered, false);
    return true;
  }

  destroy() {
    this.dom.remove();
  }
}

const mathInlineView = $view(mathInline, () => (node: ProseNode, view: EditorView) => {
  return new MathInlineView(node, view);
});

// ---------------------------------------------------------------------------
// Block math NodeView — renders KaTeX display, shows raw LaTeX when selected
// ---------------------------------------------------------------------------

class MathBlockView implements NodeView {
  dom: HTMLElement;
  private node: ProseNode;
  private editorView: EditorView;
  private renderedEl: HTMLElement;
  private editorEl: HTMLElement;

  constructor(node: ProseNode, view: EditorView) {
    this.node = node;
    this.editorView = view;

    this.dom = document.createElement("div");
    this.dom.className = "math-block-wrapper my-4";
    this.dom.setAttribute("data-type", "math_block");

    this.renderedEl = document.createElement("div");
    this.renderedEl.className =
      "katex-block-rendered p-3 rounded bg-muted/30 overflow-x-auto";
    this.renderedEl.contentEditable = "false";
    this.renderKatex(node.attrs.value as string, this.renderedEl, true);
    this.dom.appendChild(this.renderedEl);

    this.editorEl = document.createElement("pre");
    this.editorEl.className =
      "katex-block-editor border border-primary rounded p-3 text-xs font-mono text-foreground bg-background overflow-x-auto";
    this.editorEl.contentEditable = "true";
    this.editorEl.style.display = "none";
    this.dom.appendChild(this.editorEl);

    this.showRendered();
  }

  private renderKatex(value: string, container: HTMLElement, displayMode: boolean) {
    if (!value) {
      container.textContent = "(empty math block)";
      return;
    }
    try {
      katex.render(value, container, { throwOnError: false, displayMode });
    } catch {
      container.textContent = value;
    }
  }

  private showRendered() {
    this.renderedEl.style.display = "";
    this.editorEl.style.display = "none";
  }

  private showEditor() {
    this.renderedEl.style.display = "none";
    this.editorEl.style.display = "";
    this.editorEl.textContent = this.node.attrs.value as string;
    this.editorEl.focus();
  }

  selectNode() {
    this.dom.classList.add("ring-1", "ring-primary", "rounded");
    if (this.editorView.editable) {
      this.showEditor();
    }
  }

  deselectNode() {
    this.dom.classList.remove("ring-1", "ring-primary", "rounded");
    this.showRendered();
  }

  update(node: ProseNode): boolean {
    if (node.type.name !== "math_block") return false;
    this.node = node;
    this.renderKatex(node.attrs.value as string, this.renderedEl, true);
    return true;
  }

  destroy() {
    this.dom.remove();
  }
}

const mathBlockView = $view(mathBlock, () => (node: ProseNode, view: EditorView) => {
  return new MathBlockView(node, view);
});

// ---------------------------------------------------------------------------
// Input rule: $...$ → inline math node
// ---------------------------------------------------------------------------

const mathInlineInputRule = $inputRule((ctx) => {
  const nodeType = mathInline.type(ctx);
  return new InputRule(/\$([^$]+)\$$/, (state, match, start, end) => {
    const { tr } = state;
    if (match[1]) {
      const value = match[1];
      const node = nodeType.create({ value });
      tr.replaceWith(start, end, node);
    }
    return tr;
  });
});

// ---------------------------------------------------------------------------
// Input rule: $$ → block math node
// ---------------------------------------------------------------------------

const mathBlockInputRule = $inputRule((ctx) => {
  const nodeType = mathBlock.type(ctx);
  return new InputRule(/^\$\$$/, (state, _match, start, end) => {
    const { tr } = state;
    const node = nodeType.create({ value: "" });
    return tr.replaceWith(start, end, node);
  });
});

// ---------------------------------------------------------------------------
// Remark plugin: remark-math (parses $...$ and $$...$$ from markdown)
// ---------------------------------------------------------------------------

const remarkMathPlugin = $remark(
  "remark-math-katex",
  () => remarkMath as unknown as RemarkPluginRaw<Record<string, unknown>>,
);

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

export const katexPlugins = [
  mathInline,
  mathInlineView,
  mathBlock,
  mathBlockView,
  mathInlineInputRule,
  mathBlockInputRule,
  remarkMathPlugin.plugin,
];
