import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router";
import { VideoInput } from "@/components/VideoInput";
import { StepIndicator } from "@/components/StepIndicator";
import { VideoInfoCard } from "@/components/VideoInfoCard";
import { Button } from "@/components/ui/button";
import { useSSE } from "@/hooks/useSSE";
import { useVideoUpload } from "@/hooks/useVideoUpload";
import { submitUrl, cancelTask, retryTask, fetchTaskById, ApiError } from "@/api/client";
import { getAccessToken } from "@/auth/token";
import type { TaskMeta } from "@/types";

export function NewNotePage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [jobId, setJobId] = useState<string | null>(searchParams.get("job"));
  const [error, setError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [taskMeta, setTaskMeta] = useState<TaskMeta | null>(null);
  const appLanguage = i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en";

  const { progress, result, error: sseError } = useSSE(jobId);
  const { uploading, progress: uploadProgress, error: uploadError, errorCode: uploadErrorCode, upload } =
    useVideoUpload();

  const isProcessing = !!jobId;
  const isTerminal = progress?.stage === "failed" || progress?.stage === "cancelled";
  const isFailed = progress?.stage === "failed";

  // Fetch task metadata (title/thumbnail) from the REST API once the SSE stage
  // transitions from pending to an active stage, since the POST response may
  // have empty title/thumbnail (they're populated by update_task_meta shortly
  // after submission, before the first non-pending progress).
  const metaFetchedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!jobId || !progress) return;
    if (progress.stage === "pending") return;
    if (metaFetchedFor.current === jobId) return;
    metaFetchedFor.current = jobId;
    void (async () => {
      try {
        const task = await fetchTaskById(jobId);
        if (task.title || task.thumbnail_url || task.platform) {
          setTaskMeta((prev) => ({
            ...prev,
            title: task.title ?? prev?.title,
            thumbnail_url: task.thumbnail_url ?? prev?.thumbnail_url,
            platform: task.platform ?? prev?.platform,
          }));
        }
      } catch {
        // Non-fatal — metadata may still arrive later
      }
    })();
  }, [jobId, progress?.stage]);

  useEffect(() => {
    if (result && jobId) {
      navigate(`/app/notes/${jobId}`);
    }
  }, [result, jobId, navigate]);

  useEffect(() => {
    if (sseError) {
      setError(sseError);
      // Detect PROVIDER_NOT_CONFIGURED from translated task message
      setErrorCode(
        sseError === t("errors.providerNotConfigured")
          ? "PROVIDER_NOT_CONFIGURED"
          : null,
      );
      // Keep jobId and taskMeta so user can see the info card and retry
    }
  }, [sseError, t]);

  useEffect(() => {
    if (uploadError) {
      setError(uploadError);
      setErrorCode(uploadErrorCode);
    }
  }, [uploadError, uploadErrorCode]);

  const handleUrlSubmit = async (url: string) => {
    setError(null);
    setErrorCode(null);
    try {
      const data = await submitUrl(url, appLanguage);
      setJobId(data.job_id);
      setTaskMeta({
        title: data.title || undefined,
        thumbnail_url: data.thumbnail_url || undefined,
        platform: data.platform || undefined,
        source_type: data.source_type,
      });
      setSearchParams({ job: data.job_id }, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        setErrorCode(err.code ?? null);
      } else {
        setError(t("error.submitUrlFailed"));
      }
    }
  };

  const handleFileUpload = async (file: File) => {
    setError(null);
    const id = await upload(file, appLanguage, getAccessToken());
    if (!id) {
      setError(t("error.uploadFailed"));
      return;
    }
    setJobId(id);
    setTaskMeta({
      file_name: file.name,
      source_type: "upload",
    });
    setSearchParams({ job: id }, { replace: true });
  };

  const handleCancel = async () => {
    if (!jobId) return;
    if (!window.confirm(t("processing.cancelConfirm"))) return;
    try {
      await cancelTask(jobId);
      setJobId(null);
      setTaskMeta(null);
      setError(null);
      setSearchParams({}, { replace: true });
    } catch {
      setError(t("history.cancelFailed"));
    }
  };

  const handleRetry = async () => {
    if (!jobId) return;
    if (!window.confirm(t("processing.retryConfirm"))) return;
    try {
      const data = await retryTask(jobId);
      setJobId(data.job_id);
      metaFetchedFor.current = null;
      setTaskMeta({
        title: data.title || undefined,
        thumbnail_url: data.thumbnail_url || undefined,
        platform: data.platform || undefined,
        source_type: data.source_type,
      });
      setError(null);
      setErrorCode(null);
      setSearchParams({ job: data.job_id }, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        setErrorCode(err.code ?? null);
      } else {
        setError(t("history.retryFailed"));
      }
    }
  };

  const showCancelButton = isProcessing && !isTerminal && !uploading;
  const showRetryButton = isFailed;

  return (
    <div className="max-w-lg mx-auto space-y-8">
      {/* Hero */}
      <div className="text-center space-y-2 pt-4">
        <h1 className="text-3xl font-bold tracking-tight">{t("app.title")}</h1>
        <p className="text-muted-foreground">{t("app.subtitle")}</p>
      </div>

      {error && (
        <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive">
          {error}
          {errorCode === "PROVIDER_NOT_CONFIGURED" && (
            <Button
              variant="outline"
              size="sm"
              className="ml-3"
              onClick={() => navigate("/app/settings")}
            >
              {t("sidebar.settings")}
            </Button>
          )}
        </div>
      )}

      {!isProcessing ? (
        <VideoInput onSubmitUrl={handleUrlSubmit} onUploadFile={handleFileUpload} />
      ) : (
        <div className="space-y-6 pt-8">
          {/* Video info card */}
          {taskMeta && (
            <VideoInfoCard
              title={taskMeta.title}
              thumbnailUrl={taskMeta.thumbnail_url}
              platform={taskMeta.platform}
              fileName={taskMeta.file_name}
            />
          )}

          {/* Step indicator */}
          <div className="flex justify-center">
            {uploading ? (
              <StepIndicator
                stage="downloading"
                progress={uploadProgress}
                sourceType={taskMeta?.source_type === "upload" ? "upload" : "url"}
              />
            ) : (
              <StepIndicator
                stage={progress?.stage ?? null}
                progress={progress?.progress ?? 0}
                sourceType={taskMeta?.source_type === "upload" ? "upload" : "url"}
              />
            )}
          </div>

          {/* Progress message */}
          {!uploading && !isTerminal && progress?.message && (
            <p className="text-center text-sm text-muted-foreground">
              {progress.message}
            </p>
          )}

          {/* Action buttons */}
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
      )}
    </div>
  );
}
