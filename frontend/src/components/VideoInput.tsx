import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDropzone } from "react-dropzone";
import { Upload, Link, FileVideo } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface VideoInputProps {
  onSubmitUrl: (url: string) => void;
  onUploadFile: (file: File) => void;
  disabled?: boolean;
}

export function VideoInput({ onSubmitUrl, onUploadFile, disabled }: VideoInputProps) {
  const { t } = useTranslation();
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

  const handleSubmit = (e: React.SyntheticEvent<HTMLFormElement>) => {
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
        <Button
          variant="ghost"
          type="button"
          onClick={() => setTab("url")}
          className={cn(
            "flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 rounded-none",
            tab === "url"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          <Link size={16} />
          {t("input.tabUrl")}
        </Button>
        <Button
          variant="ghost"
          type="button"
          onClick={() => setTab("upload")}
          className={cn(
            "flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 rounded-none",
            tab === "upload"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          <Upload size={16} />
          {t("input.tabUpload")}
        </Button>
      </div>

      {/* URL input */}
      {tab === "url" && (
        <form onSubmit={handleSubmit} className="flex gap-2">
          <Input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder={t("input.urlPlaceholder")}
            disabled={disabled}
            className="flex-1 h-9"
          />
          <Button
            type="submit"
            disabled={disabled || !url.trim()}
            className="h-9"
          >
            {t("input.process")}
          </Button>
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
            {isDragActive ? t("input.dropHere") : t("input.dragOrBrowse")}
          </p>
          <p className="text-xs text-muted-foreground mt-1">{t("input.supportedFormats")}</p>
        </div>
      )}
    </div>
  );
}
