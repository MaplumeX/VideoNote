import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams, Link } from "react-router";
import { Download, ChevronRight } from "lucide-react";
import { fetchResult } from "@/api/client";
import { useSSE } from "@/hooks/useSSE";
import { ProgressBar } from "@/components/ProgressBar";
import { NoteView } from "@/components/NoteView";
import type { NoteResult } from "@/types";

export function NoteDetailPage() {
  const { t } = useTranslation();
  const { id: jobId } = useParams<{ id: string }>();
  const [note, setNote] = useState<NoteResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { progress, result: sseResult, error: sseError } = useSSE(processing && jobId ? jobId : null);

  useEffect(() => {
    if (!jobId) return;

    setLoading(true);
    fetchResult(jobId)
      .then((data) => {
        setNote(data);
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

  // When SSE shows progress reaching failed/cancelled, show error
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

  // When SSE completes (result received), fetch the full note
  useEffect(() => {
    if (sseResult && processing && jobId) {
      fetchResult(jobId)
        .then((data) => {
          setNote(data);
          setProcessing(false);
        })
        .catch(() => {
          setError("Failed to load note");
          setProcessing(false);
        });
    }
  }, [sseResult, processing, jobId]);

  // Handle SSE connection error
  useEffect(() => {
    if (sseError && processing) {
      setError(sseError);
      setProcessing(false);
    }
  }, [sseError, processing]);

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
      <div className="max-w-xl mx-auto space-y-6">
        <ProgressBar progress={progress} />
      </div>
    );
  }

  if (!note) return null;

  return (
    <div className="space-y-4">
      {/* Breadcrumb */}
      <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
        <Link to="/app/history" className="hover:text-foreground transition-colors">
          {t("sidebar.history")}
        </Link>
        <ChevronRight size={14} />
        <span className="text-foreground truncate">{note.title || t("note.untitled")}</span>
      </div>

      {/* Action bar */}
      <div className="flex items-center gap-2">
        <button
          onClick={handleDownload}
          className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Download size={16} />
          {t("result.downloadMarkdown")}
        </button>
      </div>

      {/* Note content */}
      <NoteView markdown={note.markdown} />
    </div>
  );
}
