import { useEffect, useRef, useState, useCallback } from "react";
import { Editor, rootCtx, defaultValueCtx } from "@milkdown/kit/core";
import { commonmark } from "@milkdown/preset-commonmark";
import { gfm } from "@milkdown/preset-gfm";
import { nord } from "@milkdown/theme-nord";
import { Milkdown, MilkdownProvider, useEditor, useInstance } from "@milkdown/react";
import { slashFactory } from "@milkdown/plugin-slash";
import { SlashProvider } from "@milkdown/plugin-slash";
import { listener, listenerCtx } from "@milkdown/plugin-listener";
import { prism, prismConfig } from "@milkdown/plugin-prism";
import { refractor } from "refractor";
import { $node, $view, $remark } from "@milkdown/kit/utils";
import type { Node as ProseNode } from "@milkdown/prose/model";
import type { NodeView, EditorView } from "@milkdown/prose/view";
import type { MarkdownNode, RemarkPluginRaw } from "@milkdown/transformer";
import { katexPlugins } from "./milkdown-katex";
import { mermaidPlugins } from "./milkdown-mermaid";

import "@milkdown/theme-nord/style.css";
import "katex/dist/katex.min.css";
import "prismjs/themes/prism.css";

// ---------------------------------------------------------------------------
// TimestampBadge custom node
// ---------------------------------------------------------------------------

const timestampBadge = $node("timestamp-badge", () => ({
  inline: true,
  group: "inline",
  atom: true,
  marks: "",
  attrs: {
    seconds: { default: 0 },
    label: { default: "" },
  },
  parseMarkdown: {
    match: (node: MarkdownNode) =>
      node.type === "timestamp-badge",
    runner: (state, node, type) => {
      const url = (node as unknown as { url: string }).url;
      const seconds = parseInt(url.slice(3), 10);
      const value = (node as unknown as { value: string }).value;
      state.addNode(type, { seconds, label: value });
    },
  },
  toMarkdown: {
    match: (node) => node.type.name === "timestamp-badge",
    runner: (state, node) => {
      const seconds: number = node.attrs.seconds;
      const label: string = node.attrs.label;
      state.addNode("link", [{ type: "text", value: label } as MarkdownNode], undefined, { url: `#t=${seconds}` });
    },
  },
}));

// ---------------------------------------------------------------------------
// Custom node view — renders the badge as a styled button
// ---------------------------------------------------------------------------

class TimestampBadgeView implements NodeView {
  dom: HTMLElement;

  constructor(node: ProseNode) {
    const seconds: number = node.attrs.seconds;
    const label: string = node.attrs.label;
    const btn = document.createElement("button");
    btn.className =
      "inline-flex items-center rounded-md bg-accent px-1.5 py-0.5 text-xs font-mono text-primary hover:bg-primary hover:text-primary-foreground transition-colors cursor-default";
    btn.textContent = label || formatSeconds(seconds);
    btn.contentEditable = "false";
    this.dom = btn;
  }

  update(node: ProseNode): boolean {
    return node.type.name === "timestamp-badge";
  }

  destroy() {
    this.dom.remove();
  }
}

const timestampBadgeView = $view(
  timestampBadge,
  () => (node: ProseNode) => new TimestampBadgeView(node),
);

