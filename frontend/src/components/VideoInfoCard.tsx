import { FileVideo } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

interface VideoInfoCardProps {
  title?: string;
  thumbnailUrl?: string;
  platform?: string;
  fileName?: string;
}

function resolveThumbnailUrl(url: string | undefined): string | undefined {
  if (!url) return undefined;
  return url.startsWith("http") ? url : `/api/thumbnails/${url}`;
}

const PLATFORM_STYLES: Record<string, { label: string; className: string }> = {
  youtube: { label: "YouTube", className: "bg-red-600 text-white" },
  bilibili: { label: "Bilibili", className: "bg-pink-500 text-white" },
};

export function VideoInfoCard({ title, thumbnailUrl, platform, fileName }: VideoInfoCardProps) {
  const { t } = useTranslation();
  const resolvedUrl = resolveThumbnailUrl(thumbnailUrl);
  const hasThumbnail = !!resolvedUrl;
  const platformInfo = platform ? PLATFORM_STYLES[platform.toLowerCase()] : undefined;

  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-muted/30 p-3">
      {hasThumbnail ? (
        <img
          src={resolvedUrl}
          alt={title || "Video thumbnail"}
          className="w-24 h-14 rounded object-cover shrink-0"
        />
      ) : (
        <div className="w-24 h-14 rounded bg-muted flex items-center justify-center shrink-0">
          <FileVideo size={24} className="text-muted-foreground" />
        </div>
      )}

      <div className="min-w-0 flex-1">
        {hasThumbnail ? (
          <>
            <p className="text-sm font-medium truncate">{title || t("videoInfo.untitled")}</p>
            {platformInfo && (
              <span
                className={cn(
                  "inline-block mt-1 px-1.5 py-0.5 text-[10px] font-semibold rounded leading-none",
                  platformInfo.className,
                )}
              >
                {platformInfo.label}
              </span>
            )}
          </>
        ) : (
          <p className="text-sm font-medium truncate">{fileName || t("videoInfo.unknownFile")}</p>
        )}
      </div>
    </div>
  );
}
