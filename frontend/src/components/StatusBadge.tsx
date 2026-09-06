import { useTranslation } from "react-i18next";
import { Clock, CheckCircle, AlertCircle, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { TaskItem } from "@/types";
import { pathForSource, synthesizeProgress } from "@/lib/phaseProgress";

export function isActiveTask(task: TaskItem): boolean {
  return task.status === "pending" || task.status === "running";
}

export function StatusBadge({ task }: { task: TaskItem }) {
  const { t } = useTranslation();

  if (task.status === "complete") {
    return (
      <Badge variant="secondary" className="gap-1 text-green-600 dark:text-green-400">
        <CheckCircle size={12} />
        {t("progress.complete")}
      </Badge>
    );
  }
  if (task.status === "failed") {
    return (
      <Badge variant="destructive" className="gap-1">
        <AlertCircle size={12} />
        {t("progress.failed")}
      </Badge>
    );
  }
  if (task.status === "cancelled") {
    return (
      <Badge variant="secondary" className="gap-1">
        <XCircle size={12} />
        {t("progress.cancelled")}
      </Badge>
    );
  }
  if (isActiveTask(task)) {
    const path = pathForSource(task.source_type === "upload" ? "upload" : "url");
    const fraction =
      task.phase !== null ? synthesizeProgress(task.phase, task.phase_progress ?? 0, path) : 0;
    return (
      <Badge variant="secondary" className="gap-1 text-blue-500 dark:text-blue-400">
        <Clock size={12} className="animate-pulse" />
        {task.status === "pending" ? t("progress.pending") : `${Math.round(fraction * 100)}%`}
      </Badge>
    );
  }
  return null;
}
