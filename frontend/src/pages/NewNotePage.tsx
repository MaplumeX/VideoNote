import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router";
import { VideoInput } from "@/components/VideoInput";
import { StepIndicator } from "@/components/StepIndicator";
import { VideoInfoCard } from "@/components/VideoInfoCard";
import { Button } from "@/components/ui/button";
import { useSSE } from "@/hooks/useSSE";
import { useVideoUpload } from "@/hooks/useVideoUpload";
import { submitUrl, cancelTask, retryTask } from "@/api/client";
import { getAccessToken } from "@/auth/token";
import type { TaskMeta } from "@/types";

export function NewNotePage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [jobId, setJobId] = useState<string | null>(searchParams.get("job"));
  const [error, setError] = useState<string | null>(null);
  const [taskMeta, setTaskMeta] = useState<TaskMeta | null>(null);
  const appLanguage = i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en";

  const { progress, result, error: sseError } = useSSE(jobId);
  const { uploading, progress: uploadProgress, error: uploadError, upload } =
    useVideoUpload();

  const isProcessing = !!jobId;
  const isFailed = progress?.stage === "failed" || progress?.stage === "cancelled";

  useEffect(() => {
    if (result && jobId) {
      navigate(`/app/notes/${jobId}`);
    }
  }, [result, jobId, navigate]);

  useEffect(() => {
    if (sseError) {
      setError(t("error.processingFailed"));
      // Keep jobId and taskMeta so user can see the info card and retry
    }
  }, [sseError, t]);

  useEffect(() => {
    if (uploadError) {
      setError(uploadError);
    }
  }, [uploadError]);

  const handleUrlSubmit = async (url: string) => {
    setError(null);
    try {
      const data = await submitUrl(url, appLanguage);
      setJobId(data.job_id);
      setTaskMeta({
        title: data.title,
        thumbnail_url: data.thumbnail_url,
        platform: data.platform,
        source_type: "url",
      });
      setSearchParams({ job: data.job_id }, { replace: true });
    } catch {
      setError(t("error.submitUrlFailed"));
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
      setTaskMeta({
        title: data.title,
        thumbnail_url: data.thumbnail_url,
        platform: data.platform,
        source_type: "url",
      });
      setError(null);
      setSearchParams({ job: data.job_id }, { replace: true });
    } catch {
      setError(t("history.retryFailed"));
    }
  };

  const showCancelButton = isProcessing && !isFailed && !uploading;
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
              <StepIndicator stage="downloading" progress={uploadProgress} />
            ) : (
              <StepIndicator stage={progress?.stage ?? null} progress={progress?.progress ?? 0} />
            )}
          </div>

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
