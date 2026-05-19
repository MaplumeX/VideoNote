import { useCallback, useEffect, useState } from "react";
import { authFetch } from "@/auth/api";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import {
  FileText,
  Trash2,
  RotateCcw,
  Ban,
  Globe,
  FileVideo,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StatusBadge, isActiveTask } from "@/components/StatusBadge";
import type { TaskListResponse, TaskItem } from "@/types";

function isRetriable(task: TaskItem): boolean {
  return task.stage === "failed" && task.source_type === "url" && !!task.video_url;
}

function SourceBadge({ task }: { task: TaskItem }) {
  if (task.source_type === "url" && task.platform) {
    return (
      <Badge variant="secondary" className="gap-1">
        <Globe size={12} />
        {task.platform}
      </Badge>
    );
  }
  if (task.source_type === "upload" && task.file_name) {
    return (
      <Badge variant="secondary" className="gap-1 truncate max-w-[150px]">
        <FileVideo size={12} />
        {task.file_name}
      </Badge>
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
        <FileText size={48} className="mx-auto text-muted-foreground/30" />
        <p className="mt-4 text-muted-foreground">{t("history.empty")}</p>
        <Button
          onClick={() => navigate("/app/new")}
          className="mt-4"
        >
          {t("history.processVideo")}
        </Button>
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
            <Card
              key={task.job_id}
              onClick={clickable ? () => navigate(`/app/notes/${task.job_id}`) : undefined}
              className={cn(
                "relative transition-all group hover:shadow-sm",
                clickable ? "cursor-pointer" : "cursor-default"
              )}
            >
              <CardContent className="p-4">
                {/* Delete button */}
                <Button
                  variant="ghost"
                  size="icon-xs"
                  onClick={(e) => {
                    e.stopPropagation();
                    void handleDelete(task.job_id);
                  }}
                  className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive"
                >
                  <Trash2 size={14} />
                </Button>

                {/* Title */}
                <p className="text-sm font-medium truncate pr-6">{getDisplayTitle(task)}</p>

                {/* Source + date */}
                <div className="flex items-center gap-2 mt-2 flex-wrap">
                  <SourceBadge task={task} />
                  {task.language && (
                    <Badge variant="outline" className="text-xs">{task.language}</Badge>
                  )}
                  <span className="text-xs text-muted-foreground">
                    {new Date(task.created_at).toLocaleDateString()}
                  </span>
                </div>

                {/* Status + actions */}
                <div className="flex items-center justify-between mt-3">
                  <StatusBadge task={task} />

                  <div className="flex items-center gap-1">
                    {isActiveTask(task) && (
                      <Button
                        variant="ghost"
                        size="icon-xs"
                        onClick={(e) => {
                          e.stopPropagation();
                          void handleCancel(task.job_id);
                        }}
                        title={t("history.cancel")}
                        className="text-muted-foreground hover:text-destructive"
                      >
                        <Ban size={14} />
                      </Button>
                    )}

                    {isRetriable(task) && (
                      <Button
                        variant="ghost"
                        size="icon-xs"
                        onClick={(e) => {
                          e.stopPropagation();
                          void handleRetry(task.job_id);
                        }}
                        title={t("history.retry")}
                        className="text-muted-foreground hover:text-blue-500"
                      >
                        <RotateCcw size={14} />
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-2">
          <p className="text-xs text-muted-foreground">
            {t("history.pageInfo", { page, totalPages })}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => loadTasks(page - 1)}
              disabled={page <= 1}
            >
              {t("history.previous")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => loadTasks(page + 1)}
              disabled={page >= totalPages}
            >
              {t("history.next")}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
