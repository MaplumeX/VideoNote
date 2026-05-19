import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDropzone } from "react-dropzone";
import { Link, FileVideo } from "lucide-react";
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
    <div className="w-full space-y-4">
      {/* URL input */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <div className="relative flex-1">
          <Link size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder={t("input.urlPlaceholder")}
            disabled={disabled}
            className="h-10 pl-9"
          />
        </div>
        <Button
          type="submit"
          disabled={disabled || !url.trim()}
          className="h-10"
        >
          {t("input.process")}
        </Button>
      </form>

      {/* Divider */}
      <div className="flex items-center gap-3">
        <div className="flex-1 h-px bg-border" />
        <span className="text-xs text-muted-foreground">{t("input.orDivider")}</span>
        <div className="flex-1 h-px bg-border" />
      </div>

      {/* File upload */}
      <div
        {...getRootProps()}
        className={cn(
          "flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 cursor-pointer transition-all",
          isDragActive
            ? "border-primary bg-primary/5 scale-[1.02]"
            : "border-border hover:border-primary/40 hover:bg-muted/50",
          disabled && "opacity-50 cursor-not-allowed"
        )}
      >
        <input {...getInputProps()} />
        <div className={cn(
          "w-12 h-12 rounded-full flex items-center justify-center mb-3 transition-colors",
          isDragActive ? "bg-primary/10" : "bg-muted"
        )}>
          <FileVideo size={24} className={cn(
            "transition-colors",
            isDragActive ? "text-primary" : "text-muted-foreground"
          )} />
        </div>
        <p className="text-sm text-muted-foreground">
          {isDragActive ? t("input.dropHere") : t("input.dragOrBrowse")}
        </p>
        <p className="text-xs text-muted-foreground/70 mt-1">{t("input.supportedFormats")}</p>
      </div>
    </div>
  );
}
