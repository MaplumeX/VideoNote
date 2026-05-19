import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { authFetch } from "@/auth/api";
import { Plus, FileText, Globe, FileVideo } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge, isActiveTask } from "@/components/StatusBadge";
import type { TaskListResponse, TaskItem } from "@/types";

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
  const [loading, setLoading] = useState(true);

  const loadRecent = useCallback(async () => {
    try {
      const res = await authFetch("/api/tasks?page=1&limit=5");
      if (!res.ok) throw new Error("Failed");
      const data: TaskListResponse = await res.json();
      setTasks(data.items);
    } catch {
      // silent fail for dashboard
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRecent();
  }, [loadRecent]);

  const getDisplayTitle = (task: TaskItem) => {
    return task.title || task.video_url || task.file_name || task.message || task.stage;
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

      {/* Recent notes */}
      <div>
        <h2 className="text-sm font-medium text-muted-foreground mb-3">
          {t("dashboard.recentNotes")}
        </h2>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <p className="text-sm text-muted-foreground">{t("history.loading")}</p>
          </div>
        ) : tasks.length === 0 ? (
          <div className="text-center py-12">
            <FileText size={48} className="mx-auto text-muted-foreground/30" />
            <p className="mt-4 text-sm text-muted-foreground">{t("dashboard.empty")}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {tasks.map((task) => {
              const clickable = task.stage === "complete" || isActiveTask(task);
              return (
                <Card
                  key={task.job_id}
                  onClick={clickable ? () => navigate(`/app/notes/${task.job_id}`) : undefined}
                  className={cn(
                    "cursor-pointer hover:shadow-sm transition-shadow",
                    !clickable && "cursor-default hover:shadow-none"
                  )}
                >
                  <CardContent className="flex items-center gap-3 py-3">
                    <SourceIcon task={task} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">
                        {getDisplayTitle(task)}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {new Date(task.created_at).toLocaleDateString()}
                      </p>
                    </div>
                    <StatusBadge task={task} />
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
