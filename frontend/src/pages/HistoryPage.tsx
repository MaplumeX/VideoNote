import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router";
import {
  FileText,
  Trash2,
  RotateCcw,
  Ban,
  Globe,
  FileVideo,
  Star,
  Tag,
  FolderOpen,
  ChevronDown,
  PanelLeftClose,
  PanelLeft,
  CheckSquare,
  Square,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StatusBadge, isActiveTask } from "@/components/StatusBadge";
import { fetchTasks, fetchTags, fetchFolderTree, toggleFavorite, batchAddTag, batchMoveToFolder, batchSetFavorite } from "@/api/client";
import { ContentSidebar } from "@/components/ContentSidebar";
import type { TaskListResponse, TaskItem, HistoryFilter, TagWithCount, FolderTreeNode } from "@/types";

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
  const [searchParams, setSearchParams] = useSearchParams();
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [batchMenuOpen, setBatchMenuOpen] = useState(false);
  const [pickerType, setPickerType] = useState<"tag" | "folder" | null>(null);
  const limit = 20;
  const totalPages = Math.max(1, Math.ceil(total / limit));

  // Read filter from URL params
  const filter: HistoryFilter = {};
  const folderParam = searchParams.get("folder");
  const tagParam = searchParams.get("tag");
  const favParam = searchParams.get("is_favorite");
  if (folderParam) filter.folder = folderParam;
  if (tagParam) filter.tag = tagParam;
  if (favParam === "true") filter.is_favorite = true;

  const handleFilterChange = (newFilter: HistoryFilter) => {
    const params = new URLSearchParams();
    if (newFilter.folder) params.set("folder", newFilter.folder);
    if (newFilter.tag) params.set("tag", newFilter.tag);
    if (newFilter.is_favorite) params.set("is_favorite", "true");
    setSearchParams(params, { replace: true });
    setSelectedIds(new Set());
  };

  const loadTasks = useCallback(
    (p: number) => {
      setLoading(true);
      setError(null);
      const params: Record<string, string | number | boolean> = { page: p, limit };
      if (filter.folder) params.folder = filter.folder;
      if (filter.tag) params.tag = filter.tag;
      if (filter.is_favorite) params.is_favorite = true;
      fetchTasks(params)
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
    [t, filter.folder, filter.tag, filter.is_favorite],
  );

  useEffect(() => {
    loadTasks(1);
  }, [loadTasks]);

  const handleDelete = async (jobId: string) => {
    if (!window.confirm(t("history.deleteConfirm"))) return;
    try {
      const { authFetch } = await import("@/auth/api");
      const res = await authFetch(`/api/tasks/${jobId}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      loadTasks(page);
    } catch {
      setActionError(t("history.deleteFailed"));
    }
  };

  const handleRetry = async (jobId: string) => {
    try {
      const { authFetch } = await import("@/auth/api");
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
      const { authFetch } = await import("@/auth/api");
      const res = await authFetch(`/api/tasks/${jobId}/cancel`, { method: "POST" });
      if (!res.ok) throw new Error();
      loadTasks(page);
    } catch {
      setActionError(t("history.cancelFailed"));
    }
  };

  const handleFavorite = async (jobId: string, currentFav: boolean) => {
    try {
      await toggleFavorite(jobId, { is_favorite: !currentFav });
      loadTasks(page);
    } catch {
      setActionError(t("history.actionFailed"));
    }
  };

  const toggleSelect = (jobId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(jobId)) next.delete(jobId);
      else next.add(jobId);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === tasks.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(tasks.map((t) => t.job_id)));
    }
  };

  const handleBatchFavorite = async (isFav: boolean) => {
    try {
      await batchSetFavorite({ job_ids: Array.from(selectedIds), is_favorite: isFav });
      setSelectedIds(new Set());
      loadTasks(page);
    } catch {
      setActionError(t("history.actionFailed"));
    }
    setBatchMenuOpen(false);
  };

  const handleBatchTag = async (tagId: string) => {
    try {
      await batchAddTag({ job_ids: Array.from(selectedIds), tag_id: tagId });
      loadTasks(page);
    } catch {
      setActionError(t("history.actionFailed"));
    }
    setPickerType(null);
    setBatchMenuOpen(false);
  };

  const handleBatchMove = async (folderId: string | null) => {
    try {
      await batchMoveToFolder({ job_ids: Array.from(selectedIds), folder_id: folderId });
      loadTasks(page);
    } catch {
      setActionError(t("history.actionFailed"));
    }
    setPickerType(null);
    setBatchMenuOpen(false);
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

  return (
    <div className="flex gap-6 -mx-4 md:-mx-6">
      {/* Sidebar */}
      <div
        className={cn(
          "shrink-0 border-r border-border transition-all overflow-hidden",
          sidebarOpen ? "w-52 pr-4" : "w-0 pr-0",
        )}
      >
        <ContentSidebar filter={filter} onFilterChange={handleFilterChange} />
      </div>

      {/* Main content */}
      <div className="flex-1 min-w-0 space-y-4">
        {/* Header row */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="text-muted-foreground"
            >
              {sidebarOpen ? <PanelLeftClose size={18} /> : <PanelLeft size={18} />}
            </Button>
            {selectedIds.size > 0 && (
              <span className="text-sm text-muted-foreground">
                {t("history.selected", { count: selectedIds.size })}
              </span>
            )}
          </div>

          {selectedIds.size > 0 && (
            <div className="relative">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setBatchMenuOpen(!batchMenuOpen)}
                className="gap-1.5"
              >
                <ChevronDown size={14} />
                {t("history.batchTag")}
              </Button>
              {batchMenuOpen && (
                <div className="absolute right-0 top-full mt-1 z-10 w-48 rounded-lg border border-border bg-background shadow-lg py-1">
                  <Button
                    variant="ghost"
                    onClick={() => {
                      setPickerType("tag");
                      setBatchMenuOpen(false);
                    }}
                    className="w-full justify-start gap-2 px-3 py-1.5 text-sm"
                  >
                    <Tag size={14} />
                    {t("history.batchTag")}
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => {
                      setPickerType("folder");
                      setBatchMenuOpen(false);
                    }}
                    className="w-full justify-start gap-2 px-3 py-1.5 text-sm"
                  >
                    <FolderOpen size={14} />
                    {t("history.batchMove")}
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => handleBatchFavorite(true)}
                    className="w-full justify-start gap-2 px-3 py-1.5 text-sm"
                  >
                    <Star size={14} />
                    {t("history.batchFavorite")}
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => handleBatchFavorite(false)}
                    className="w-full justify-start gap-2 px-3 py-1.5 text-sm"
                  >
                    <Star size={14} className="fill-none" />
                    {t("history.batchUnfavorite")}
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>

        {actionError && (
          <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive">
            {actionError}
          </div>
        )}

        {tasks.length === 0 ? (
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
        ) : (
          <>
            {/* Select all row */}
            <div className="flex items-center gap-2">
              <button
                onClick={toggleSelectAll}
                className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                {selectedIds.size === tasks.length ? (
                  <CheckSquare size={14} className="text-primary" />
                ) : (
                  <Square size={14} />
                )}
                {selectedIds.size === tasks.length ? t("history.deselectAll") : t("history.selectAll")}
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {tasks.map((task) => {
                const clickable = task.stage === "complete";
                const isSelected = selectedIds.has(task.job_id);
                const taskFav = task.is_favorite;
                return (
                  <Card
                    key={task.job_id}
                    onClick={clickable ? () => navigate(`/app/notes/${task.job_id}`) : undefined}
                    className={cn(
                      "relative transition-all group",
                      isSelected && "border-primary/40",
                      clickable ? "cursor-pointer hover:shadow-sm" : "cursor-default"
                    )}
                  >
                    <CardContent className="p-4">
                      {/* Select checkbox + Favorite + Delete */}
                      <div className="absolute top-2 right-2 flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="icon-xs"
                          onClick={(e: React.MouseEvent) => {
                            e.stopPropagation();
                            void handleFavorite(task.job_id, taskFav);
                          }}
                          className={cn(
                            taskFav
                              ? "text-yellow-500 hover:text-yellow-600"
                              : "text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-yellow-500"
                          )}
                        >
                          <Star size={14} className={taskFav ? "fill-current" : ""} />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon-xs"
                          onClick={(e: React.MouseEvent) => {
                            e.stopPropagation();
                            toggleSelect(task.job_id);
                          }}
                          className="text-muted-foreground"
                        >
                          {isSelected ? (
                            <CheckSquare size={14} className="text-primary" />
                          ) : (
                            <Square size={14} className="opacity-0 group-hover:opacity-100" />
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon-xs"
                          onClick={(e: React.MouseEvent) => {
                            e.stopPropagation();
                            void handleDelete(task.job_id);
                          }}
                          className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive"
                        >
                          <Trash2 size={14} />
                        </Button>
                      </div>

                      {/* Title */}
                      <p className="text-sm font-medium truncate pr-20">{getDisplayTitle(task)}</p>

                      {/* Source + date */}
                      <div className="flex items-center gap-3 mt-2">
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
                              onClick={(e: React.MouseEvent) => {
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
                              onClick={(e: React.MouseEvent) => {
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
          </>
        )}

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

      {/* Tag picker modal */}
      {pickerType === "tag" && (
        <TagPicker
          onPick={handleBatchTag}
          onClose={() => setPickerType(null)}
        />
      )}

      {/* Folder picker modal */}
      {pickerType === "folder" && (
        <FolderPickerModal
          onPick={handleBatchMove}
          onClose={() => setPickerType(null)}
        />
      )}
    </div>
  );
}

/** Simple modal to pick a tag from existing tags */
function TagPicker({
  onPick,
  onClose,
}: {
  onPick: (tagId: string) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [tags, setTags] = useState<TagWithCount[]>([]);

  useEffect(() => {
    fetchTags().then(setTags).catch(() => {});
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div
        className="w-72 rounded-lg border border-border bg-background shadow-lg p-4 space-y-2"
        onClick={(e: React.MouseEvent) => e.stopPropagation()}
      >
        <p className="text-sm font-medium">{t("history.batchTag")}</p>
        {tags.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t("history.noTags")}</p>
        ) : (
          <div className="space-y-1 max-h-60 overflow-y-auto">
            {tags.map((tag) => (
              <button
                key={tag.id}
                onClick={() => onPick(tag.id)}
                className="w-full text-left flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-muted transition-colors"
              >
                <span
                  className="w-2.5 h-2.5 rounded-full shrink-0"
                  style={{ backgroundColor: tag.color || "#6b7280" }}
                />
                {tag.name}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** Simple modal to pick a folder */
function FolderPickerModal({
  onPick,
  onClose,
}: {
  onPick: (folderId: string | null) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [folders, setFolders] = useState<FolderTreeNode[]>([]);

  useEffect(() => {
    fetchFolderTree().then(setFolders).catch(() => {});
  }, []);

  const renderNodes = (nodes: FolderTreeNode[], depth: number) =>
    nodes.map((node) => (
      <div key={node.id}>
        <button
          onClick={() => onPick(node.id)}
          className="w-full text-left flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-muted transition-colors"
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
        >
          <FolderOpen size={14} className="shrink-0" />
          {node.name}
        </button>
        {node.children.length > 0 && renderNodes(node.children, depth + 1)}
      </div>
    ));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div
        className="w-72 rounded-lg border border-border bg-background shadow-lg p-4 space-y-2"
        onClick={(e: React.MouseEvent) => e.stopPropagation()}
      >
        <p className="text-sm font-medium">{t("history.batchMove")}</p>
        <button
          onClick={() => onPick(null)}
          className="w-full text-left flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-muted transition-colors"
        >
          <FolderOpen size={14} />
          {t("history.noFolder")}
        </button>
        <div className="max-h-60 overflow-y-auto">{renderNodes(folders, 0)}</div>
      </div>
    </div>
  );
}
