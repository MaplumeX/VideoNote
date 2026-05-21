import { useEffect, useState, useRef, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

interface TOCItem {
  id: string;
  text: string;
  level: number;
}

interface TableOfContentsProps {
  containerRef: React.RefObject<HTMLDivElement | null>;
  /** Pass a value that changes when the container's content changes (e.g. markdown string) */
  contentKey?: string;
}

export function TableOfContents({ containerRef, contentKey }: TableOfContentsProps) {
  const { t } = useTranslation();
  const [headings, setHeadings] = useState<TOCItem[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const observerRef = useRef<IntersectionObserver | null>(null);
  const mutationTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const extractHeadings = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;

    const headingElements = container.querySelectorAll("h2, h3");
    const items: TOCItem[] = Array.from(headingElements)
      .filter((el) => el.id)
      .map((el) => ({
        id: el.id,
        text: el.textContent || "",
        level: parseInt(el.tagName[1], 10),
      }));
    setHeadings(items);
  }, [containerRef]);

  // Extract headings when contentKey changes
  useEffect(() => {
    // Delay slightly to allow Milkdown async render to complete
    const timer = setTimeout(extractHeadings, 100);
    return () => clearTimeout(timer);
  }, [contentKey, extractHeadings]);

  // Watch DOM mutations so TOC updates after Milkdown finishes async rendering
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const mo = new MutationObserver(() => {
      if (mutationTimerRef.current) clearTimeout(mutationTimerRef.current);
      mutationTimerRef.current = setTimeout(extractHeadings, 50);
    });

    mo.observe(container, { childList: true, subtree: true });
    return () => mo.disconnect();
  }, [containerRef, extractHeadings]);

  // Track active heading with IntersectionObserver
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Clean up previous observer
    if (observerRef.current) {
      observerRef.current.disconnect();
    }

    const headingElements = container.querySelectorAll("h2, h3");

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveId(entry.target.id);
          }
        }
      },
      { rootMargin: "-80px 0px -80% 0px" },
    );

    headingElements.forEach((el) => observer.observe(el));
    observerRef.current = observer;

    return () => observer.disconnect();
  }, [containerRef, headings]);

  const scrollTo = useCallback((id: string) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, []);

  if (headings.length === 0) return null;

  return (
    <nav className="sticky top-4 w-52 shrink-0 hidden lg:block">
      <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
        {t("toc.onThisPage")}
      </div>
      <ul className="space-y-1">
        {headings.map((heading) => (
          <li key={heading.id}>
            <button
              onClick={() => scrollTo(heading.id)}
              className={cn(
                "block text-left text-sm leading-snug transition-colors hover:text-foreground",
                heading.level === 3 && "pl-3",
                heading.id === activeId
                  ? "text-foreground font-medium"
                  : "text-muted-foreground",
              )}
            >
              {heading.text}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
