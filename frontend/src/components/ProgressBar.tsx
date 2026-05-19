import { useTranslation } from "react-i18next";
import type { TaskProgress, TaskStage } from "../types";
import { cn } from "../lib/utils";
import { Card, CardContent } from "@/components/ui/card";

interface ProgressBarProps {
  progress: TaskProgress | null;
}

const STAGE_KEY: Record<TaskStage, string> = {
  pending: "progress.pending",
  downloading: "progress.downloading",
  extracting_subtitles: "progress.extracting_subtitles",
  transcribing: "progress.transcribing",
  generating_notes: "progress.generating_notes",
  complete: "progress.complete",
  failed: "progress.failed",
  cancelled: "progress.cancelled",
};

export function ProgressBar({ progress }: ProgressBarProps) {
  const { t } = useTranslation();

  if (!progress) return null;

  const percentage = Math.round(progress.progress * 100);
  const isFailed = progress.stage === "failed";
  const isCancelled = progress.stage === "cancelled";
  const isComplete = progress.stage === "complete";
  const stageKey = STAGE_KEY[progress.stage];

  return (
    <Card className="max-w-xl mx-auto">
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">
            {t(stageKey)}
          </span>
          <span className={cn("text-sm", isFailed || isCancelled ? "text-destructive" : "text-muted-foreground")}>
            {isFailed || isCancelled ? "" : `${percentage}%`}
          </span>
        </div>

        <div className="h-2 rounded-full bg-muted overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-500",
              isFailed || isCancelled ? "bg-destructive" : isComplete ? "bg-green-500 dark:bg-green-400" : "bg-primary"
            )}
            style={{ width: isFailed || isCancelled ? "100%" : `${percentage}%` }}
          />
        </div>
      </CardContent>
    </Card>
  );
}
