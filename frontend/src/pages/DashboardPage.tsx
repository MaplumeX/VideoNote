import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import {
  Plus,
  FileText,
  Globe,
  FileVideo,
  Clock,
  CheckCircle,
  AlertCircle,
  XCircle,
  Star,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { fetchTasks } from "@/api/client";
import type { TaskItem, TaskStage } from "@/types";

const ACTIVE_STAGES: TaskStage[] = [
  "pending",
  "downloading",
  "extracting_subtitles",
  "transcribing",
  "generating_notes",
];

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

function SourceIcon({ task }: { task: TaskItem }) {
  if (task.source_type === "url" && task.platform) {
    return <Globe size={14} className="text-muted-foreground" />;
  }
  if (task.source_type === "upload") {
    return <FileVideo size={14} className="text-muted-foreground" />;
  }
  return <FileText size={14} className="text-muted-foreground" />;
}

export function DashboardPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [favoriteTasks, setFavoriteTasks] = useState<TaskItem[]>([]);
  const [loading, setLoading] = useState(true);

  const loadRecent = useCallback(async () => {
    try {
      const data = await fetchTasks({ page: 1, limit: 5 });
      setTasks(data.items);
    } catch {
      // silent fail for dashboard
    } finally {
      setLoading(false);
    }
  }, []);

  const loadFavorites = useCallback(async () => {
    try {
      const data = await fetchTasks({ page: 1, limit: 5, is_favorite: true });
      setFavoriteTasks(data.items);
    } catch {
      // silent fail
    }
  }, []);

  useEffect(() => {
    void loadRecent();
    void loadFavorites();
  }, [loadRecent, loadFavorites]);

  const getDisplayTitle = (task: TaskItem) => {
    return task.title || task.video_url || task.file_name || task.message || task.stage;
  };

  const TaskRow = ({ task }: { task: TaskItem }) => {
    const clickable = task.stage === "complete";
    const taskFav = task.is_favorite;
    return (
      <div
        onClick={clickable ? () => navigate(`/app/notes/${task.job_id}`) : undefined}
        className={cn(
          "flex items-center gap-3 rounded-lg border border-border p-3 transition-colors group",
          clickable ? "cursor-pointer hover:bg-muted/50" : "cursor-default",
        )}
      >
        <SourceIcon task={task} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            {taskFav && <Star size={12} className="text-yellow-500 fill-current shrink-0" />}
            <p className="text-sm font-medium truncate">{getDisplayTitle(task)}</p>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            {new Date(task.created_at).toLocaleDateString()}
          </p>
        </div>
        <StatusBadge task={task} />
      </div>
    );
  };

  return (
    <div className="space-y-8">
      {/* New Note button */}
      <button
        onClick={() => navigate("/app/new")}
        className="w-full flex items-center justify-center gap-2 rounded-xl bg-primary px-6 py-4 text-base font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
      >
        <Plus size={20} />
        {t("dashboard.newNote")}
      </button>

      {/* Favorites section */}
      {favoriteTasks.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Star size={16} className="text-yellow-500 fill-current" />
            <h2 className="text-sm font-medium text-muted-foreground">
              {t("dashboard.favorites")}
            </h2>
          </div>
          <div className="space-y-2">
            {favoriteTasks.map((task) => (
              <TaskRow key={task.job_id} task={task} />
            ))}
          </div>
        </div>
      )}

      {/* Recent notes */}
      <div>
        <h2 className="text-sm font-medium text-muted-foreground mb-3">
          {t("dashboard.recentNotes")}
        </h2>

        {loading ? (
          <div className="flex items-center justify-center py-8">
            <p className="text-sm text-muted-foreground">{t("history.loading")}</p>
          </div>
        ) : tasks.length === 0 ? (
          <div className="text-center py-8">
            <FileText size={36} className="mx-auto text-muted-foreground/40" />
            <p className="mt-3 text-sm text-muted-foreground">{t("dashboard.empty")}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {tasks.map((task) => (
              <TaskRow key={task.job_id} task={task} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
