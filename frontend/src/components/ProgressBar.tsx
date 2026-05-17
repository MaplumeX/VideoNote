import type { TaskProgress } from "../types";
import { cn } from "../lib/utils";

interface ProgressBarProps {
  progress: TaskProgress | null;
}

const STAGE_LABELS: Record<string, string> = {
  pending: "Queued",
  downloading: "Downloading video",
  extracting_subtitles: "Extracting subtitles",
  transcribing: "Transcribing audio",
  generating_notes: "Generating notes",
  complete: "Complete",
  failed: "Failed",
};

export function ProgressBar({ progress }: ProgressBarProps) {
  if (!progress) return null;

  const percentage = Math.round(progress.progress * 100);
  const isFailed = progress.stage === "failed";
  const isComplete = progress.stage === "complete";

  return (
    <div className="w-full max-w-xl mx-auto">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium">
          {STAGE_LABELS[progress.stage] || progress.stage}
        </span>
        <span className={cn("text-sm", isFailed ? "text-destructive" : "text-muted-foreground")}>
          {isFailed ? "" : `${percentage}%`}
        </span>
      </div>

      <div className="h-2 rounded-full bg-muted overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            isFailed ? "bg-destructive" : isComplete ? "bg-green-500" : "bg-primary"
          )}
          style={{ width: `${percentage}%` }}
        />
      </div>

      {progress.message && (
        <p className={cn("text-xs mt-2", isFailed ? "text-destructive" : "text-muted-foreground")}>
          {progress.message}
        </p>
      )}
    </div>
  );
}
