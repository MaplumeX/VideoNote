import { useEffect, useState } from "react";
import { VideoInput } from "./components/VideoInput";
import { ProgressBar } from "./components/ProgressBar";
import { NoteView } from "./components/NoteView";
import { useSSE } from "./hooks/useSSE";
import { useVideoUpload } from "./hooks/useVideoUpload";
import { submitUrl } from "./api/client";
import { Download, RotateCcw } from "lucide-react";

type AppStep = "input" | "processing" | "result";

export default function App() {
  const [step, setStep] = useState<AppStep>("input");
  const [jobId, setJobId] = useState<string | null>(null);
  const [noteMarkdown, setNoteMarkdown] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { progress, result, error: sseError } = useSSE(jobId);
  const { uploading, progress: uploadProgress, jobId: uploadJobId, error: uploadError, upload } = useVideoUpload();

  // When SSE delivers the final result
  useEffect(() => {
    if (result && step === "processing") {
      setNoteMarkdown(result);
      setStep("result");
    }
  }, [result, step]);

  // When SSE reports a processing failure
  useEffect(() => {
    if (sseError && step === "processing") {
      setError(sseError);
      setStep("input");
    }
  }, [sseError, step]);

  // When upload completes and we have a job ID
  useEffect(() => {
    if (uploadJobId && !jobId && step === "processing") {
      setJobId(uploadJobId);
    }
  }, [uploadJobId, jobId, step]);

  const handleUrlSubmit = async (url: string) => {
    setError(null);
    setStep("processing");
    try {
      const res = await submitUrl(url);
      setJobId(res.job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to submit URL");
      setStep("input");
    }
  };

  const handleFileUpload = async (file: File) => {
    setError(null);
    setStep("processing");
    const id = await upload(file);
    if (id) {
      setJobId(id);
    } else {
      setError(uploadError || "Upload failed");
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
    <div className="min-h-screen bg-background">
      <header className="border-b border-border">
        <div className="max-w-5xl mx-auto px-4 py-4">
          <h1 className="text-xl font-bold">VideoNote</h1>
          <p className="text-sm text-muted-foreground">AI-powered video notes with timestamps</p>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8 space-y-8">
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
                <p className="text-sm font-medium">Uploading video... {Math.round(uploadProgress * 100)}%</p>
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
                Download Markdown
              </button>
              <button
                onClick={handleReset}
                className="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-muted transition-colors"
              >
                <RotateCcw size={16} />
                New Video
              </button>
            </div>
            <NoteView markdown={noteMarkdown} />
          </div>
        )}
      </main>
    </div>
  );
}
