import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  LayoutGrid,
  List,
  SlidersHorizontal,
  ArrowUpDown,
  CheckSquare,
  Square,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import { StatusBadge, isActiveTask } from "@/components/StatusBadge";
import { useConfirm } from "@/hooks/useConfirm";
import {
  fetchTasks,
  fetchTags,
  fetchFolderTree,
  toggleFavorite,
  batchAddTag,
  batchMoveToFolder,
  batchSetFavorite,
  batchDelete,
} from "@/api/client";
import { ContentSidebar } from "@/components/ContentSidebar";
import type {
  TaskListResponse,
  TaskItem,
  HistoryFilter,
  TagWithCount,
  FolderTreeNode,
} from "@/types";

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

type ViewMode = "card" | "list";

function getStoredViewMode(): ViewMode {
  try {
    const stored = localStorage.getItem("history-view-mode");
    if (stored === "list" || stored === "card") return stored;
  } catch {
    // ignore
  }
  return "card";
}

function storeViewMode(mode: ViewMode) {
  try {
    localStorage.setItem("history-view-mode", mode);
  } catch {
    // ignore
  }
}

/** Generate page numbers with ellipsis for pagination */
function getPageNumbers(current: number, total: number): (number | "ellipsis")[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }
  const pages: (number | "ellipsis")[] = [1];
  if (current > 3) pages.push("ellipsis");
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  for (let i = start; i <= end; i++) pages.push(i);
  if (current < total - 2) pages.push("ellipsis");
  pages.push(total);
  return pages;
}

