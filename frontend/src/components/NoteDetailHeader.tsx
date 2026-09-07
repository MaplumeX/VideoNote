import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import {
  ArrowLeft,
  Check,
  Download,
  Ellipsis,
  ListTree,
  Loader2,
  Play,
  Star,
  TriangleAlert,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { NoteMetaPopover } from "@/components/NoteMetaPopover";
import { cn } from "@/lib/utils";
import type { Tag as TagType, TagWithCount, FolderTreeNode } from "@/types";

interface NoteDetailHeaderProps {
  title: string;
  platform: string | null;
  fileName: string | null;
  createdAt: string | null;
  saving: boolean;
  saveError: boolean;
  hasUnsavedChanges: boolean;
  isFavorite: boolean;
  hasVideo: boolean;
  noteTags: TagType[];
  allTags: TagWithCount[];
  folderTree: FolderTreeNode[];
  folderId: string | null;
  onToggleFavorite: () => void;
  onDownload: () => void;
  onPlayVideo: () => void;
  onAddTag: (name: string) => void;
  onRemoveTag: (tagId: string) => void;
  onMoveToFolder: (folderId: string | null) => void;
  onOpenToc: () => void;
}

type TooltipRender =
  React.ComponentProps<typeof TooltipTrigger>["render"];

function HeaderTooltip({
  label,
  render,
}: {
  label: string;
  render: TooltipRender;
}) {
  return (
    <Tooltip>
      <TooltipTrigger render={render} />
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

function SaveStatus({
  saving,
  saveError,
  hasUnsavedChanges,
}: {
  saving: boolean;
  saveError: boolean;
  hasUnsavedChanges: boolean;
}) {
  const { t } = useTranslation();
  if (saving) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <Loader2 size={14} className="animate-spin" />
        {t("noteDetail.saving")}
      </span>
    );
  }
  if (saveError) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-destructive">
        <TriangleAlert size={14} />
        {t("noteDetail.saveFailed")}
      </span>
    );
  }
  if (hasUnsavedChanges) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <TriangleAlert size={14} />
        {t("noteDetail.unsaved")}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      <Check size={14} />
      {t("noteDetail.saved")}
    </span>
  );
}

export function NoteDetailHeader({
  title,
  platform,
  fileName,
  createdAt,
  saving,
  saveError,
  hasUnsavedChanges,
  isFavorite,
  hasVideo,
  noteTags,
  allTags,
  folderTree,
  folderId,
  onToggleFavorite,
  onDownload,
  onPlayVideo,
  onAddTag,
  onRemoveTag,
  onMoveToFolder,
  onOpenToc,
}: NoteDetailHeaderProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const createdLabel = createdAt
    ? new Date(createdAt).toLocaleString()
    : null;

  const metaItems: string[] = [];
  if (platform) metaItems.push(platform);
  if (fileName) metaItems.push(fileName);
  if (createdLabel) metaItems.push(createdLabel);

  const favoriteButton = (props: React.HTMLAttributes<HTMLButtonElement>) => (
    <Button
      variant="ghost"
      size="icon"
      aria-label={isFavorite ? t("noteDetail.unfavorite") : t("noteDetail.favorite")}
      {...props}
      onClick={(e) => {
        props.onClick?.(e);
        onToggleFavorite();
      }}
    >
      <Star className={cn(isFavorite && "fill-current text-yellow-500")} />
    </Button>
  );

  const downloadButton = (props: React.HTMLAttributes<HTMLButtonElement>) => (
    <Button
      variant="ghost"
      size="icon"
      aria-label={t("noteDetail.download")}
      {...props}
      onClick={(e) => {
        props.onClick?.(e);
        onDownload();
      }}
    >
      <Download />
    </Button>
  );

  const playButton = (props: React.HTMLAttributes<HTMLButtonElement>) => (
    <Button
      variant="ghost"
      size="icon"
      aria-label={t("noteDetail.playVideo")}
      {...props}
      onClick={(e) => {
        props.onClick?.(e);
        onPlayVideo();
      }}
    >
      <Play />
    </Button>
  );

  const tocButton = (props: React.HTMLAttributes<HTMLButtonElement>) => (
    <Button
      variant="ghost"
      size="icon"
      aria-label={t("noteDetail.toc")}
      className="xl:hidden"
      {...props}
      onClick={(e) => {
        props.onClick?.(e);
        onOpenToc();
      }}
    >
      <ListTree />
    </Button>
  );

  return (
    <header className="sticky top-0 z-20 -mx-4 md:-mx-6 mb-6 bg-background/95 backdrop-blur px-4 md:px-6 pt-2 pb-3 border-b border-border">
      <div className="flex items-start gap-2">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => navigate("/app/history")}
          aria-label={t("noteDetail.backToHistory")}
          className="shrink-0 mt-1"
        >
          <ArrowLeft />
        </Button>

        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-semibold leading-tight line-clamp-2 break-words">
            {title || t("note.untitled")}
          </h1>
          {metaItems.length > 0 && (
            <p className="mt-1 text-xs text-muted-foreground truncate">
              {metaItems.join(" · ")}
            </p>
          )}
        </div>

        {/* Save status + actions — inline on ≥lg */}
        <div className="hidden lg:flex items-center gap-1.5 shrink-0 mt-1">
          <SaveStatus
            saving={saving}
            saveError={saveError}
            hasUnsavedChanges={hasUnsavedChanges}
          />
          <HeaderTooltip label={t("noteDetail.toc")} render={tocButton} />
          <HeaderTooltip
            label={isFavorite ? t("noteDetail.unfavorite") : t("noteDetail.favorite")}
            render={favoriteButton}
          />
          {hasVideo && (
            <HeaderTooltip label={t("noteDetail.playVideo")} render={playButton} />
          )}
          <HeaderTooltip label={t("noteDetail.download")} render={downloadButton} />
          <NoteMetaPopover
            noteTags={noteTags}
            allTags={allTags}
            folderTree={folderTree}
            folderId={folderId}
            onAddTag={onAddTag}
            onRemoveTag={onRemoveTag}
            onMoveToFolder={onMoveToFolder}
          />
        </div>

        {/* Compact actions on <lg */}
        <div className="flex lg:hidden items-center gap-1 shrink-0 mt-1">
          <SaveStatus
            saving={saving}
            saveError={saveError}
            hasUnsavedChanges={hasUnsavedChanges}
          />
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("noteDetail.toc")}
            className="xl:hidden"
            onClick={onOpenToc}
          >
            <ListTree />
          </Button>
          <NoteMetaPopover
            noteTags={noteTags}
            allTags={allTags}
            folderTree={folderTree}
            folderId={folderId}
            onAddTag={onAddTag}
            onRemoveTag={onRemoveTag}
            onMoveToFolder={onMoveToFolder}
          />
          <DropdownMenu>
            <DropdownMenuTrigger
              render={(props: React.HTMLAttributes<HTMLButtonElement>) => (
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={t("noteDetail.moreActions")}
                  {...props}
                >
                  <Ellipsis />
                </Button>
              )}
            />
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={onToggleFavorite}>
                <Star className={cn(isFavorite && "fill-current text-yellow-500")} />
                {isFavorite ? t("noteDetail.unfavorite") : t("noteDetail.favorite")}
              </DropdownMenuItem>
              {hasVideo && (
                <DropdownMenuItem onClick={onPlayVideo}>
                  <Play />
                  {t("noteDetail.playVideo")}
                </DropdownMenuItem>
              )}
              <DropdownMenuItem onClick={onDownload}>
                <Download />
                {t("noteDetail.download")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  );
}
