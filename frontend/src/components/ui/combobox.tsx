import { useState, useRef, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import { ChevronDownIcon, Loader2 } from "lucide-react";

interface ComboboxProps {
  value: string;
  onChange: (value: string) => void;
  options: string[];
  placeholder?: string;
  loading?: boolean;
  disabled?: boolean;
  className?: string;
  loadingText?: string;
  emptyText?: string;
}

export function Combobox({
  value,
  onChange,
  options,
  placeholder = "Select or type...",
  loading = false,
  disabled = false,
  className,
  loadingText = "Loading...",
  emptyText = "No options found",
}: ComboboxProps) {
  const [open, setOpen] = useState(false);
  const [inputValue, setInputValue] = useState(value);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const [highlightIndex, setHighlightIndex] = useState(-1);

  // Sync external value changes to local input
  useEffect(() => {
    setInputValue(value);
  }, [value]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const filtered = options.filter((opt) =>
    opt.toLowerCase().includes(inputValue.toLowerCase())
  );

  // Reset highlight when filtered list changes
  useEffect(() => {
    setHighlightIndex(-1);
  }, [filtered.length]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value;
    setInputValue(v);
    onChange(v);
    setOpen(true);
    setHighlightIndex(-1);
  };

  const handleSelect = useCallback(
    (opt: string) => {
      setInputValue(opt);
      onChange(opt);
      setOpen(false);
      inputRef.current?.blur();
    },
    [onChange]
  );

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!open && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      setOpen(true);
      return;
    }
    if (!open) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightIndex((prev: number) => {
        const next = prev < filtered.length - 1 ? prev + 1 : prev;
        // Scroll into view
        requestAnimationFrame(() => {
          listRef.current?.children[next]?.scrollIntoView({ block: "nearest" });
        });
        return next;
      });
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightIndex((prev: number) => {
        const next = prev > 0 ? prev - 1 : 0;
        requestAnimationFrame(() => {
          listRef.current?.children[next]?.scrollIntoView({ block: "nearest" });
        });
        return next;
      });
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (highlightIndex >= 0 && highlightIndex < filtered.length) {
        handleSelect(filtered[highlightIndex]);
      } else {
        setOpen(false);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const handleFocus = () => {
    if (!disabled) setOpen(true);
  };

  return (
    <div ref={containerRef} className={cn("relative", className)}>
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          className={cn(
            "flex h-8 w-full rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm transition-colors outline-none placeholder:text-muted-foreground",
            "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
            "disabled:cursor-not-allowed disabled:opacity-50",
            "dark:bg-input/30"
          )}
          value={inputValue}
          onChange={handleInputChange}
          onFocus={handleFocus}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
        />
        <div className="absolute right-1.5 top-1/2 -translate-y-1/2 flex items-center gap-1 pointer-events-none">
          {loading && <Loader2 className="size-3.5 animate-spin text-muted-foreground" />}
          <ChevronDownIcon className="size-3.5 text-muted-foreground" />
        </div>
      </div>

      {open && (filtered.length > 0 || loading) && (
        <ul
          ref={listRef}
          className="absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-lg border bg-popover text-popover-foreground shadow-md ring-1 ring-foreground/10 py-1"
        >
          {loading && filtered.length === 0 ? (
            <li className="px-2.5 py-1.5 text-sm text-muted-foreground">
              {loading ? loadingText : emptyText}
            </li>
          ) : (
            filtered.map((opt, idx) => (
              <li
                key={opt}
                className={cn(
                  "cursor-pointer px-2.5 py-1.5 text-sm outline-none",
                  "hover:bg-accent hover:text-accent-foreground",
                  idx === highlightIndex && "bg-accent text-accent-foreground"
                )}
                onMouseDown={(e) => {
                  e.preventDefault();
                  handleSelect(opt);
                }}
                onMouseEnter={() => setHighlightIndex(idx)}
              >
                {opt}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