export function HistoryPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { confirm } = useConfirm();
  const [searchParams, setSearchParams] = useSearchParams();
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [pickerType, setPickerType] = useState<"tag" | "folder" | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const limit = 20;
  const totalPages = Math.max(1, Math.ceil(total / limit));

  // View mode: URL param > localStorage > default
  const viewParam = searchParams.get("view");
  const [viewMode, setViewMode] = useState<ViewMode>(
    viewParam === "list" ? "list" : viewParam === "card" ? "card" : getStoredViewMode(),
  );

  // Search debounce
  const searchParam = searchParams.get("search") || "";
  const [searchInput, setSearchInput] = useState(searchParam);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Sort: URL params
  const sortBy = searchParams.get("sort_by") || "";
  const sortOrder = searchParams.get("sort_order") || "";

  // Read filter from URL params
  const filter: HistoryFilter = {};
  const folderParam = searchParams.get("folder");
  const tagParam = searchParams.get("tag");
  const favParam = searchParams.get("is_favorite");
  if (folderParam) filter.folder = folderParam;
  if (tagParam) filter.tag = tagParam;
  if (favParam === "true") filter.is_favorite = true;
  if (searchParam) filter.search = searchParam;
  if (sortBy) filter.sort_by = sortBy;
  if (sortOrder) filter.sort_order = sortOrder;

  // Resolve tag/folder names for filter pills
  const [allTags, setAllTags] = useState<TagWithCount[]>([]);
  const [allFolders, setAllFolders] = useState<FolderTreeNode[]>([]);

  useEffect(() => {
    fetchTags().then(setAllTags).catch(() => {});
    fetchFolderTree().then(setAllFolders).catch(() => {});
  }, []);

  const findFolderName = useCallback(
    (id: string): string => {
      function search(nodes: FolderTreeNode[]): string {
        for (const node of nodes) {
          if (node.id === id) return node.name;
          const found = search(node.children);
          if (found) return found;
        }
        return "";
      }
      return search(allFolders) || id;
    },
    [allFolders],
  );

  const findTagName = useCallback(
    (id: string): string => {
      return allTags.find((tg) => tg.id === id)?.name || id;
    },
    [allTags],
  );

  const handleFilterChange = (newFilter: HistoryFilter) => {
    const params = new URLSearchParams(searchParams);
    // Remove old filter keys
    params.delete("folder");
    params.delete("tag");
    params.delete("is_favorite");
    if (newFilter.folder) params.set("folder", newFilter.folder);
    if (newFilter.tag) params.set("tag", newFilter.tag);
    if (newFilter.is_favorite) params.set("is_favorite", "true");
    setSearchParams(params, { replace: true });
    setSelectedIds(new Set());
  };

  const removeFilter = (key: "folder" | "tag" | "is_favorite") => {
    const newFilter = { ...filter };
    delete (newFilter as Record<string, unknown>)[key];
    handleFilterChange(newFilter);
  };

  const handleSearchChange = (value: string) => {
    setSearchInput(value);
    setSelectedIds(new Set());
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      const params = new URLSearchParams(searchParams);
      if (value) {
        params.set("search", value);
      } else {
        params.delete("search");
      }
      params.delete("page");
      setSearchParams(params, { replace: true });
    }, 300);
  };

  const handleViewModeChange = (mode: ViewMode) => {
    setViewMode(mode);
    storeViewMode(mode);
    const params = new URLSearchParams(searchParams);
    params.set("view", mode);
    setSearchParams(params, { replace: true });
  };

  const handleSortChange = (value: string | null) => {
    const params = new URLSearchParams(searchParams);
    if (!value) {
      params.delete("sort_by");
      params.delete("sort_order");
    } else {
      const [by, order] = value.split("-");
      params.set("sort_by", by);
      params.set("sort_order", order);
    }
    setSearchParams(params, { replace: true });
  };

  const loadTasks = useCallback(
    (p: number) => {
      setLoading(true);
      setError(null);
      setSelectedIds(new Set());
      const params: Record<string, string | number | boolean> = { page: p, limit };
      if (filter.folder) params.folder = filter.folder;
      if (filter.tag) params.tag = filter.tag;
      if (filter.is_favorite) params.is_favorite = true;
      if (filter.search) params.search = filter.search;
      if (filter.sort_by) params.sort_by = filter.sort_by;
      if (filter.sort_order) params.sort_order = filter.sort_order;
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
    [t, filter.folder, filter.tag, filter.is_favorite, filter.search, filter.sort_by, filter.sort_order],
  );

  useEffect(() => {
    loadTasks(1);
  }, [loadTasks]);

  // Sync searchInput when URL search param changes externally
  const searchParamValue = searchParams.get("search") || "";
  useEffect(() => {
    if (searchParamValue !== searchInput) setSearchInput(searchParamValue);
    // searchInput intentionally excluded to avoid loop
  }, [searchParamValue]);

  // Escape key clears selection (R4)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && selectedIds.size > 0) {
        setSelectedIds(new Set());
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [selectedIds.size]);

  const handleDelete = async (jobId: string) => {
    if (!await confirm({ title: t("history.deleteConfirm"), destructive: true })) return;
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
    if (!await confirm({ title: t("history.retryConfirm") })) return;
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
    if (!await confirm({ title: t("history.cancelConfirm"), destructive: true })) return;
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
      setSelectedIds(new Set(tasks.map((task) => task.job_id)));
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
  };

  const handleBatchDelete = async () => {
    if (!await confirm({ title: t("history.deleteConfirmCount", { count: selectedIds.size }), destructive: true })) return;
    try {
      await batchDelete({ job_ids: Array.from(selectedIds) });
      setSelectedIds(new Set());
      loadTasks(page);
    } catch {
      setActionError(t("history.deleteFailed"));
    }
  };

  const handleBatchTag = async (tagId: string) => {
    try {
      await batchAddTag({ job_ids: Array.from(selectedIds), tag_id: tagId });
      loadTasks(page);
    } catch {
      setActionError(t("history.actionFailed"));
    }
    setPickerType(null);
  };

  const handleBatchMove = async (folderId: string | null) => {
    try {
      await batchMoveToFolder({ job_ids: Array.from(selectedIds), folder_id: folderId });
      loadTasks(page);
    } catch {
      setActionError(t("history.actionFailed"));
    }
    setPickerType(null);
  };

  const getDisplayTitle = (task: TaskItem) => {
    return task.title || task.video_url || task.file_name || task.message || task.stage;
  };

  // Active filter pills
  const activeFilterPills = useMemo(() => {
    const pills: { key: string; label: string; onRemove: () => void }[] = [];
    if (filter.folder) {
      const name = findFolderName(filter.folder);
      pills.push({
        key: "folder",
        label: name || filter.folder,
        onRemove: () => removeFilter("folder"),
      });
    }
    if (filter.tag) {
      const name = findTagName(filter.tag);
      pills.push({
        key: "tag",
        label: name || filter.tag,
        onRemove: () => removeFilter("tag"),
      });
    }
    if (filter.is_favorite) {
      pills.push({
        key: "is_favorite",
        label: t("contentSidebar.favorites"),
        onRemove: () => removeFilter("is_favorite"),
      });
    }
    return pills;
    // removeFilter and findFolderName/findTagName are stable via useCallback
  }, [filter.folder, filter.tag, filter.is_favorite, allTags, allFolders, t]);

  // Context menu items for a task
  const getContextMenuItems = (task: TaskItem) => {
    const items: { label: string; icon: React.ReactNode; onClick: () => void; variant?: "destructive" }[] = [];
    items.push({
      label: t("history.select"),
      icon: selectedIds.has(task.job_id) ? <CheckSquare size={14} /> : <Square size={14} />,
      onClick: () => toggleSelect(task.job_id),
    });
    if (isActiveTask(task)) {
      items.push({
        label: t("history.cancel"),
        icon: <Ban size={14} />,
        onClick: () => void handleCancel(task.job_id),
      });
    }
    if (isRetriable(task)) {
      items.push({
        label: t("history.retry"),
        icon: <RotateCcw size={14} />,
        onClick: () => void handleRetry(task.job_id),
      });
    }
    items.push({
      label: t("history.delete"),
      icon: <Trash2 size={14} />,
      onClick: () => void handleDelete(task.job_id),
      variant: "destructive",
    });
    return items;
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
    <div className="space-y-4">
      {/* Sheet sidebar */}
      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent side="left" className="p-0 w-72">
          <SheetHeader className="p-4 pb-0">
            <SheetTitle>{t("history.filter")}</SheetTitle>
          </SheetHeader>
          <div className="p-4 pt-2 overflow-y-auto h-full">
            <ContentSidebar filter={filter} onFilterChange={(f) => { handleFilterChange(f); setSheetOpen(false); }} />
          </div>
        </SheetContent>
      </Sheet>

      {/* Top filter bar */}
      <div className="space-y-2">
        <div className="flex items-center gap-2 flex-wrap">
          {/* Filter sidebar button */}
          <Button
            variant="outline"
            size="icon"
            onClick={() => setSheetOpen(true)}
            title={t("history.openFilter")}
            className="shrink-0"
          >
            <SlidersHorizontal size={16} />
          </Button>

          {/* Search input */}
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <Input
              value={searchInput}
              onChange={(e) => handleSearchChange(e.target.value)}
              placeholder={t("history.search")}
              className="h-8 text-sm"
            />
            {searchInput && (
              <button
                onClick={() => handleSearchChange("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X size={14} />
              </button>
            )}
          </div>

          {/* Sort dropdown */}
          {viewMode === "list" && (
            <Select
              value={sortBy && sortOrder ? `${sortBy}-${sortOrder}` : ""}
              onValueChange={handleSortChange}
            >
              <SelectTrigger className="h-8 w-auto gap-1 text-sm min-w-[140px]">
                <ArrowUpDown size={14} />
                <SelectValue placeholder={t("history.sortDate")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="created_at-desc">{t("history.sortDate")} ({t("history.sortDesc")})</SelectItem>
                <SelectItem value="created_at-asc">{t("history.sortDate")} ({t("history.sortAsc")})</SelectItem>
                <SelectItem value="title-asc">{t("history.sortTitle")} ({t("history.sortAsc")})</SelectItem>
                <SelectItem value="title-desc">{t("history.sortTitle")} ({t("history.sortDesc")})</SelectItem>
              </SelectContent>
            </Select>
          )}

          {/* View toggle */}
          <div className="flex items-center border rounded-md">
            <Button
              variant={viewMode === "card" ? "secondary" : "ghost"}
              size="icon"
              className="h-8 w-8 rounded-r-none"
              onClick={() => handleViewModeChange("card")}
              title={t("history.viewCard")}
            >
              <LayoutGrid size={16} />
            </Button>
            <Button
              variant={viewMode === "list" ? "secondary" : "ghost"}
              size="icon"
              className="h-8 w-8 rounded-l-none"
              onClick={() => handleViewModeChange("list")}
              title={t("history.viewList")}
            >
              <List size={16} />
            </Button>
          </div>
        </div>

        {/* Active filter pills */}
        {activeFilterPills.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap">
            {activeFilterPills.map((pill) => (
              <Badge key={pill.key} variant="secondary" className="gap-1 pl-2 pr-1 py-0.5">
                {pill.label}
                <button
                  onClick={pill.onRemove}
                  className="rounded-full hover:bg-muted-foreground/20 p-0.5"
                >
                  <X size={12} />
                </button>
              </Badge>
            ))}
            <button
              onClick={() => handleFilterChange({})}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              {t("history.deselectAll")}
            </button>
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
      ) : viewMode === "card" ? (
        /* Card view */
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {tasks.map((task) => {
            const clickable = task.stage === "complete";
            const isSelected = selectedIds.has(task.job_id);
            const taskFav = task.is_favorite;
            const ctxItems = getContextMenuItems(task);
            const thumbSrc = task.thumbnail_url
              ? task.thumbnail_url.startsWith("http")
                ? task.thumbnail_url
                : `/api/thumbnails/${task.thumbnail_url}`
              : null;

            return (
              <ContextMenu key={task.job_id}>
                <ContextMenuTrigger>
                  <Card
                    onClick={clickable ? () => navigate(`/app/notes/${task.job_id}`) : undefined}
                    className={cn(
                      "relative transition-all",
                      isSelected && "border-primary/40",
                      clickable ? "cursor-pointer hover:shadow-sm" : "cursor-default",
                    )}
                  >
                    {thumbSrc ? (
                      <img
                        src={thumbSrc}
                        alt=""
                        className="w-full aspect-video object-cover"
                        loading="lazy"
                      />
                    ) : task.source_type === "upload" ? (
                      <div className="w-full aspect-video bg-muted flex items-center justify-center">
                        <FileVideo size={32} className="text-muted-foreground/40" />
                      </div>
                    ) : null}
                    {/* Checkbox - always visible, top-left corner */}
                    <button
                      className={cn(
                        "absolute top-2 left-2 z-10 flex items-center justify-center rounded-md p-1 transition-colors",
                        isSelected
                          ? "bg-primary text-primary-foreground"
                          : "bg-background/80 text-muted-foreground hover:text-foreground",
                      )}
                      onClick={(e: React.MouseEvent) => {
                        e.stopPropagation();
                        e.preventDefault();
                        toggleSelect(task.job_id);
                      }}
                    >
                      {isSelected ? <CheckSquare size={16} /> : <Square size={16} />}
                    </button>
                    <CardContent className="p-4">
                      {/* Favorite star - always visible */}
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
                              : "text-muted-foreground hover:text-yellow-500",
                          )}
                        >
                          <Star size={14} className={taskFav ? "fill-current" : ""} />
                        </Button>
                      </div>

                      {/* Title */}
                      <p className="text-sm font-medium truncate pr-8">{getDisplayTitle(task)}</p>

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

                      {/* Status */}
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
                </ContextMenuTrigger>
                <ContextMenuContent>
                  {ctxItems.map((item, i) => (
                    <span key={item.label}>
                      {i === ctxItems.length - 1 && <ContextMenuSeparator />}
                      <ContextMenuItem
                        variant={item.variant}
                        onClick={item.onClick}
                        className="flex items-center gap-2"
                      >
                        {item.icon}
                        {item.label}
                      </ContextMenuItem>
                    </span>
                  ))}
                </ContextMenuContent>
              </ContextMenu>
            );
          })}
        </div>
      ) : (
        /* List view */
        <div className="rounded-lg border">
          {/* Header row */}
          <div className="grid grid-cols-[32px_1fr_100px_80px_120px_100px_40px] gap-2 px-4 py-2 text-xs font-medium text-muted-foreground border-b bg-muted/30">
            <span></span>
            <span>{t("history.title")}</span>
            <span>{t("history.source")}</span>
            <span>{t("lang.label")}</span>
            <span>{t("history.date")}</span>
            <span>{t("history.status")}</span>
            <span></span>
          </div>
          {tasks.map((task) => {
            const clickable = task.stage === "complete";
            const isSelected = selectedIds.has(task.job_id);
            const taskFav = task.is_favorite;
            const ctxItems = getContextMenuItems(task);

            return (
              <ContextMenu key={task.job_id}>
                <ContextMenuTrigger>
                  <div
                    onClick={clickable ? () => navigate(`/app/notes/${task.job_id}`) : undefined}
                    className={cn(
                      "grid grid-cols-[32px_1fr_100px_80px_120px_100px_40px] gap-2 px-4 py-2.5 items-center text-sm border-b last:border-b-0 transition-colors",
                      isSelected && "bg-primary/5",
                      clickable ? "cursor-pointer hover:bg-muted/50" : "cursor-default",
                    )}
                  >
                    {/* Checkbox */}
                    <button
                      className={cn(
                        "flex items-center justify-center rounded p-0.5 transition-colors",
                        isSelected
                          ? "text-primary"
                          : "text-muted-foreground hover:text-foreground",
                      )}
                      onClick={(e: React.MouseEvent) => {
                        e.stopPropagation();
                        e.preventDefault();
                        toggleSelect(task.job_id);
                      }}
                    >
                      {isSelected ? <CheckSquare size={16} /> : <Square size={16} />}
                    </button>
                    <span className="truncate font-medium">{getDisplayTitle(task)}</span>
                    <span className="truncate">
                      <SourceBadge task={task} />
                    </span>
                    <span className="text-xs text-muted-foreground">{task.language || ""}</span>
                    <span className="text-xs text-muted-foreground">
                      {new Date(task.created_at).toLocaleDateString()}
                    </span>
                    <span>
                      <StatusBadge task={task} />
                    </span>
                    <span>
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
                            : "text-muted-foreground hover:text-yellow-500",
                        )}
                      >
                        <Star size={14} className={taskFav ? "fill-current" : ""} />
                      </Button>
                    </span>
                  </div>
                </ContextMenuTrigger>
                <ContextMenuContent>
                  {ctxItems.map((item, i) => (
                    <span key={item.label}>
                      {i === ctxItems.length - 1 && <ContextMenuSeparator />}
                      <ContextMenuItem
                        variant={item.variant}
                        onClick={item.onClick}
                        className="flex items-center gap-2"
                      >
                        {item.icon}
                        {item.label}
                      </ContextMenuItem>
                    </span>
                  ))}
                </ContextMenuContent>
              </ContextMenu>
            );
          })}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            {t("history.pageInfo", { page, totalPages })} ({total})
          </p>
          <Pagination>
            <PaginationContent>
              <PaginationItem>
                <PaginationPrevious
                  onClick={() => loadTasks(page - 1)}
                  className={cn(page <= 1 && "pointer-events-none opacity-50")}
                  text={t("history.previous")}
                />
              </PaginationItem>
              {getPageNumbers(page, totalPages).map((p, i) =>
                p === "ellipsis" ? (
                  <PaginationItem key={`ellipsis-${i}`}>
                    <PaginationEllipsis />
                  </PaginationItem>
                ) : (
                  <PaginationItem key={p}>
                    <PaginationLink
                      isActive={p === page}
                      onClick={() => loadTasks(p)}
                    >
                      {p}
                    </PaginationLink>
                  </PaginationItem>
                ),
              )}
              <PaginationItem>
                <PaginationNext
                  onClick={() => loadTasks(page + 1)}
                  className={cn(page >= totalPages && "pointer-events-none opacity-50")}
                  text={t("history.next")}
                />
              </PaginationItem>
            </PaginationContent>
          </Pagination>
        </div>
      )}

      {/* Batch action bar */}
      {selectedIds.size > 0 && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 flex items-center gap-3 rounded-lg border border-border bg-background shadow-lg px-4 py-2">
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={() => setSelectedIds(new Set())}
            className="text-muted-foreground hover:text-foreground"
          >
            <X size={16} />
          </Button>
          <span className="text-sm text-muted-foreground">
            {t("history.selected", { count: selectedIds.size })}
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={toggleSelectAll}
            className="text-xs"
          >
            {selectedIds.size === tasks.length ? t("history.deselectAll") : t("history.selectAll")}
          </Button>
          <div className="h-4 w-px bg-border" />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setPickerType("tag")}
            className="gap-1.5 text-xs"
          >
            <Tag size={14} />
            {t("history.batchTag")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setPickerType("folder")}
            className="gap-1.5 text-xs"
          >
            <FolderOpen size={14} />
            {t("history.batchMove")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void handleBatchFavorite(true)}
            className="gap-1.5 text-xs"
          >
            <Star size={14} />
            {t("history.batchFavorite")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void handleBatchFavorite(false)}
            className="gap-1.5 text-xs"
          >
            <Star size={14} className="fill-none" />
            {t("history.batchUnfavorite")}
          </Button>
          <div className="h-4 w-px bg-border" />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void handleBatchDelete()}
            className="gap-1.5 text-xs text-destructive hover:text-destructive"
          >
            <Trash2 size={14} />
            {t("history.batchDelete")}
          </Button>
        </div>
      )}

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
                  className="w-2.5 h-2.5 rounded-full shrink-0 bg-[var(--tag-color)]"
                  style={{ "--tag-color": tag.color || "#6b7280" } as React.CSSProperties}
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
          className="w-full text-left flex items-center gap-2 rounded-lg py-1.5 text-sm hover:bg-muted transition-colors pl-[var(--depth-pad)]"
          style={{ "--depth-pad": `${depth * 16 + 8}px` } as React.CSSProperties}
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