function formatSeconds(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

// ---------------------------------------------------------------------------
// Remark plugin: transform `#t=` links into `timestamp-badge` mdast nodes
// so that our custom ProseMirror node can parse them.
// ---------------------------------------------------------------------------

// eslint-disable-next-line @typescript-eslint/no-empty-object-type
interface TimestampBadgeRemarkOptions {}

const remarkTimestampBadge: RemarkPluginRaw<TimestampBadgeRemarkOptions> =
  function remarkTimestampBadgePlugin() {
    return (tree) => {
      const visit = (nodes: MarkdownNode[]): void => {
        for (const node of nodes) {
          if (node.children) {
            visit(node.children);
          }
          if (
            node.type === "link" &&
            typeof node.url === "string" &&
            node.url.startsWith("#t=")
          ) {
            const label =
              node.children?.[0] && "value" in node.children[0]
                ? String(node.children[0].value)
                : "";
            // Mutate the node into our custom type.
            // Milkdown's parser will then match it via parseMarkdown.match.
            (node as Record<string, unknown>).type = "timestamp-badge";
            (node as Record<string, unknown>).value = label;
            // Remove children so it's treated as an atomic node
            node.children = [];
            // Keep url as an attribute for the parser runner
          }
        }
      };
      visit((tree as unknown as MarkdownNode).children ?? []);
    };
  };

const remarkTimestampBadgePlugin = $remark(
  "remark-timestamp-badge",
  () => remarkTimestampBadge,
);

// ---------------------------------------------------------------------------
// Slash command items
// ---------------------------------------------------------------------------

interface SlashItem {
  label: string;
  description?: string;
  icon?: string;
  command: (view: EditorView) => void;
}

const slashItems: SlashItem[] = [
  {
    label: "Heading 1",
    description: "Large heading",
    icon: "H1",
    command: (view) => insertHeading(view, 1),
  },
  {
    label: "Heading 2",
    description: "Medium heading",
    icon: "H2",
    command: (view) => insertHeading(view, 2),
  },
  {
    label: "Heading 3",
    description: "Small heading",
    icon: "H3",
    command: (view) => insertHeading(view, 3),
  },
  {
    label: "Bullet List",
    description: "Unordered list",
    icon: "•",
    command: (view) => insertBlock(view, "bullet_list"),
  },
  {
    label: "Ordered List",
    description: "Numbered list",
    icon: "1.",
    command: (view) => insertBlock(view, "ordered_list"),
  },
  {
    label: "Task List",
    description: "Checkbox list (GFM)",
    icon: "☑",
    command: (view) => insertTaskList(view),
  },
  {
    label: "Code Block",
    description: "Code with syntax",
    icon: "</>",
    command: (view) => insertBlock(view, "code_block"),
  },
  {
    label: "Quote",
    description: "Block quote",
    icon: "\"",
    command: (view) => insertBlock(view, "blockquote"),
  },
  {
    label: "Table",
    description: "GFM table",
    icon: "⊞",
    command: (view) => insertTable(view),
  },
  {
    label: "Divider",
    description: "Horizontal rule",
    icon: "—",
    command: (view) => insertBlock(view, "hr"),
  },
];

function insertHeading(view: EditorView, level: number): void {
  const { state, dispatch } = view;
  const headingType = state.schema.nodes["heading"];
  if (!headingType) return;
  const node = headingType.createAndFill({ level });
  if (!node) return;
  dispatch(state.tr.replaceSelectionWith(node));
}

function insertBlock(view: EditorView, type: string): void {
  const { state, dispatch } = view;
  const nodeType = state.schema.nodes[type];
  if (!nodeType) return;
  const node = nodeType.createAndFill();
  if (!node) return;
  dispatch(state.tr.replaceSelectionWith(node));
}

function insertTaskList(view: EditorView): void {
  const { state, dispatch } = view;
  const taskList = state.schema.nodes["task_list"];
  const listItem = state.schema.nodes["list_item"];
  const paragraph = state.schema.nodes["paragraph"];
  if (!taskList || !listItem || !paragraph) return;
  const itemNode = listItem.createAndFill({ checked: false }, paragraph.create());
  if (!itemNode) return;
  const listNode = taskList.createAndFill(null, itemNode);
  if (!listNode) return;
  dispatch(state.tr.replaceSelectionWith(listNode));
}

function insertTable(view: EditorView): void {
  const { state, dispatch } = view;
  const table = state.schema.nodes["table"];
  const tableRow = state.schema.nodes["table_row"];
  const tableCell = state.schema.nodes["table_cell"];
  const paragraph = state.schema.nodes["paragraph"];
  if (!table || !tableRow || !tableCell || !paragraph) return;
  const cell = tableCell.createAndFill(null, paragraph.create());
  if (!cell) return;
  const row = tableRow.createAndFill(null, [cell, cell, cell]);
  if (!row) return;
  const tableNode = table.createAndFill(null, [row, row]);
  if (!tableNode) return;
  dispatch(state.tr.replaceSelectionWith(tableNode));
}

// ---------------------------------------------------------------------------
// Slash menu React component
// ---------------------------------------------------------------------------

function SlashMenu({
  items,
  onSelect,
  position,
}: {
  items: SlashItem[];
  onSelect: (item: SlashItem) => void;
  position: { top: number; left: number };
}) {
  return (
    <div
      className="fixed z-50 w-64 rounded-lg border border-border bg-background shadow-lg py-1 max-h-72 overflow-y-auto"
      style={{ top: position.top, left: position.left }}
    >
      {items.map((item) => (
        <button
          key={item.label}
          onMouseDown={(e) => {
            e.preventDefault();
            onSelect(item);
          }}
          className="w-full text-left flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-muted transition-colors"
        >
          <span className="w-8 text-center text-xs font-mono text-muted-foreground shrink-0">
            {item.icon}
          </span>
          <div>
            <div className="text-foreground">{item.label}</div>
            {item.description && (
              <div className="text-xs text-muted-foreground">{item.description}</div>
            )}
          </div>
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Slash plugin
// ---------------------------------------------------------------------------

const slash = slashFactory("NoteSlash");

// ---------------------------------------------------------------------------
// Inner editor component — lives inside MilkdownProvider
// ---------------------------------------------------------------------------

interface MilkdownEditorInnerProps {
  markdown: string;
  onChange: (markdown: string) => void;
}

function MilkdownEditorInner({ markdown, onChange }: MilkdownEditorInnerProps) {
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  // Slash menu state
  const [slashVisible, setSlashVisible] = useState(false);
  const [slashPosition, setSlashPosition] = useState({ top: 0, left: 0 });
  const [slashFilter, setSlashFilter] = useState("");
  const editorViewRef = useRef<EditorView | null>(null);

  // The slash menu container ref — SlashProvider needs an HTMLElement
  const slashMenuRef = useRef<HTMLDivElement | null>(null);

  useEditor((container) => {
    return Editor.make()
      .config((ctx) => {
        ctx.set(rootCtx, container);
        ctx.set(defaultValueCtx, markdown);
      })
      .config(nord)
      .use(commonmark)
      .use(gfm)
      .use(timestampBadge)
      .use(timestampBadgeView)
      .use(remarkTimestampBadgePlugin)
      .use(slash)
      .use(listener)
      .use(prism)
      .config((ctx) => {
        ctx.set(prismConfig.key, { configureRefractor: () => refractor });
      })
      .use(katexPlugins)
      .use(mermaidPlugins)
      .config((ctx) => {
        const listenerManager = ctx.get(listenerCtx);
        listenerManager.markdownUpdated((_, updatedMarkdown) => {
          onChangeRef.current(updatedMarkdown);
        });
      });
  }, [markdown]);

  const [loading, getEditorInstance] = useInstance();

  // When editor is ready, set up SlashProvider for slash command menu
  useEffect(() => {
    if (loading) return;
    const editor = getEditorInstance();
    if (!editor || !slashMenuRef.current) return;

    let provider: SlashProvider | null = null;

    try {
      editor.action((ctx) => {
        // Get the ProseMirror EditorView from the context.
        // We access it through the internal plugin system.
        const view = (ctx as unknown as Record<string, unknown>)
          .editorView as EditorView | undefined;
        if (!view) return;

        editorViewRef.current = view;

        provider = new SlashProvider({
          content: slashMenuRef.current!,
          trigger: "/",
          shouldShow: (currentView) => {
            // Show slash menu when "/" is typed
            const { selection } = currentView.state;
            if (!selection.empty) return false;
            const textBefore = currentView.state.doc.textBetween(
              Math.max(0, selection.from - 10),
              selection.from,
              "\n",
            );
            const match = textBefore.endsWith("/");
            if (match) {
              // Get cursor position for menu placement
              const coords = currentView.coordsAtPos(selection.from);
              setSlashPosition({
                top: coords.bottom + 4,
                left: coords.left,
              });
              setSlashFilter("");
            }
            return match;
          },
        });

        provider?.update(view);
      });
    } catch {
      // Slash provider setup may fail if editor view isn't ready yet
    }

    return () => {
      provider?.destroy();
    };
  }, [loading, getEditorInstance]);

  // Filter slash items by current input
  const filteredItems = slashFilter
    ? slashItems.filter(
        (item) =>
          item.label.toLowerCase().includes(slashFilter.toLowerCase()) ||
          (item.description &&
            item.description.toLowerCase().includes(slashFilter.toLowerCase())),
      )
    : slashItems;

  const handleSlashSelect = useCallback((item: SlashItem) => {
    if (editorViewRef.current) {
      // Delete the "/" trigger character before inserting the block
      const view = editorViewRef.current;
      const { from } = view.state.selection;
      const tr = view.state.tr.delete(from - 1, from);
      view.dispatch(tr);
      item.command(view);
    }
    setSlashVisible(false);
    setSlashFilter("");
  }, []);

  return (
    <div className="relative">
      {/* Invisible container for SlashProvider positioning */}
      <div ref={slashMenuRef} className="hidden" />
      <Milkdown />
      {slashVisible && (
        <SlashMenu
          items={filteredItems}
          onSelect={handleSlashSelect}
          position={slashPosition}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Public NoteEditor component
// ---------------------------------------------------------------------------

interface NoteEditorProps {
  markdown: string;
  onChange: (markdown: string) => void;
}

export function NoteEditor({ markdown, onChange }: NoteEditorProps) {
  const [editorKey, setEditorKey] = useState(0);
  const prevMarkdownRef = useRef(markdown);

  // Reset the editor when the markdown prop changes externally (e.g. switching notes)
  useEffect(() => {
    if (markdown !== prevMarkdownRef.current) {
      prevMarkdownRef.current = markdown;
      setEditorKey((k) => k + 1);
    }
  }, [markdown]);

  return (
    <div className="w-full">
      <div className="rounded-xl border border-border bg-background p-6 milkdown-editor-wrapper">
        <MilkdownProvider key={editorKey}>
          <MilkdownEditorInner markdown={markdown} onChange={onChange} />
        </MilkdownProvider>
      </div>
    </div>
  );
}
