import { useEffect, useState } from "react";
import { authFetch } from "@/auth/api";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { FileText, Clock, AlertCircle, CheckCircle } from "lucide-react";

interface TaskItem {
  job_id: string;
  stage: string;
  progress: number;
  message: string;
  created_at: string;
}

export function HistoryPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    authFetch("/api/tasks")
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load tasks");
        return res.json();
      })
      .then((data: TaskItem[]) => {
        setTasks(data);
        setLoading(false);
      })
      .catch(() => {
        setError(t("history.loadFailed"));
        setLoading(false);
      });
  }, [t]);

  if (loading) {
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
    <div className="space-y-3">
      {tasks.map((task) => (
        <button
          key={task.job_id}
          onClick={() => {
            if (task.stage === "complete") navigate(`/app?task=${task.job_id}`);
          }}
          disabled={task.stage !== "complete"}
          className="w-full text-left rounded-lg border border-border p-4 hover:bg-muted/50 transition-colors disabled:opacity-60 disabled:cursor-default"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-start gap-3 min-w-0">
              <div className="mt-0.5">
                {task.stage === "complete" && <CheckCircle size={16} className="text-green-500" />}
                {task.stage === "failed" && <AlertCircle size={16} className="text-destructive" />}
                {task.stage !== "complete" && task.stage !== "failed" && (
                  <Clock size={16} className="text-muted-foreground" />
                )}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium truncate">{task.message || task.stage}</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {task.job_id.slice(0, 8)} · {new Date(task.created_at).toLocaleString()}
                </p>
              </div>
            </div>
            <span className="text-xs text-muted-foreground shrink-0">
              {task.stage === "complete" ? "100%" : `${Math.round(task.progress * 100)}%`}
            </span>
          </div>
        </button>
      ))}
    </div>
  );
}
