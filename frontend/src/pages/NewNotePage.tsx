import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router";
import { VideoInput } from "@/components/VideoInput";
import { StepIndicator } from "@/components/StepIndicator";
import { useSSE } from "@/hooks/useSSE";
import { useVideoUpload } from "@/hooks/useVideoUpload";
import { submitUrl } from "@/api/client";
import { getAccessToken } from "@/auth/token";

export function NewNotePage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [jobId, setJobId] = useState<string | null>(searchParams.get("job"));
  const [error, setError] = useState<string | null>(null);
  const appLanguage = i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en";

  const { progress, result, error: sseError } = useSSE(jobId);
  const { uploading, progress: uploadProgress, error: uploadError, upload } =
    useVideoUpload();

  const isProcessing = !!jobId;

  useEffect(() => {
    if (result && jobId) {
      navigate(`/app/notes/${jobId}`);
    }
  }, [result, jobId, navigate]);

  useEffect(() => {
    if (sseError) {
      setError(t("error.processingFailed"));
      setJobId(null);
      setSearchParams({}, { replace: true });
    }
  }, [sseError, t, setSearchParams]);

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
    setSearchParams({ job: id }, { replace: true });
  };

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
        <div className="flex justify-center pt-8">
          {uploading ? (
            <StepIndicator stage="downloading" progress={uploadProgress} />
          ) : (
            <StepIndicator stage={progress?.stage ?? null} progress={progress?.progress ?? 0} />
          )}
        </div>
      )}
    </div>
  );
}
