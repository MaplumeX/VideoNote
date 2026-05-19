import React, {
  useState,
  useRef,
  useCallback,
  useEffect,
  forwardRef,
  useImperativeHandle,
} from "react";
import { useTranslation } from "react-i18next";
import { Minus, X, Play, GripVertical } from "lucide-react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Helpers: extract video ID / embed URL
// ---------------------------------------------------------------------------

/** Extract YouTube video ID from various URL formats. */
function extractYouTubeId(url: string): string | null {
  // https://www.youtube.com/watch?v=VIDEO_ID
  const watchMatch = url.match(/[?&]v=([a-zA-Z0-9_-]{11})/);
  if (watchMatch) return watchMatch[1];
  // https://youtu.be/VIDEO_ID
  const shortMatch = url.match(/youtu\.be\/([a-zA-Z0-9_-]{11})/);
  if (shortMatch) return shortMatch[1];
  // https://www.youtube.com/embed/VIDEO_ID
  const embedMatch = url.match(/youtube\.com\/embed\/([a-zA-Z0-9_-]{11})/);
  if (embedMatch) return embedMatch[1];
  return null;
}

/** Extract Bilibili BV ID from URL. */
function extractBilibiliBvid(url: string): string | null {
  const match = url.match(/\/(BV[a-zA-Z0-9]+)/);
  return match ? match[1] : null;
}

