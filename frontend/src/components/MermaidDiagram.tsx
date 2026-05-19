import { useEffect, useRef, useState, useId } from "react";
import { useTranslation } from "react-i18next";

interface MermaidDiagramProps {
  code: string;
  theme?: "light" | "dark";
}

export function MermaidDiagram({ code, theme }: MermaidDiagramProps) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const uniqueId = useId().replace(/:/g, "_");
  const renderCountRef = useRef(0);

  useEffect(() => {
    let cancelled = false;

    async function render() {
      try {
        const mermaid = await import("mermaid");
        const m = mermaid.default;

        m.initialize({
          startOnLoad: false,
          theme: theme === "dark" ? "dark" : "default",
          securityLevel: "loose",
        });

        renderCountRef.current += 1;
        const id = `mermaid_${uniqueId}_${renderCountRef.current}`;

        const { svg } = await m.render(id, code);

        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;
          setLoading(false);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          setLoading(false);
        }
      }
    }

    render();

    return () => {
      cancelled = true;
    };
  }, [code, theme, uniqueId]);

  if (loading) {
    return (
      <div className="mermaid-diagram rounded-lg border border-border bg-muted/30 p-4 text-center text-sm text-muted-foreground">
        {t("mermaid.loading")}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4">
        <p className="text-sm text-destructive mb-2">{t("mermaid.error")}</p>
        <pre className="text-xs text-muted-foreground overflow-x-auto whitespace-pre-wrap">
          {code}
        </pre>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="mermaid-diagram rounded-lg border border-border bg-muted/30 p-4"
    />
  );
}
