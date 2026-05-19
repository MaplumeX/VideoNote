import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  FolderOpen,
  Star,
  Folder,
  ChevronRight,
  ChevronDown,
  Plus,
  Pencil,
  Trash2,
  X,
  Check,
  Inbox,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  fetchTags,
  fetchFolderTree,
  createTag,
  updateTag,
  deleteTag,
  createFolder,
  updateFolder,
  deleteFolder,
} from "@/api/client";
import type { TagWithCount, FolderTreeNode, HistoryFilter } from "@/types";

interface ContentSidebarProps {
  filter: HistoryFilter;
  onFilterChange: (filter: HistoryFilter) => void;
}

type EditState =
  | { type: "none" }
  | { type: "creating-tag" }
  | { type: "creating-folder"; parentId: string | null }
  | { type: "renaming-tag"; id: string }
  | { type: "renaming-folder"; id: string };

export function ContentSidebar({ filter, onFilterChange }: ContentSidebarProps) {
  const { t } = useTranslation();
  const [tags, setTags] = useState<TagWithCount[]>([]);
  const [folders, setFolders] = useState<FolderTreeNode[]>([]);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
  const [editState, setEditState] = useState<EditState>({ type: "none" });
  const [editValue, setEditValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [tagsData, foldersData] = await Promise.all([fetchTags(), fetchFolderTree()]);
      setTags(tagsData);
      setFolders(foldersData);
      // Auto-expand all folders on first load
      const allIds = new Set<string>();
      function collectIds(nodes: FolderTreeNode[]) {
        for (const node of nodes) {
          if (node.children.length > 0) {
            allIds.add(node.id);
            collectIds(node.children);
          }
        }
      }
      collectIds(foldersData);
      setExpandedFolders(allIds);
    } catch {
      // silent fail
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleCreateTag = async () => {
    if (!editValue.trim()) return;
    try {
      await createTag(editValue.trim());
      setEditState({ type: "none" });
      setEditValue("");
      await loadData();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("contentSidebar.createFailed"));
    }
  };

  const handleCreateFolder = async (parentId: string | null) => {
    if (!editValue.trim()) return;
    try {
      await createFolder(editValue.trim(), parentId || undefined);
      setEditState({ type: "none" });
      setEditValue("");
      await loadData();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("contentSidebar.createFailed"));
    }
  };

  const handleRenameTag = async (id: string) => {
    if (!editValue.trim()) return;
    try {
      await updateTag(id, { name: editValue.trim() });
      setEditState({ type: "none" });
      setEditValue("");
      await loadData();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("contentSidebar.renameFailed"));
    }
  };

  const handleRenameFolder = async (id: string) => {
    if (!editValue.trim()) return;
    try {
      await updateFolder(id, { name: editValue.trim() });
      setEditState({ type: "none" });
      setEditValue("");
      await loadData();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("contentSidebar.renameFailed"));
    }
  };

  const handleDeleteTag = async (id: string, name: string) => {
    if (!window.confirm(t("contentSidebar.deleteTagConfirm", { name }))) return;
    try {
      await deleteTag(id);
      // If currently filtering by this tag, clear filter
      if (filter.tag === id) {
        onFilterChange({});
      }
      await loadData();
    } catch {
      setError(t("contentSidebar.deleteFailed"));
    }
  };

  const handleDeleteFolder = async (id: string, name: string) => {
    if (!window.confirm(t("contentSidebar.deleteFolderConfirm", { name }))) return;
    try {
      await deleteFolder(id);
      if (filter.folder === id) {
        onFilterChange({});
      }
      await loadData();
    } catch {
      setError(t("contentSidebar.deleteFailed"));
    }
  };

  const toggleFolder = (id: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const isFilterActive = (key: keyof HistoryFilter, value?: string) => {
    if (key === "is_favorite") return filter.is_favorite === true;
    if (key === "folder") return filter.folder === value;
    if (key === "tag") return filter.tag === value;
    return false;
  };

  const startCreatingTag = () => {
    setEditState({ type: "creating-tag" });
    setEditValue("");
  };

  const startCreatingFolder = (parentId: string | null) => {
    setEditState({ type: "creating-folder", parentId });
    setEditValue("");
  };

  const startRenamingTag = (id: string, currentName: string) => {
    setEditState({ type: "renaming-tag", id });
    setEditValue(currentName);
  };

  const startRenamingFolder = (id: string, currentName: string) => {
    setEditState({ type: "renaming-folder", id });
    setEditValue(currentName);
  };

  const submitEdit = () => {
    if (editState.type === "creating-tag") handleCreateTag();
    else if (editState.type === "creating-folder") handleCreateFolder(editState.parentId);
    else if (editState.type === "renaming-tag") handleRenameTag(editState.id);
    else if (editState.type === "renaming-folder") handleRenameFolder(editState.id);
  };

  const cancelEdit = () => {
    setEditState({ type: "none" });
    setEditValue("");
    setError(null);
  };

  const handleEditKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") submitEdit();
    else if (e.key === "Escape") cancelEdit();
  };

  const EditRow = () => (
    <div className="flex items-center gap-1 px-2 py-1">
      <input
        type="text"
        value={editValue}
        onChange={(e) => setEditValue(e.target.value)}
        onKeyDown={handleEditKeyDown}
        placeholder={
          editState.type === "creating-tag" || editState.type === "renaming-tag"
            ? t("contentSidebar.tagNamePlaceholder")
            : t("contentSidebar.folderNamePlaceholder")
        }
        className="flex-1 min-w-0 rounded border border-border px-2 py-0.5 text-xs bg-background focus:outline-none focus:ring-1 focus:ring-primary"
        autoFocus
      />
      <button onClick={submitEdit} className="p-0.5 rounded hover:bg-muted text-green-600">
        <Check size={14} />
      </button>
      <button onClick={cancelEdit} className="p-0.5 rounded hover:bg-muted text-muted-foreground">
        <X size={14} />
      </button>
    </div>
  );

  const FolderNode = ({ node, depth }: { node: FolderTreeNode; depth: number }) => {
    const hasChildren = node.children.length > 0;
    const isExpanded = expandedFolders.has(node.id);
    const isEditing = editState.type === "renaming-folder" && editState.id === node.id;
    const isCreating = editState.type === "creating-folder" && editState.parentId === node.id;

    return (
      <div>
        <div
          className={cn(
            "group flex items-center gap-1 rounded-lg px-2 py-1.5 text-sm transition-colors cursor-pointer",
            isFilterActive("folder", node.id)
              ? "bg-muted font-medium text-foreground"
              : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
          )}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
        >
          <button
            onClick={() => toggleFolder(node.id)}
            className="p-0.5 shrink-0"
          >
            {hasChildren ? (
              isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />
            ) : (
              <span className="w-3.5" />
            )}
          </button>
          <Folder size={14} className="shrink-0" />
          {isEditing ? (
            <div className="flex-1 min-w-0 flex items-center gap-1">
              <input
                type="text"
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onKeyDown={handleEditKeyDown}
                className="flex-1 min-w-0 rounded border border-border px-1.5 py-0 text-xs bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                autoFocus
                onClick={(e) => e.stopPropagation()}
              />
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  submitEdit();
                }}
                className="p-0.5 rounded hover:bg-muted text-green-600"
              >
                <Check size={12} />
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  cancelEdit();
                }}
                className="p-0.5 rounded hover:bg-muted text-muted-foreground"
              >
                <X size={12} />
              </button>
            </div>
          ) : (
            <>
              <span
                className="flex-1 truncate"
                onClick={() => onFilterChange({ folder: node.id })}
              >
                {node.name}
              </span>
              {node.note_count > 0 && (
                <span className="text-xs text-muted-foreground/60 shrink-0">{node.note_count}</span>
              )}
              <div className="hidden group-hover:flex items-center gap-0.5 shrink-0">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    startRenamingFolder(node.id, node.name);
                  }}
                  className="p-0.5 rounded hover:bg-muted"
                  title={t("contentSidebar.rename")}
                >
                  <Pencil size={12} />
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    startCreatingFolder(node.id);
                  }}
                  className="p-0.5 rounded hover:bg-muted"
                  title={t("contentSidebar.newFolder")}
                >
                  <Plus size={12} />
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    void handleDeleteFolder(node.id, node.name);
                  }}
                  className="p-0.5 rounded hover:bg-muted hover:text-destructive"
                  title={t("contentSidebar.delete")}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </>
          )}
        </div>

        {isCreating && <EditRow />}

        {hasChildren && isExpanded && (
          <div>
            {node.children.map((child) => (
              <FolderNode key={child.id} node={child} depth={depth + 1} />
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-3 py-2 text-xs text-destructive">
          {error}
          <button onClick={() => setError(null)} className="ml-2 underline">
            <X size={12} className="inline" />
          </button>
        </div>
      )}

      {/* Special items */}
      <div className="space-y-0.5">
        <button
          onClick={() => onFilterChange({})}
          className={cn(
            "w-full flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm transition-colors",
            !filter.folder && !filter.tag && filter.is_favorite === undefined
              ? "bg-muted font-medium text-foreground"
              : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
          )}
        >
          <Inbox size={16} />
          {t("contentSidebar.allNotes")}
        </button>

        <button
          onClick={() => onFilterChange({ is_favorite: true })}
          className={cn(
            "w-full flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm transition-colors",
            isFilterActive("is_favorite")
              ? "bg-muted font-medium text-foreground"
              : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
          )}
        >
          <Star size={16} />
          {t("contentSidebar.favorites")}
        </button>

        <button
          onClick={() => onFilterChange({ folder: "none" })}
          className={cn(
            "w-full flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm transition-colors",
            filter.folder === "none"
              ? "bg-muted font-medium text-foreground"
              : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
          )}
        >
          <FolderOpen size={16} />
          {t("contentSidebar.uncategorized")}
        </button>
      </div>

      {/* Folders section */}
      <div>
        <div className="flex items-center justify-between px-2 mb-1">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            {t("contentSidebar.folders")}
          </span>
          <button
            onClick={() => startCreatingFolder(null)}
            className="p-0.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
            title={t("contentSidebar.newFolder")}
          >
            <Plus size={14} />
          </button>
        </div>

        {editState.type === "creating-folder" && editState.parentId === null && <EditRow />}

        <div className="space-y-0.5">
          {folders.map((node) => (
            <FolderNode key={node.id} node={node} depth={0} />
          ))}
        </div>
      </div>

      {/* Tags section */}
      <div>
        <div className="flex items-center justify-between px-2 mb-1">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            {t("contentSidebar.tags")}
          </span>
          <button
            onClick={startCreatingTag}
            className="p-0.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
            title={t("contentSidebar.newTag")}
          >
            <Plus size={14} />
          </button>
        </div>

        {editState.type === "creating-tag" && <EditRow />}

        <div className="space-y-0.5">
          {tags.map((tag) => {
            const isEditing = editState.type === "renaming-tag" && editState.id === tag.id;
            return (
              <div
                key={tag.id}
                className={cn(
                  "group flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors cursor-pointer",
                  isFilterActive("tag", tag.id)
                    ? "bg-muted font-medium text-foreground"
                    : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                )}
              >
                <span
                  className="shrink-0 w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: tag.color || "#6b7280" }}
                />
                {isEditing ? (
                  <div className="flex-1 min-w-0 flex items-center gap-1">
                    <input
                      type="text"
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      onKeyDown={handleEditKeyDown}
                      className="flex-1 min-w-0 rounded border border-border px-1.5 py-0 text-xs bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                      autoFocus
                      onClick={(e) => e.stopPropagation()}
                    />
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        submitEdit();
                      }}
                      className="p-0.5 rounded hover:bg-muted text-green-600"
                    >
                      <Check size={12} />
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        cancelEdit();
                      }}
                      className="p-0.5 rounded hover:bg-muted text-muted-foreground"
                    >
                      <X size={12} />
                    </button>
                  </div>
                ) : (
                  <>
                    <span
                      className="flex-1 truncate"
                      onClick={() => onFilterChange({ tag: tag.id })}
                    >
                      {tag.name}
                    </span>
                    {tag.note_count > 0 && (
                      <span className="text-xs text-muted-foreground/60 shrink-0">
                        {tag.note_count}
                      </span>
                    )}
                    <div className="hidden group-hover:flex items-center gap-0.5 shrink-0">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          startRenamingTag(tag.id, tag.name);
                        }}
                        className="p-0.5 rounded hover:bg-muted"
                        title={t("contentSidebar.rename")}
                      >
                        <Pencil size={12} />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          void handleDeleteTag(tag.id, tag.name);
                        }}
                        className="p-0.5 rounded hover:bg-muted hover:text-destructive"
                        title={t("contentSidebar.delete")}
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
