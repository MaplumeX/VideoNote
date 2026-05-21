import { useEffect, useState, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useParams, Link } from "react-router";
import {
  Download,
  ChevronRight,
  Star,
  Tag,
  FolderOpen,
  X,
  Plus,
  Play,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { fetchResult, fetchTags, fetchFolderTree, fetchTaskById, fetchNoteTags, addTagsToNote, removeTagFromNote, moveNoteToFolder, toggleFavorite, updateNoteContent } from "@/api/client";
import { useSSE } from "@/hooks/useSSE";
import { StepIndicator } from "@/components/StepIndicator";
import { NoteEditor } from "@/components/NoteEditor";
import { TableOfContents } from "@/components/TableOfContents";
import { VideoPlayerFloat } from "@/components/VideoPlayerFloat";
import type { VideoPlayerFloatHandle } from "@/components/VideoPlayerFloat";
import type { NoteResult, Tag as TagType, TagWithCount, FolderTreeNode } from "@/types";

export function NoteDetailPage() {
  const { t } = useTranslation();
  const { id: jobId } = useParams<{ id: string }>();
  const [note, setNote] = useState<NoteResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isFavorite, setIsFavorite] = useState(false);
  const [noteTags, setNoteTags] = useState<TagType[]>([]);
  const [folderId, setFolderId] = useState<string | null>(null);
  const [folderName, setFolderName] = useState<string | null>(null);
  const [tagInputOpen, setTagInputOpen] = useState(false);
  const [tagInputValue, setTagInputValue] = useState("");
  const [folderPickerOpen, setFolderPickerOpen] = useState(false);
  const [allTags, setAllTags] = useState<TagWithCount[]>([]);
  const [folderTree, setFolderTree] = useState<FolderTreeNode[]>([]);

  const [editMarkdown, setEditMarkdown] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const [editorResetKey, setEditorResetKey] = useState(0);
  const autoSaveTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const editMarkdownRef = useRef(editMarkdown);
  const lastSavedMarkdownRef = useRef("");
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [platform, setPlatform] = useState<string | null>(null);
  const [playerOpen, setPlayerOpen] = useState(false);
  const playerRef = useRef<VideoPlayerFloatHandle>(null);

  const previewRef = useRef<HTMLDivElement>(null);

  const { progress, result: sseResult, error: sseError } = useSSE(processing && jobId ? jobId : null);

  const hasUnsavedChanges = note !== null && editMarkdown !== lastSavedMarkdownRef.current;

  // Keep ref in sync so async callbacks (debounce auto-save) always read latest value
  useEffect(() => {
    editMarkdownRef.current = editMarkdown;
  }, [editMarkdown]);

  useEffect(() => {
    if (!jobId) return;

    setLoading(true);
    setEditorResetKey((k) => k + 1);
    fetchResult(jobId)
      .then((data) => {
        setNote(data);
        setEditMarkdown(data.markdown);
        lastSavedMarkdownRef.current = data.markdown;
        setLoading(false);
      })
      .catch((err) => {
        if (err.message === "Still processing") {
          setProcessing(true);
          setLoading(false);
        } else {
          setError(err.message || "Failed to load note");
          setLoading(false);
        }
      });
  }, [jobId]);

  useEffect(() => {
    if (!jobId) return;

    fetchNoteTags(jobId)
      .then((tags) => {
        setNoteTags(tags);
      })
      .catch(() => {
        setNoteTags([]);
      });

    fetchTaskById(jobId)
      .then((task) => {
        setIsFavorite(task.is_favorite);
        setFolderId(task.folder_id);
        setVideoUrl(task.video_url);
        setPlatform(task.platform);
      })
      .catch(() => {});

    fetchTags().then(setAllTags).catch(() => {});
    fetchFolderTree().then(setFolderTree).catch(() => {});
  }, [jobId]);

  useEffect(() => {
    if (!folderId) {
      setFolderName(null);
      return;
    }
    const findFolder = (nodes: FolderTreeNode[], id: string): string | null => {
      for (const node of nodes) {
        if (node.id === id) return node.name;
        const found = findFolder(node.children, id);
        if (found) return found;
      }
      return null;
    };
    setFolderName(findFolder(folderTree, folderId));
  }, [folderId, folderTree]);

  useEffect(() => {
    if (progress?.stage === "failed" && processing) {
      setError(progress.message || "Processing failed");
      setProcessing(false);
    }
    if (progress?.stage === "cancelled" && processing) {
      setError("Task cancelled");
      setProcessing(false);
    }
  }, [progress?.stage, processing]);

  useEffect(() => {
    if (sseResult && processing && jobId) {
      fetchResult(jobId)
        .then((data) => {
          setNote(data);
          setEditMarkdown(data.markdown);
          lastSavedMarkdownRef.current = data.markdown;
          setEditorResetKey((k) => k + 1);
          setProcessing(false);
        })
        .catch(() => {
          setError("Failed to load note");
          setProcessing(false);
        });
    }
  }, [sseResult, processing, jobId]);

  useEffect(() => {
    if (sseError && processing) {
      setError(sseError);
      setProcessing(false);
    }
  }, [sseError, processing]);

  const handleSave = useCallback(async () => {
    if (!jobId || !hasUnsavedChanges || saving) return;
    setSaving(true);
    setSaveError(false);
    try {
      const savedNote = await updateNoteContent(jobId, { markdown: editMarkdownRef.current });
      setNote(savedNote);
      lastSavedMarkdownRef.current = editMarkdownRef.current;
      setSaving(false);
    } catch {
      setSaving(false);
      setSaveError(true);
    }
  }, [jobId, hasUnsavedChanges, saving]);

  const handleEditorChange = useCallback((value: string) => {
    editMarkdownRef.current = value;
    setEditMarkdown(value);
    if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current);
    autoSaveTimerRef.current = setTimeout(() => {
      void handleSave();
    }, 1500);
  }, [handleSave]);

  // Clean up debounce timer on note switch or unmount
  useEffect(() => {
    return () => {
      if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current);
    };
  }, [jobId]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        if (hasUnsavedChanges) {
          if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current);
          handleSave();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [hasUnsavedChanges, handleSave]);

  const handleDownload = () => {
    if (!note) return;
    const blob = new Blob([note.markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${note.title || "videonote"}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleToggleFavorite = async () => {
    if (!jobId) return;
    try {
      await toggleFavorite(jobId, { is_favorite: !isFavorite });
      setIsFavorite(!isFavorite);
    } catch {
      // silent
    }
  };

  const handleAddTag = async () => {
    if (!jobId || !tagInputValue.trim()) return;
    try {
      const result = await addTagsToNote(jobId, { tag_names: [tagInputValue.trim()] });
      setNoteTags(result.tags);
      setTagInputValue("");
      setTagInputOpen(false);
      fetchTags().then(setAllTags).catch(() => {});
    } catch {
      // silent
    }
  };

  const handleRemoveTag = async (tagId: string) => {
    if (!jobId) return;
    try {
      await removeTagFromNote(jobId, tagId);
      setNoteTags((prev) => prev.filter((tag) => tag.id !== tagId));
    } catch {
      // silent
    }
  };

  const handleMoveToFolder = async (newFolderId: string | null) => {
    if (!jobId) return;
    try {
      await moveNoteToFolder(jobId, { folder_id: newFolderId });
      setFolderId(newFolderId);
      setFolderPickerOpen(false);
    } catch {
      // silent
    }
  };

  const handleTagInputKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleAddTag();
    else if (e.key === "Escape") {
      setTagInputOpen(false);
      setTagInputValue("");
    }
  };

  const existingTagIds = new Set(noteTags.map((tag) => tag.id));
  const suggestedTags = allTags.filter((tag) => !existingTagIds.has(tag.id));

  const hasVideo = !!(videoUrl && platform && (platform === "youtube" || platform === "bilibili"));

  const handleTimestampClick = useCallback((seconds: number) => {
    if (!hasVideo) return;
    if (!playerOpen) setPlayerOpen(true);
    // Defer seek so the player ref is available after render
    setTimeout(() => playerRef.current?.seekTo(seconds), 0);
  }, [hasVideo, playerOpen]);

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

  if (processing) {
    return (
      <div className="flex justify-center pt-12">
        <StepIndicator stage={progress?.stage ?? null} progress={progress?.progress ?? 0} />
      </div>
    );
  }

  if (!note) return null;

  return (
    <div className="flex gap-6 h-full">
      {/* Left sidebar — actions, tags, folder */}
      <aside className="w-56 shrink-0 space-y-5 sticky top-0 self-start">
        {/* Breadcrumb */}
        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <Link to="/app/history" className="hover:text-foreground transition-colors">
            {t("sidebar.history")}
          </Link>
          <ChevronRight size={14} />
          <span className="text-foreground truncate">{note.title || t("note.untitled")}</span>
        </div>

        {/* Actions */}
        <div className="space-y-2">
          <Button
            variant="outline"
            onClick={handleDownload}
            className="w-full gap-2"
          >
            <Download size={16} />
            {t("result.downloadMarkdown")}
          </Button>
          <Button
            variant="outline"
            onClick={handleToggleFavorite}
            className={cn("w-full gap-2", isFavorite && "text-yellow-500")}
          >
            <Star size={16} className={isFavorite ? "fill-current" : ""} />
            {isFavorite ? t("noteDetail.unfavorite") : t("noteDetail.favorite")}
          </Button>
        </div>

        {/* Save status */}
        {saving && (
          <p className="text-xs text-muted-foreground animate-pulse">{t("noteDetail.saving")}</p>
        )}
        {!saving && saveError && (
          <p className="text-xs text-destructive">{t("noteDetail.saveFailed")}</p>
        )}
        {!saving && !saveError && !hasUnsavedChanges && (
          <p className="text-xs text-muted-foreground">{t("noteDetail.saved")}</p>
        )}

        {/* Tags */}
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <Tag size={14} className="text-muted-foreground" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              {t("noteDetail.tags")}
            </span>
          </div>
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
                  onClick={() => handleRemoveTag(tag.id)}
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
                    {suggestedTags
                      .filter((tag) => tag.name.toLowerCase().includes(tagInputValue.toLowerCase()))
                      .slice(0, 5)
                      .map((tag) => (
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

        {/* Folder */}
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <FolderOpen size={14} className="text-muted-foreground" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              {t("noteDetail.folder")}
            </span>
          </div>
          <div className="relative">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setFolderPickerOpen(!folderPickerOpen)}
              className={cn("w-full gap-1.5 justify-start", folderName ? "text-foreground" : "text-muted-foreground")}
            >
              <FolderOpen size={12} />
              <span className="truncate">{folderName || t("history.noFolder")}</span>
            </Button>
            {folderPickerOpen && (
              <div className="absolute top-full left-0 mt-1 z-10 w-full rounded-lg border border-border bg-background shadow-lg py-1 max-h-60 overflow-y-auto">
                <button
                  onClick={() => handleMoveToFolder(null)}
                  className="w-full text-left flex items-center gap-2 px-3 py-1.5 text-sm hover:bg-muted"
                >
                  <FolderOpen size={14} />
                  {t("history.noFolder")}
                </button>
                {renderFolderNodes(folderTree, 0, handleMoveToFolder)}
              </div>
            )}
          </div>
        </div>

        {/* Video play button */}
        {hasVideo && (
          <div className="space-y-1.5">
            <Button
              variant="outline"
              onClick={() => setPlayerOpen(true)}
              className="w-full gap-2"
            >
              <Play size={16} />
              {t("noteDetail.playVideo")}
            </Button>
          </div>
        )}
      </aside>

      {/* Center — Milkdown editor */}
      <div className="flex-1 min-w-0" ref={previewRef}>
        <NoteEditor
          markdown={editMarkdown}
          onChange={handleEditorChange}
          onTimestampClick={hasVideo ? handleTimestampClick : undefined}
          hasVideo={hasVideo}
          resetKey={editorResetKey}
        />
      </div>

      {/* Right — TOC */}
      <TableOfContents containerRef={previewRef} contentKey={editMarkdown} />

      {/* Floating video player */}
      {playerOpen && hasVideo && videoUrl && platform && (
        <VideoPlayerFloat
          ref={playerRef}
          videoUrl={videoUrl}
          platform={platform}
          onClose={() => setPlayerOpen(false)}
        />
      )}
    </div>
  );
}

function renderFolderNodes(
  nodes: FolderTreeNode[],
  depth: number,
  onPick: (id: string) => void,
): React.ReactNode {
  return nodes.map((node) => (
    <div key={node.id}>
      <button
        onClick={() => onPick(node.id)}
        className="w-full text-left flex items-center gap-2 py-1.5 text-sm hover:bg-muted pl-[var(--depth-pad)]"
        style={{ "--depth-pad": `${depth * 16 + 12}px` } as React.CSSProperties}
      >
        <FolderOpen size={14} className="shrink-0" />
        {node.name}
      </button>
      {node.children.length > 0 && renderFolderNodes(node.children, depth + 1, onPick)}
    </div>
  ));
}
