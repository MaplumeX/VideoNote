import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";
import { VideoInput } from "./components/VideoInput";
import { ProgressBar } from "./components/ProgressBar";
import { NoteView } from "./components/NoteView";
import { useSSE } from "./hooks/useSSE";
import { useVideoUpload } from "./hooks/useVideoUpload";
import { authFetch } from "./auth/api";
import { getAccessToken } from "./auth/token";
import { Download, RotateCcw } from "lucide-react";

type AppStep = "input" | "processing" | "result";

export function VideoNoteApp() {
  const { t, i18n } = useTranslation();
  const [searchParams] = useSearchParams();
  const [step, setStep] = useState<AppStep>("input");
  const [jobId, setJobId] = useState<string | null>(null);
  const [noteMarkdown, setNoteMarkdown] = useState("");
  const [error, setError] = useState<string | null>(null);
  const appLanguage = i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en";

  const { progress, result, error: sseError } = useSSE(jobId);
  const { uploading, progress: uploadProgress, jobId: uploadJobId, error: uploadError, upload } = useVideoUpload();

  // Load existing task result if task param provided
  useEffect(() => {
    const taskId = searchParams.get("task");
    if (taskId && step === "input") {
      authFetch(`/api/tasks/${taskId}/result`)
        .then((res) => {
          if (!res.ok) throw new Error("Not found");
          return res.json();
        })
        .then((data) => {
          setNoteMarkdown(data.markdown);
          setStep("result");
        })
        .catch(() => {
          setError("Failed to load task result");
        });
    }
  }, [searchParams, step]);

  useEffect(() => {
    if (result && step === "processing") {
      setNoteMarkdown(result);
      setStep("result");
    }
  }, [result, step]);

  useEffect(() => {
    if (sseError && step === "processing") {
      setError(t("error.processingFailed"));
      setStep("input");
    }
  }, [sseError, step, t]);

  useEffect(() => {
    if (uploadJobId && !jobId && step === "processing") {
      setJobId(uploadJobId);
    }
  }, [uploadJobId, jobId, step]);

  const handleUrlSubmit = async (url: string) => {
    setError(null);
    setStep("processing");
    try {
      const res = await authFetch("/api/process", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, language: appLanguage }),
      });
      if (!res.ok) throw new Error("Failed");
      const data = await res.json();
      setJobId(data.job_id);
    } catch {
      setError(t("error.submitUrlFailed"));
      setStep("input");
    }
  };

  const handleFileUpload = async (file: File) => {
    setError(null);
    setStep("processing");
    const id = await upload(file, appLanguage, getAccessToken());
    if (id) {
      setJobId(id);
    } else {
      if (uploadError) console.error("Upload error:", uploadError);
      setError(t("error.uploadFailed"));
      setStep("input");
    }
  };

  const handleReset = () => {
    setStep("input");
    setJobId(null);
    setNoteMarkdown("");
    setError(null);
  };

  const handleDownload = () => {
    const blob = new Blob([noteMarkdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "videonote.md";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-8">
      {error && (
        <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {step === "input" && (
        <VideoInput onSubmitUrl={handleUrlSubmit} onUploadFile={handleFileUpload} />
      )}

      {step === "processing" && (
        <div className="space-y-6">
          {uploading ? (
            <div className="space-y-2">
              <p className="text-sm font-medium">
                {t("progress.uploading", { percent: Math.round(uploadProgress * 100) })}
              </p>
              <div className="h-2 rounded-full bg-muted overflow-hidden">
                <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${uploadProgress * 100}%` }} />
              </div>
            </div>
          ) : (
            <ProgressBar progress={progress} />
          )}
        </div>
      )}

      {step === "result" && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <button
              onClick={handleDownload}
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              <Download size={16} />
              {t("result.downloadMarkdown")}
            </button>
            <button
              onClick={handleReset}
              className="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-muted transition-colors"
            >
              <RotateCcw size={16} />
              {t("result.newVideo")}
            </button>
          </div>
          <NoteView markdown={noteMarkdown} />
        </div>
      )}
    </div>
  );
}
