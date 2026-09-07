import { useEffect, useState, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useParams, useNavigate } from "react-router";
import {
  fetchResult,
  fetchTags,
  fetchFolderTree,
  fetchTaskById,
  fetchNoteTags,
  addTagsToNote,
  removeTagFromNote,
  moveNoteToFolder,
  toggleFavorite,
  updateNoteContent,
  cancelTask,
  retryTask,
  ApiError,
} from "@/api/client";
import { useSSE } from "@/hooks/useSSE";
import { useNoteAutoSave } from "@/hooks/useNoteAutoSave";
import { StepIndicator } from "@/components/StepIndicator";
import { VideoInfoCard } from "@/components/VideoInfoCard";
import { NoteEditor } from "@/components/NoteEditor";
import { TableOfContents } from "@/components/TableOfContents";
import { VideoPlayerFloat } from "@/components/VideoPlayerFloat";
import { NoteDetailHeader } from "@/components/NoteDetailHeader";
import type { VideoPlayerFloatHandle } from "@/components/VideoPlayerFloat";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { NoteResult, Tag as TagType, TagWithCount, FolderTreeNode } from "@/types";

export function NoteDetailPage() {
  const { t } = useTranslation();
  const { id: jobId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [note, setNote] = useState<NoteResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [processError, setProcessError] = useState<string | null>(null);
  const [isFavorite, setIsFavorite] = useState(false);
  const [noteTags, setNoteTags] = useState<TagType[]>([]);
  const [folderId, setFolderId] = useState<string | null>(null);
  const [allTags, setAllTags] = useState<TagWithCount[]>([]);
  const [folderTree, setFolderTree] = useState<FolderTreeNode[]>([]);

  const [editMarkdown, setEditMarkdown] = useState("");
  const [editorResetKey, setEditorResetKey] = useState(0);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [platform, setPlatform] = useState<string | null>(null);
  const [thumbnailUrl, setThumbnailUrl] = useState<string | null>(null);
  const [taskTitle, setTaskTitle] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [createdAt, setCreatedAt] = useState<string | null>(null);
  const [playerOpen, setPlayerOpen] = useState(false);
  const [tocSheetOpen, setTocSheetOpen] = useState(false);
  const playerRef = useRef<VideoPlayerFloatHandle>(null);
  const previewRef = useRef<HTMLDivElement>(null);

  const { progress, result: sseResult, error: sseError } = useSSE(processing && jobId ? jobId : null);

  const {
    handleChange: queueAutoSave,
    lastSavedMarkdown,
    reset: resetAutoSave,
    saveError,
    saving,
  } = useNoteAutoSave({
    save: async (snapshot) => {
      if (!jobId) throw new Error("Cannot save a note without a job ID");
      return updateNoteContent(jobId, { markdown: snapshot });
    },
    onSaved: (savedNote) => {
      setNote(savedNote);
    },
  });
  const hasUnsavedChanges = note !== null && editMarkdown !== lastSavedMarkdown;

  useEffect(() => {
    if (!jobId) return;

    setLoading(true);
    resetAutoSave("");
    setEditorResetKey((k) => k + 1);
    fetchResult(jobId)
      .then((data) => {
        setNote(data);
        setEditMarkdown(data.markdown);
        resetAutoSave(data.markdown);
        setLoading(false);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.code === "TASK_STILL_PROCESSING") {
          setProcessing(true);
          setProcessError(null);
          setLoading(false);
        } else {
          setError(err.message || t("noteDetail.loadFailed"));
          setLoading(false);
        }
      });
  }, [jobId, resetAutoSave, t]);

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
        setThumbnailUrl(task.thumbnail_url);
        setTaskTitle(task.title);
        setFileName(task.file_name);
        setCreatedAt(task.created_at);
      })
      .catch(() => {});

    fetchTags().then(setAllTags).catch(() => {});
    fetchFolderTree().then(setFolderTree).catch(() => {});
  }, [jobId]);

  useEffect(() => {
    if (progress?.status === "failed" && processing) {
      setProcessError(progress.message || t("error.processingFailed"));
      setProcessing(false);
    }
    if (progress?.status === "cancelled" && processing) {
      setProcessError(t("processing.cancelled"));
      setProcessing(false);
    }
  }, [progress?.status, processing, t]);

  useEffect(() => {
    if (sseResult && processing && jobId) {
      fetchResult(jobId)
        .then((data) => {
          setNote(data);
          setEditMarkdown(data.markdown);
          resetAutoSave(data.markdown);
          setEditorResetKey((k) => k + 1);
          setProcessing(false);
          setProcessError(null);
        })
        .catch(() => {
          setError(t("noteDetail.loadFailed"));
          setProcessing(false);
        });
    }
  }, [sseResult, processing, jobId, resetAutoSave, t]);

  useEffect(() => {
    if (sseError && processing) {
      setProcessError(sseError);
      setProcessing(false);
    }
  }, [sseError, processing]);

  const handleEditorChange = useCallback((value: string) => {
    setEditMarkdown(value);
    queueAutoSave(value);
  }, [queueAutoSave]);

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

  const handleAddTag = async (name: string) => {
    if (!jobId || !name.trim()) return;
    try {
      const result = await addTagsToNote(jobId, { tag_names: [name.trim()] });
      setNoteTags(result.tags);
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
    } catch {
      // silent
    }
  };

  const hasVideo = !!(videoUrl && platform && (platform === "youtube" || platform === "bilibili"));

  const handleTimestampClick = useCallback((seconds: number) => {
    if (!hasVideo) return;
    if (!playerOpen) setPlayerOpen(true);
    // Defer seek so the player ref is available after render
    setTimeout(() => playerRef.current?.seekTo(seconds), 0);
  }, [hasVideo, playerOpen]);

  const handleTocNavigate = useCallback(() => {
    setTocSheetOpen(false);
  }, []);

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

  if (processing || processError) {
    const isFailed = !!processError;
    const showCancelButton = !isFailed;
    const showRetryButton = isFailed;

    const handleCancel = async () => {
      if (!jobId) return;
      if (!window.confirm(t("processing.cancelConfirm"))) return;
      try {
        await cancelTask(jobId);
        setProcessError(t("processing.cancelled"));
        setProcessing(false);
      } catch {
        setProcessError(t("history.cancelFailed"));
        setProcessing(false);
      }
    };

    const handleRetry = async () => {
      if (!jobId) return;
      if (!window.confirm(t("processing.retryConfirm"))) return;
      try {
        const data = await retryTask(jobId);
        // Navigate to the new task so SSE tracks the correct job
        navigate(`/app/notes/${data.job_id}`);
      } catch {
        setProcessError(t("history.retryFailed"));
        setProcessing(false);
      }
    };

    return (
      <div className="max-w-lg mx-auto space-y-6 pt-12">
        {(thumbnailUrl || taskTitle || fileName) && (
          <VideoInfoCard
            title={taskTitle ?? undefined}
            thumbnailUrl={thumbnailUrl ?? undefined}
            platform={platform ?? undefined}
            fileName={fileName ?? undefined}
          />
        )}
        <div className="flex justify-center">
          <StepIndicator
            status={progress?.status ?? null}
            phase={progress?.phase ?? null}
            phaseProgress={progress?.phase_progress ?? 0}
            failedPhase={progress?.phase ?? null}
          />
        </div>
        {processError && (
          <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive">
            {processError}
          </div>
        )}
        {(showCancelButton || showRetryButton) && (
          <div className="flex justify-center gap-3">
            {showCancelButton && (
              <Button variant="outline" onClick={handleCancel}>
                {t("processing.cancel")}
              </Button>
            )}
            {showRetryButton && (
              <Button variant="outline" onClick={handleRetry}>
                {t("processing.retry")}
              </Button>
            )}
          </div>
        )}
      </div>
    );
  }

  if (!note) return null;

  return (
    <div className="flex gap-6">
      <div className="flex-1 min-w-0">
        <NoteDetailHeader
          title={taskTitle || note.title || ""}
          platform={platform}
          fileName={fileName}
          createdAt={createdAt}
          saving={saving}
          saveError={saveError}
          hasUnsavedChanges={hasUnsavedChanges}
          isFavorite={isFavorite}
          hasVideo={hasVideo}
          noteTags={noteTags}
          allTags={allTags}
          folderTree={folderTree}
          folderId={folderId}
          onToggleFavorite={handleToggleFavorite}
          onDownload={handleDownload}
          onPlayVideo={() => setPlayerOpen(true)}
          onAddTag={handleAddTag}
          onRemoveTag={handleRemoveTag}
          onMoveToFolder={handleMoveToFolder}
          onOpenToc={() => setTocSheetOpen(true)}
        />
        <div className="mx-auto w-full max-w-3xl" ref={previewRef}>
          <NoteEditor
            markdown={editMarkdown}
            onChange={handleEditorChange}
            onTimestampClick={hasVideo ? handleTimestampClick : undefined}
            hasVideo={hasVideo}
            resetKey={editorResetKey}
          />
        </div>
      </div>

      {/* Right — TOC on wide screens */}
      <div className="hidden xl:block">
        <TableOfContents containerRef={previewRef} contentKey={editMarkdown} />
      </div>

      {/* TOC drawer on narrow screens */}
      <Sheet open={tocSheetOpen} onOpenChange={setTocSheetOpen}>
        <SheetContent side="right" className="w-72">
          <SheetHeader>
            <SheetTitle>{t("toc.onThisPage")}</SheetTitle>
          </SheetHeader>
          <div className="px-4 pb-4">
            <TableOfContents
              containerRef={previewRef}
              contentKey={editMarkdown}
              className="block static"
              onNavigate={handleTocNavigate}
            />
          </div>
        </SheetContent>
      </Sheet>

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
