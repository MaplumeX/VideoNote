import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

interface NoteViewProps {
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

const components: Components = {
  a({ href, children }) {
    if (href?.startsWith("#t=")) {
      const seconds = parseInt(href.slice(3), 10);
      if (!isNaN(seconds)) {
        return (
          <TimestampBadge
            seconds={seconds}
          />
        );
      }
    }
    return <a href={href}>{children}</a>;
  },
};

export function NoteView({ markdown }: NoteViewProps) {
  if (!markdown) return null;

  return (
    <div className="w-full max-w-3xl mx-auto">
      <div className="rounded-xl border border-border bg-background p-6">
        <div className="prose prose-sm max-w-none">
          <Markdown remarkPlugins={[remarkGfm]} components={components}>
            {markdown}
          </Markdown>
        </div>
      </div>
    </div>
  );
}
