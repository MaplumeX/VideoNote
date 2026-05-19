import { useTranslation } from "react-i18next";
import { Clock, CheckCircle, AlertCircle, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { TaskItem, TaskStage } from "@/types";

const ACTIVE_STAGES: TaskStage[] = [
  "pending",
  "downloading",
  "extracting_subtitles",
  "transcribing",
  "generating_notes",
];

export function isActiveTask(task: TaskItem): boolean {
  return ACTIVE_STAGES.includes(task.stage);
}

export function StatusBadge({ task }: { task: TaskItem }) {
  const { t } = useTranslation();

  if (task.stage === "complete") {
    return (
      <Badge variant="secondary" className="gap-1 text-green-600 dark:text-green-400">
        <CheckCircle size={12} />
        {t("progress.complete")}
      </Badge>
    );
  }
  if (task.stage === "failed") {
    return (
      <Badge variant="destructive" className="gap-1">
        <AlertCircle size={12} />
        {t("progress.failed")}
      </Badge>
    );
  }
  if (task.stage === "cancelled") {
    return (
      <Badge variant="secondary" className="gap-1">
        <XCircle size={12} />
        {t("progress.cancelled")}
      </Badge>
    );
  }
  if (isActiveTask(task)) {
    return (
      <Badge variant="secondary" className="gap-1 text-blue-500 dark:text-blue-400">
        <Clock size={12} className="animate-pulse" />
        {Math.round(task.progress * 100)}%
      </Badge>
    );
  }
  return null;
}
