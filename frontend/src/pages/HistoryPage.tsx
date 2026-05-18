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
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground truncate max-w-[180px]">
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
      navigate(`/app?task=${data.job_id}`);
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
          onClick={() => navigate("/app")}
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

      <div className="space-y-3">
        {tasks.map((task) => (
          <div
            key={task.job_id}
            className="rounded-lg border border-border p-4 hover:bg-muted/50 transition-colors"
          >
            <div className="flex items-start justify-between gap-3">
              <div
                className="flex items-start gap-3 min-w-0 flex-1 cursor-pointer"
                onClick={() => {
                  if (task.stage === "complete") navigate(`/app?task=${task.job_id}`);
                }}
              >
                <div className="mt-0.5 shrink-0">
                  {task.stage === "complete" && <CheckCircle size={16} className="text-green-500" />}
                  {task.stage === "failed" && <AlertCircle size={16} className="text-destructive" />}
                  {task.stage === "cancelled" && <XCircle size={16} className="text-muted-foreground" />}
                  {isActive(task) && <Clock size={16} className="text-blue-500 animate-pulse" />}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">
                    {task.video_url || task.file_name || task.message || task.stage}
                  </p>
                  <div className="flex items-center gap-3 mt-1">
                    <SourceBadge task={task} />
                    {task.language && (
                      <span className="text-xs text-muted-foreground">
                        {task.language}
                      </span>
                    )}
                    <span className="text-xs text-muted-foreground">
                      {task.job_id.slice(0, 8)} · {new Date(task.created_at).toLocaleString()}
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <span className="text-xs text-muted-foreground">
                  {task.stage === "complete"
                    ? "100%"
                    : task.stage === "failed" || task.stage === "cancelled"
                      ? "-"
                      : `${Math.round(task.progress * 100)}%`}
                </span>

                {isActive(task) && (
                  <button
                    onClick={() => handleCancel(task.job_id)}
                    className="p-1.5 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-destructive"
                    title={t("history.cancel")}
                  >
                    <Ban size={14} />
                  </button>
                )}

                {isRetriable(task) && (
                  <button
                    onClick={() => handleRetry(task.job_id)}
                    className="p-1.5 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-blue-500"
                    title={t("history.retry")}
                  >
                    <RotateCcw size={14} />
                  </button>
                )}

                <button
                  onClick={() => handleDelete(task.job_id)}
                  className="p-1.5 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-destructive"
                  title={t("history.delete")}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          </div>
        ))}
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
