import { useTranslation } from "react-i18next";
import type { TaskPhase, TaskProgress, TaskStatus } from "../types";
import { cn } from "../lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { pathForSource, synthesizeProgress } from "@/lib/phaseProgress";

interface ProgressBarProps {
  progress: TaskProgress | null;
  sourceType?: "url" | "upload";
}

const PHASE_KEY: Record<TaskPhase, string> = {
  fetching: "progress.fetching",
  subtitle: "progress.subtitle",
  audio: "progress.audio",
  transcribe: "progress.transcribe",
  notegen: "progress.notegen",
};

const STATUS_KEY: Record<TaskStatus, string> = {
  pending: "progress.pending",
  running: "progress.running",
  complete: "progress.complete",
  failed: "progress.failed",
  cancelled: "progress.cancelled",
};

export function ProgressBar({ progress, sourceType }: ProgressBarProps) {
  const { t } = useTranslation();

  if (!progress) return null;

  const isFailed = progress.status === "failed";
  const isCancelled = progress.status === "cancelled";
  const isComplete = progress.status === "complete";
  const path = pathForSource(sourceType);
  const percentage = Math.round(
    synthesizeProgress(progress.phase, progress.phase_progress, path) * 100,
  );
  const labelKey =
    progress.status === "running" && progress.phase
      ? PHASE_KEY[progress.phase]
      : STATUS_KEY[progress.status];

  return (
    <Card className="max-w-xl mx-auto">
      <CardContent className="p-4 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">
            {t(labelKey)}
          </span>
          <span className={cn("text-sm", isFailed || isCancelled ? "text-destructive" : "text-muted-foreground")}>
            {isFailed || isCancelled ? "" : `${isComplete ? 100 : percentage}%`}
          </span>
        </div>

        <div className="h-2 rounded-full bg-muted overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-500",
              isFailed || isCancelled ? "bg-destructive" : isComplete ? "bg-green-500 dark:bg-green-400" : "bg-primary"
            )}
            style={{ width: isFailed || isCancelled ? "100%" : `${isComplete ? 100 : percentage}%` }}
          />
        </div>
      </CardContent>
    </Card>
  );
}
