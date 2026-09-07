import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FolderOpen, Plus, Tag, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import type { Tag as TagType, TagWithCount, FolderTreeNode } from "@/types";

interface NoteMetaPopoverProps {
  noteTags: TagType[];
  allTags: TagWithCount[];
  folderTree: FolderTreeNode[];
  folderId: string | null;
  onAddTag: (name: string) => void;
  onRemoveTag: (tagId: string) => void;
  onMoveToFolder: (folderId: string | null) => void;
}

export function NoteMetaPopover({
  noteTags,
  allTags,
  folderTree,
  folderId,
  onAddTag,
  onRemoveTag,
  onMoveToFolder,
}: NoteMetaPopoverProps) {
  const { t } = useTranslation();
  const [tagInputOpen, setTagInputOpen] = useState(false);
  const [tagInputValue, setTagInputValue] = useState("");

  const existingTagIds = new Set(noteTags.map((tag) => tag.id));
  const suggestedTags = allTags
    .filter((tag) => !existingTagIds.has(tag.id))
    .filter((tag) => tag.name.toLowerCase().includes(tagInputValue.toLowerCase()))
    .slice(0, 5);

  const handleAddTag = () => {
    if (!tagInputValue.trim()) return;
    onAddTag(tagInputValue.trim());
    setTagInputValue("");
    setTagInputOpen(false);
  };

  const handleTagInputKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleAddTag();
    else if (e.key === "Escape") {
      setTagInputOpen(false);
      setTagInputValue("");
    }
  };

  const folderName = folderId
    ? findFolderName(folderTree, folderId)
    : null;

  return (
    <Popover>
      <PopoverTrigger
        render={(props: React.HTMLAttributes<HTMLButtonElement>) => (
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("noteDetail.noteInfo")}
            className="relative"
            {...props}
          >
            <Tag />
            {noteTags.length > 0 && (
              <span className="absolute -top-0.5 -right-0.5 min-w-4 h-4 px-0.5 rounded-full bg-primary text-primary-foreground text-[10px] leading-4 flex items-center justify-center">
                {noteTags.length}
              </span>
            )}
          </Button>
        )}
      />
      <PopoverContent align="end" className="w-80">
        {/* Tags section */}
        <div className="space-y-1.5">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            {t("noteDetail.tags")}
          </span>
          <div className="flex items-center gap-1.5 flex-wrap">
            {noteTags.map((tag) => (
              <span
                key={tag.id}
                className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-0.5 text-xs"
              >
                <span
                  className="w-2 h-2 rounded-full shrink-0 bg-[var(--tag-color)]"
                  style={{ "--tag-color": tag.color || "#6b7280" } as React.CSSProperties}
                />
                {tag.name}
                <button
                  onClick={() => onRemoveTag(tag.id)}
                  aria-label={t("noteDetail.removeTag", { name: tag.name })}
                  className="p-0.5 rounded hover:bg-muted text-muted-foreground hover:text-destructive"
                >
                  <X size={10} />
                </button>
              </span>
            ))}
            {tagInputOpen ? (
              <div className="relative">
                <input
                  type="text"
                  value={tagInputValue}
                  onChange={(e) => setTagInputValue(e.target.value)}
                  onKeyDown={handleTagInputKeyDown}
                  onBlur={() => {
                    if (!tagInputValue) setTagInputOpen(false);
                  }}
                  placeholder={t("noteDetail.addTag")}
                  className="rounded-full border border-border px-2.5 py-0.5 text-xs bg-background focus:outline-none focus:ring-1 focus:ring-primary w-28"
                  autoFocus
                />
                {tagInputValue && suggestedTags.length > 0 && (
                  <div className="absolute top-full left-0 mt-1 z-10 w-40 rounded-lg border border-border bg-background shadow-lg py-1 max-h-32 overflow-y-auto">
                    {suggestedTags.map((tag) => (
                      <button
                        key={tag.id}
                        onMouseDown={(e) => {
                          e.preventDefault();
                          setTagInputValue(tag.name);
                        }}
                        className="w-full text-left flex items-center gap-2 px-2 py-1 text-xs hover:bg-muted"
                      >
                        <span
                          className="w-2 h-2 rounded-full shrink-0 bg-[var(--tag-color)]"
                          style={{ "--tag-color": tag.color || "#6b7280" } as React.CSSProperties}
                        />
                        {tag.name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <button
                onClick={() => setTagInputOpen(true)}
                className="inline-flex items-center gap-1 rounded-full border border-dashed border-border px-2.5 py-0.5 text-xs text-muted-foreground hover:text-foreground hover:border-primary/50 transition-colors"
              >
                <Plus size={10} />
                {t("noteDetail.addTag")}
              </button>
            )}
          </div>
        </div>

        {/* Folder section */}
        <div className="space-y-1.5 pt-1">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            {t("noteDetail.folder")}
          </span>
          <div className="rounded-lg border border-border max-h-60 overflow-y-auto py-1">
            <button
              onClick={() => onMoveToFolder(null)}
              className={cn(
                "w-full text-left flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-muted",
                !folderId && "bg-accent text-accent-foreground"
              )}
            >
              <FolderOpen size={14} className="shrink-0" />
              {t("history.noFolder")}
            </button>
            {renderFolderNodes(folderTree, 0, folderId, onMoveToFolder)}
          </div>
          {folderName && (
            <p className="text-xs text-muted-foreground">
              {t("noteDetail.currentFolder", { name: folderName })}
            </p>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

function findFolderName(
  nodes: FolderTreeNode[],
  id: string,
): string | null {
  for (const node of nodes) {
    if (node.id === id) return node.name;
    const found = findFolderName(node.children, id);
    if (found) return found;
  }
  return null;
}

function renderFolderNodes(
  nodes: FolderTreeNode[],
  depth: number,
  selectedId: string | null,
  onPick: (id: string | null) => void,
): React.ReactNode {
  return nodes.map((node) => (
    <div key={node.id}>
      <button
        onClick={() => onPick(node.id)}
        className={cn(
          "w-full text-left flex items-center gap-2 py-1.5 pr-3 text-sm hover:bg-muted pl-[var(--depth-pad)]",
          node.id === selectedId && "bg-accent text-accent-foreground"
        )}
        style={{ "--depth-pad": `${depth * 16 + 12}px` } as React.CSSProperties}
      >
        <FolderOpen size={14} className="shrink-0" />
        {node.name}
      </button>
      {node.children.length > 0 &&
        renderFolderNodes(node.children, depth + 1, selectedId, onPick)}
    </div>
  ));
}
