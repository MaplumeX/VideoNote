import { useCallback, useEffect, useState } from "react";
import { authFetch } from "@/auth/api";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import {
  FileText,
  Clock,
  AlertCircle,
  CheckCircle,
  XCircle,
  Trash2,
  RotateCcw,
  Ban,
  Globe,
  FileVideo,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { TaskListResponse, TaskItem, TaskStage } from "@/types";

const ACTIVE_STAGES: TaskStage[] = [
  "pending",
  "downloading",
  "extracting_subtitles",
  "transcribing",
  "generating_notes",
];

function isRetriable(task: TaskItem): boolean {
  return task.stage === "failed" && task.source_type === "url" && !!task.video_url;
}

function isActive(task: TaskItem): boolean {
  return ACTIVE_STAGES.includes(task.stage);
}

function StatusBadge({ task }: { task: TaskItem }) {
  const { t } = useTranslation();
  if (task.stage === "complete") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-green-600">
        <CheckCircle size={12} />
        {t("progress.complete")}
      </span>
    );
  }
  if (task.stage === "failed") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-destructive">
        <AlertCircle size={12} />
        {t("progress.failed")}
      </span>
    );
  }
  if (task.stage === "cancelled") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <XCircle size={12} />
        {t("progress.cancelled")}
      </span>
    );
  }
  if (isActive(task)) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-blue-500">
        <Clock size={12} className="animate-pulse" />
        {Math.round(task.progress * 100)}%
      </span>
    );
  }
  return null;
}

function SourceBadge({ task }: { task: TaskItem }) {
  if (task.source_type === "url" && task.platform) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <Globe size={12} />
        {task.platform}
      </span>
    );
  }
  if (task.source_type === "upload" && task.file_name) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground truncate max-w-[150px]">
        <FileVideo size={12} />
        {task.file_name}
      </span>
    );
  }
  return null;
}

export function HistoryPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const limit = 20;

  const totalPages = Math.max(1, Math.ceil(total / limit));

  const loadTasks = useCallback(
    (p: number) => {
      setLoading(true);
      setError(null);
      authFetch(`/api/tasks?page=${p}&limit=${limit}`)
        .then((res) => {
          if (!res.ok) throw new Error("Failed to load tasks");
          return res.json();
        })
        .then((data: TaskListResponse) => {
          setTasks(data.items);
          setTotal(data.total);
          setPage(data.page);
          setLoading(false);
        })
        .catch(() => {
          setError(t("history.loadFailed"));
          setLoading(false);
        });
    },
    [t],
  );

  useEffect(() => {
    loadTasks(1);
  }, [loadTasks]);

  const handleDelete = async (jobId: string) => {
    if (!window.confirm(t("history.deleteConfirm"))) return;
    try {
      const res = await authFetch(`/api/tasks/${jobId}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      loadTasks(page);
    } catch {
      setActionError(t("history.deleteFailed"));
    }
  };

  const handleRetry = async (jobId: string) => {
    try {
      const res = await authFetch(`/api/tasks/${jobId}/retry`, { method: "POST" });
      if (!res.ok) throw new Error();
      const data = await res.json();
      navigate(`/app/new?job=${data.job_id}`);
    } catch {
      setActionError(t("history.retryFailed"));
    }
  };

  const handleCancel = async (jobId: string) => {
    try {
      const res = await authFetch(`/api/tasks/${jobId}/cancel`, { method: "POST" });
      if (!res.ok) throw new Error();
      loadTasks(page);
    } catch {
      setActionError(t("history.cancelFailed"));
    }
  };

  const getDisplayTitle = (task: TaskItem) => {
    return task.title || task.video_url || task.file_name || task.message || task.stage;
  };

  if (loading && tasks.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-muted-foreground">{t("history.loading")}</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive">
        {error}
      </div>
    );
  }

  if (tasks.length === 0) {
    return (
      <div className="text-center py-12">
        <FileText size={48} className="mx-auto text-muted-foreground/50" />
        <p className="mt-4 text-muted-foreground">{t("history.empty")}</p>
        <button
          onClick={() => navigate("/app/new")}
          className="mt-4 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          {t("history.processVideo")}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {actionError && (
        <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive">
          {actionError}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {tasks.map((task) => {
          const clickable = task.stage === "complete";
          return (
            <div
              key={task.job_id}
              onClick={clickable ? () => navigate(`/app/notes/${task.job_id}`) : undefined}
              className={cn(
                "relative rounded-lg border border-border p-4 transition-all group",
                clickable
                  ? "cursor-pointer hover:shadow-sm hover:border-primary/20"
                  : "cursor-default"
              )}
            >
              {/* Delete button */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  void handleDelete(task.job_id);
                }}
                className="absolute top-2 right-2 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-muted transition-all text-muted-foreground hover:text-destructive"
              >
                <Trash2 size={14} />
              </button>

              {/* Title */}
              <p className="text-sm font-medium truncate pr-6">{getDisplayTitle(task)}</p>

              {/* Source + date */}
              <div className="flex items-center gap-3 mt-2">
                <SourceBadge task={task} />
                {task.language && (
                  <span className="text-xs text-muted-foreground">{task.language}</span>
                )}
                <span className="text-xs text-muted-foreground">
                  {new Date(task.created_at).toLocaleDateString()}
                </span>
              </div>

              {/* Status + actions */}
              <div className="flex items-center justify-between mt-3">
                <StatusBadge task={task} />

                <div className="flex items-center gap-1">
                  {isActive(task) && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleCancel(task.job_id);
                      }}
                      className="p-1 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-destructive"
                      title={t("history.cancel")}
                    >
                      <Ban size={14} />
                    </button>
                  )}

                  {isRetriable(task) && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleRetry(task.job_id);
                      }}
                      className="p-1 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-blue-500"
                      title={t("history.retry")}
                    >
                      <RotateCcw size={14} />
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-2">
          <p className="text-xs text-muted-foreground">
            {t("history.pageInfo", { page, totalPages })}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => loadTasks(page - 1)}
              disabled={page <= 1}
              className="rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-muted transition-colors disabled:opacity-40 disabled:cursor-default"
            >
              {t("history.previous")}
            </button>
            <button
              onClick={() => loadTasks(page + 1)}
              disabled={page >= totalPages}
              className="rounded-lg border border-border px-3 py-1.5 text-sm hover:bg-muted transition-colors disabled:opacity-40 disabled:cursor-default"
            >
              {t("history.next")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
