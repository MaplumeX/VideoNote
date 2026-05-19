import { useMemo } from "react";
import { MarkdownHooks } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeSlug from "rehype-slug";
import rehypeKatex from "rehype-katex";
import rehypeShiki from "@shikijs/rehype";
import type { Components } from "react-markdown";
import type { PluggableList } from "unified";
import { MermaidDiagram } from "./MermaidDiagram";
import { useTheme } from "@/hooks/useTheme";
import "katex/dist/katex.min.css";

interface NotePreviewProps {
  markdown: string;
  onSeekTo?: (seconds: number) => void;
}

function TimestampBadge({
  seconds,
  onClick,
}: {
  seconds: number;
  onClick?: () => void;
}) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const timestamp = `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;

  return (
    <button
      onClick={onClick}
      className="inline-flex items-center rounded-md bg-accent px-1.5 py-0.5 text-xs font-mono text-primary hover:bg-primary hover:text-primary-foreground transition-colors cursor-pointer"
    >
      {timestamp}
    </button>
  );
}

const rehypePlugins: PluggableList = [
  rehypeSlug,
  [rehypeShiki, { themes: { light: "github-light", dark: "github-dark" } }],
  rehypeKatex,
];

const remarkPlugins: PluggableList = [remarkGfm, remarkMath];

export function NotePreview({ markdown, onSeekTo }: NotePreviewProps) {
  const { theme: currentTheme } = useTheme();

  const components: Components = useMemo(() => ({
    a({ href, children }) {
      if (href?.startsWith("#t=")) {
        const seconds = parseInt(href.slice(3), 10);
        if (!isNaN(seconds)) {
          return <TimestampBadge seconds={seconds} onClick={onSeekTo ? () => onSeekTo(seconds) : undefined} />;
        }
      }
      return <a href={href}>{children}</a>;
    },
    code({ className, children }) {
      // Handle mermaid code blocks — render with MermaidDiagram component
      if (className === "language-mermaid") {
        return <MermaidDiagram code={String(children).replace(/\n$/, "")} theme={currentTheme} />;
      }
      // For other code blocks, let shiki handle highlighting via the rehype plugin.
      // Only pass className and children to avoid spreading react-markdown internal props.
      return <code className={className}>{children}</code>;
    },
  }), [onSeekTo, currentTheme]);

  if (!markdown) return null;

  return (
    <div className="w-full max-w-3xl mx-auto">
      <div className="rounded-xl border border-border bg-background p-6">
        <div className="prose prose-sm max-w-none">
          <MarkdownHooks
            remarkPlugins={remarkPlugins}
            rehypePlugins={rehypePlugins}
            components={components}
            fallback={null}
          >
            {markdown}
          </MarkdownHooks>
        </div>
      </div>
    </div>
  );
}
