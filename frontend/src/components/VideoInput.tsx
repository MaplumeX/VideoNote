import { useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, Link, FileVideo } from "lucide-react";
import { cn } from "../lib/utils";

interface VideoInputProps {
  onSubmitUrl: (url: string) => void;
  onUploadFile: (file: File) => void;
  disabled?: boolean;
}

export function VideoInput({ onSubmitUrl, onUploadFile, disabled }: VideoInputProps) {
  const [url, setUrl] = useState("");
  const [tab, setTab] = useState<"url" | "upload">("url");

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: (acceptedFiles) => {
      const file = acceptedFiles[0];
      if (file) onUploadFile(file);
    },
    accept: { "video/*": [] },
    maxFiles: 1,
    disabled,
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (url.trim()) {
      onSubmitUrl(url.trim());
      setUrl("");
    }
  };

  return (
    <div className="w-full max-w-xl mx-auto">
      {/* Tab switcher */}
      <div className="flex border-b border-border mb-4">
        <button
          type="button"
          onClick={() => setTab("url")}
          className={cn(
            "flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors",
            tab === "url"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          <Link size={16} />
          Video URL
        </button>
        <button
          type="button"
          onClick={() => setTab("upload")}
          className={cn(
            "flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors",
            tab === "upload"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          <Upload size={16} />
          Upload File
        </button>
      </div>

      {/* URL input */}
      {tab === "url" && (
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Paste YouTube or Bilibili URL..."
            disabled={disabled}
            className="flex-1 rounded-lg border border-border bg-background px-4 py-2.5 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 transition-colors disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={disabled || !url.trim()}
            className="rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Process
          </button>
        </form>
      )}

      {/* File upload */}
      {tab === "upload" && (
        <div
          {...getRootProps()}
          className={cn(
            "flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 cursor-pointer transition-colors",
            isDragActive
              ? "border-primary bg-accent"
              : "border-border hover:border-primary/50 hover:bg-muted",
            disabled && "opacity-50 cursor-not-allowed"
          )}
        >
          <input {...getInputProps()} />
          <FileVideo size={40} className="text-muted-foreground mb-3" />
          <p className="text-sm text-muted-foreground">
            {isDragActive ? "Drop video here..." : "Drag & drop a video file, or click to browse"}
          </p>
          <p className="text-xs text-muted-foreground mt-1">MP4, WebM, MKV, etc.</p>
        </div>
      )}
    </div>
  );
}