/** Build embeddable iframe URL with optional start seconds. */
function buildEmbedUrl(
  platform: string,
  videoUrl: string,
  seconds: number,
): string | null {
  if (platform === "youtube") {
    const id = extractYouTubeId(videoUrl);
    if (!id) return null;
    const params = new URLSearchParams({ autoplay: "1" });
    if (seconds > 0) params.set("start", String(seconds));
    return `https://www.youtube.com/embed/${id}?${params.toString()}`;
  }
  if (platform === "bilibili") {
    const bvid = extractBilibiliBvid(videoUrl);
    if (!bvid) return null;
    const params = new URLSearchParams({
      page: "1",
      high_quality: "1",
    });
    if (seconds > 0) params.set("start", String(seconds));
    return `https://player.bilibili.com/player.html?bvid=${bvid}&${params.toString()}`;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MIN_WIDTH = 320;
const MIN_HEIGHT = 180;
const DEFAULT_WIDTH = 480;
const DEFAULT_HEIGHT = 270;
const TITLE_BAR_HEIGHT = 36;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export interface VideoPlayerFloatProps {
  videoUrl: string;
  platform: string;
  onClose: () => void;
  initialSeconds?: number;
}

export interface VideoPlayerFloatHandle {
  seekTo: (seconds: number) => void;
}

export const VideoPlayerFloat = forwardRef<
  VideoPlayerFloatHandle,
  VideoPlayerFloatProps
>(function VideoPlayerFloat({ videoUrl, platform, onClose, initialSeconds = 0 }, ref) {
  const { t } = useTranslation();
  // -- Position & size state (bottom-right initial) --------------------------
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const [size, setSize] = useState({ w: DEFAULT_WIDTH, h: DEFAULT_HEIGHT });
  const [minimized, setMinimized] = useState(false);
  const [currentSeconds, setCurrentSeconds] = useState(initialSeconds);
  const [iframeKey, setIframeKey] = useState(0);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Set initial position once after first mount so we can read viewport size
  const initializedRef = useRef(false);
  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;
    const right = 24;
    const bottom = 24;
    setPos({
      x: window.innerWidth - DEFAULT_WIDTH - right,
      y: window.innerHeight - DEFAULT_HEIGHT - bottom,
    });
  }, []);

  // -- Imperative handle: seekTo ---------------------------------------------
  const seekTo = useCallback(
    (seconds: number) => {
      setCurrentSeconds(seconds);
      setMinimized(false);
      // Rebuild iframe by bumping key so the new src with start= is loaded
      setIframeKey((k) => k + 1);
    },
    [],
  );

  useImperativeHandle(ref, () => ({ seekTo }), [seekTo]);

  // -- Embed URL -------------------------------------------------------------
  const embedUrl = buildEmbedUrl(platform, videoUrl, currentSeconds);

  // -- Drag logic ------------------------------------------------------------
  const dragRef = useRef<{
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);

  const onDragStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      dragRef.current = {
        startX: e.clientX,
        startY: e.clientY,
        originX: pos.x,
        originY: pos.y,
      };
    },
    [pos.x, pos.y],
  );

  useEffect(() => {
    if (!dragRef.current) return;

    const onMouseMove = (e: MouseEvent) => {
      if (!dragRef.current) return;
      const dx = e.clientX - dragRef.current.startX;
      const dy = e.clientY - dragRef.current.startY;
      setPos({
        x: dragRef.current.originX + dx,
        y: dragRef.current.originY + dy,
      });
    };

    const onMouseUp = () => {
      dragRef.current = null;
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [pos.x, pos.y]);

  // -- Resize logic ----------------------------------------------------------
  const resizeRef = useRef<{
    startX: number;
    startY: number;
    originW: number;
    originH: number;
  } | null>(null);

  const onResizeStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      resizeRef.current = {
        startX: e.clientX,
        startY: e.clientY,
        originW: size.w,
        originH: size.h,
      };
    },
    [size.w, size.h],
  );

  useEffect(() => {
    if (!resizeRef.current) return;

    const onMouseMove = (e: MouseEvent) => {
      if (!resizeRef.current) return;
      const dw = e.clientX - resizeRef.current.startX;
      const dh = e.clientY - resizeRef.current.startY;
      setSize({
        w: Math.max(MIN_WIDTH, resizeRef.current.originW + dw),
        h: Math.max(MIN_HEIGHT, resizeRef.current.originH + dh),
      });
    };

    const onMouseUp = () => {
      resizeRef.current = null;
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [size.w, size.h]);

  // -- Invalid platform / URL guard ------------------------------------------
  if (!embedUrl) return null;

  const displayHeight = minimized ? TITLE_BAR_HEIGHT : size.h;

  return (
    <div
      ref={containerRef}
      className={cn(
        "fixed rounded-lg border border-border shadow-lg bg-background overflow-hidden",
        "flex flex-col z-50 transition-[height] duration-150 ease-in-out",
        "left-[var(--fp-left)] top-[var(--fp-top)] w-[var(--fp-w)] h-[var(--fp-h)]",
      )}
      style={{
        "--fp-left": `${pos.x}px`,
        "--fp-top": `${pos.y}px`,
        "--fp-w": `${size.w}px`,
        "--fp-h": `${displayHeight}px`,
      } as React.CSSProperties}
    >
      {/* Title bar */}
      <div
        className="flex items-center gap-2 px-3 shrink-0 bg-muted select-none cursor-grab active:cursor-grabbing h-[var(--fp-title-h)]"
        style={{ "--fp-title-h": `${TITLE_BAR_HEIGHT}px` } as React.CSSProperties}
        onMouseDown={onDragStart}
      >
        <GripVertical size={14} className="text-muted-foreground shrink-0" />
        <Play size={14} className="text-muted-foreground shrink-0" />
        <span className="text-xs font-medium text-foreground truncate">
          {t("videoPlayer.title", "Video Player")}
        </span>
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            className="inline-flex items-center justify-center rounded p-1 text-muted-foreground hover:bg-background hover:text-foreground transition-colors"
            onClick={(e) => {
              e.stopPropagation();
              setMinimized((m) => !m);
            }}
          >
            <Minus size={14} />
          </button>
          <button
            type="button"
            className="inline-flex items-center justify-center rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
            onClick={(e) => {
              e.stopPropagation();
              onClose();
            }}
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* iframe area */}
      {!minimized && (
        <div className="relative flex-1 min-h-0">
          <iframe
            key={iframeKey}
            src={embedUrl}
            className="absolute inset-0 w-full h-full border-0"
            allow="autoplay; encrypted-media; fullscreen"
            allowFullScreen
            title={t("videoPlayer.title", "Video Player")}
          />
        </div>
      )}

      {/* Resize handle */}
      {!minimized && (
        <div
          className="absolute bottom-0 right-0 w-4 h-4 cursor-se-resize"
          onMouseDown={onResizeStart}
        >
          {/* Diagonal grip lines */}
          <svg
            className="absolute bottom-0.5 right-0.5 text-muted-foreground/50"
            width="10"
            height="10"
            viewBox="0 0 10 10"
          >
            <line x1="7" y1="10" x2="10" y2="7" stroke="currentColor" strokeWidth="1.5" />
            <line x1="4" y1="10" x2="10" y2="4" stroke="currentColor" strokeWidth="1.5" />
          </svg>
        </div>
      )}
    </div>
  );
});
