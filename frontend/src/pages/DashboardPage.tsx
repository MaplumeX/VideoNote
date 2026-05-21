import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import {
  Plus,
  FileText,
  Globe,
  FileVideo,
  Star,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge, isActiveTask } from "@/components/StatusBadge";
import { fetchTasks } from "@/api/client";
import type { TaskItem } from "@/types";

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
    const clickable = task.stage === "complete" || isActiveTask(task);
    const taskFav = task.is_favorite;
    const thumbSrc = task.thumbnail_url
      ? task.thumbnail_url.startsWith("http")
        ? task.thumbnail_url
        : `/api/thumbnails/${task.thumbnail_url}`
      : null;
    return (
      <Card
        onClick={clickable ? () => navigate(`/app/notes/${task.job_id}`) : undefined}
        className={cn(
          "cursor-pointer hover:shadow-sm transition-shadow",
          !clickable && "cursor-default hover:shadow-none"
        )}
      >
        <CardContent className="flex items-center gap-3 py-3">
          {thumbSrc ? (
            <img
              src={thumbSrc}
              alt=""
              className="w-16 h-10 rounded object-cover shrink-0"
              loading="lazy"
            />
          ) : task.source_type === "upload" ? (
            <div className="w-16 h-10 rounded bg-muted flex items-center justify-center shrink-0">
              <FileVideo size={16} className="text-muted-foreground/40" />
            </div>
          ) : (
            <SourceIcon task={task} />
          )}
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
        </CardContent>
      </Card>
    );
  };

  return (
    <div className="space-y-8">
      {/* New Note CTA */}
      <div className="flex justify-center">
        <Button
          size="lg"
          onClick={() => navigate("/app/new")}
          className="gap-2 px-8 py-5 text-base"
        >
          <Plus size={20} />
          {t("dashboard.newNote")}
        </Button>
      </div>

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
