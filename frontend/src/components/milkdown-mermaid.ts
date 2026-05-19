import { $node, $view, $remark } from "@milkdown/kit/utils";
import type { Node as ProseNode } from "@milkdown/prose/model";
import type { NodeView } from "@milkdown/prose/view";
import type { MarkdownNode, RemarkPluginRaw } from "@milkdown/transformer";

// ---------------------------------------------------------------------------
// Mermaid diagram node schema
// ---------------------------------------------------------------------------

const mermaidDiagram = $node("mermaid-diagram", () => ({
  group: "block",
  atom: true,
  isolating: true,
  attrs: {
    value: { default: "" },
  },
  parseMarkdown: {
    match: (node: MarkdownNode) => node.type === "mermaid-diagram",
    runner: (state, node, type) => {
      state.addNode(type, { value: (node as unknown as { value: string }).value });
    },
  },
  toMarkdown: {
    match: (node) => node.type.name === "mermaid-diagram",
    runner: (state, node) => {
      const value: string = node.attrs.value;
      state.addNode("code", undefined, value, { lang: "mermaid" });
    },
  },
  toDOM: (node: ProseNode) => {
    return ["div", { "data-type": "mermaid-diagram", "data-value": node.attrs.value }];
  },
}));

// ---------------------------------------------------------------------------
// Mermaid diagram NodeView — async SVG rendering
// ---------------------------------------------------------------------------

let mermaidInitialized = false;
let idCounter = 0;

class MermaidDiagramView implements NodeView {
  dom: HTMLElement;
  private svgContainer: HTMLElement;
  private codeContainer: HTMLElement;
  private value: string;
  private renderId = 0;

  constructor(node: ProseNode) {
    this.value = node.attrs.value;

    this.dom = document.createElement("div");
    this.dom.className = "mermaid-diagram-node my-4 rounded-lg border border-border overflow-hidden";

    this.svgContainer = document.createElement("div");
    this.svgContainer.className = "mermaid-svg p-4 bg-muted/30";

    this.codeContainer = document.createElement("pre");
    this.codeContainer.className =
      "hidden border-t border-border bg-muted/50 px-4 py-2 text-xs font-mono text-muted-foreground overflow-x-auto whitespace-pre-wrap";
    this.codeContainer.textContent = this.value;
    this.codeContainer.contentEditable = "false";

    this.dom.appendChild(this.svgContainer);
    this.dom.appendChild(this.codeContainer);

    this.renderDiagram();
  }

  update(node: ProseNode): boolean {
    if (node.type.name !== "mermaid-diagram") return false;
    const newValue: string = node.attrs.value;
    if (newValue !== this.value) {
      this.value = newValue;
      this.codeContainer.textContent = newValue;
      this.renderDiagram();
    }
    return true;
  }

  selectNode(): void {
    this.dom.classList.add("ring-2", "ring-ring");
    this.codeContainer.classList.remove("hidden");
    this.codeContainer.classList.add("block");
  }

  deselectNode(): void {
    this.dom.classList.remove("ring-2", "ring-ring");
    this.codeContainer.classList.add("hidden");
    this.codeContainer.classList.remove("block");
  }

  stopEvent(): boolean {
    return true;
  }

  destroy(): void {
    this.renderId++;
    this.dom.remove();
  }

  private async renderDiagram(): Promise<void> {
    const currentRenderId = ++this.renderId;
    const code = this.value;

    if (!code) {
      this.svgContainer.innerHTML = "";
      return;
    }

    this.svgContainer.innerHTML =
      '<div class="text-sm text-muted-foreground text-center py-2">Rendering...</div>';

    try {
      const mermaid = await import("mermaid");
      const m = mermaid.default;

      const isDark = document.documentElement.classList.contains("dark");
      const theme = isDark ? "dark" : "default";

      if (!mermaidInitialized || lastMermaidTheme !== theme) {
        m.initialize({
          startOnLoad: false,
          theme,
          securityLevel: "loose",
        });
        mermaidInitialized = true;
        lastMermaidTheme = theme;
      }

      idCounter++;
      const id = `mermaid_milkdown_${idCounter}`;

      const { svg } = await m.render(id, code);

      if (currentRenderId === this.renderId) {
        this.svgContainer.innerHTML = svg;
      }
    } catch {
      if (currentRenderId === this.renderId) {
        this.svgContainer.innerHTML = "";
        this.svgContainer.className =
          "mermaid-svg p-4 border border-destructive/30 bg-destructive/5";
        const errorEl = document.createElement("p");
        errorEl.className = "text-sm text-destructive mb-1";
        errorEl.textContent = "Mermaid rendering failed";
        this.svgContainer.appendChild(errorEl);
      }
    }
  }
}

let lastMermaidTheme: string | null = null;

const mermaidDiagramView = $view(
  mermaidDiagram,
  () => (node: ProseNode) => new MermaidDiagramView(node),
);

// ---------------------------------------------------------------------------
// Remark plugin: convert code[lang=mermaid] into mermaid-diagram mdast nodes
// ---------------------------------------------------------------------------

// eslint-disable-next-line @typescript-eslint/no-empty-object-type
interface MermaidDiagramRemarkOptions {}

const remarkMermaidDiagram: RemarkPluginRaw<MermaidDiagramRemarkOptions> =
  function remarkMermaidDiagramPlugin() {
    return (tree) => {
      const visit = (nodes: MarkdownNode[]): void => {
        for (const node of nodes) {
          if (node.children) {
            visit(node.children);
          }
          if (
            node.type === "code" &&
            (node as unknown as { lang: string }).lang === "mermaid"
          ) {
            (node as Record<string, unknown>).type = "mermaid-diagram";
            (node as Record<string, unknown>).value =
              "value" in node ? String(node.value) : "";
            node.children = [];
          }
        }
      };
      visit((tree as unknown as MarkdownNode).children ?? []);
    };
  };

const remarkMermaidDiagramPlugin = $remark(
  "remark-mermaid-diagram",
  () => remarkMermaidDiagram,
);

// ---------------------------------------------------------------------------
// Exported plugin array — use with .use() on the editor
// ---------------------------------------------------------------------------

export const mermaidPlugins = [
  mermaidDiagram,
  mermaidDiagramView,
  remarkMermaidDiagramPlugin.plugin,
];
