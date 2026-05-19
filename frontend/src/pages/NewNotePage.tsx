import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router";
import { VideoInput } from "@/components/VideoInput";
import { ProgressBar } from "@/components/ProgressBar";
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
    <div className="max-w-xl mx-auto space-y-6">
      {error && (
        <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {!isProcessing ? (
        <VideoInput onSubmitUrl={handleUrlSubmit} onUploadFile={handleFileUpload} />
      ) : (
        <div className="space-y-6">
          {uploading ? (
            <ProgressBar
              progress={{
                stage: "downloading",
                progress: uploadProgress,
                message: "",
              }}
            />
          ) : (
            <ProgressBar progress={progress} />
          )}
        </div>
      )}
    </div>
  );
}
