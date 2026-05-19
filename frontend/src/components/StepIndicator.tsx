import { useTranslation } from "react-i18next";
import { Check, X, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TaskStage } from "@/types";

interface StepIndicatorProps {
  stage: TaskStage | null;
  progress: number;
}

type StepStatus = "pending" | "active" | "done" | "error";

interface StepDef {
  key: string;
  labelKey: string;
}

const STEPS: StepDef[] = [
  { key: "download", labelKey: "steps.download" },
  { key: "transcribe", labelKey: "steps.transcribe" },
  { key: "generate", labelKey: "steps.generate" },
];

function getStepStatuses(stage: TaskStage | null): StepStatus[] {
  if (!stage || stage === "pending") return ["pending", "pending", "pending"];
  if (stage === "downloading" || stage === "extracting_subtitles")
    return ["active", "pending", "pending"];
  if (stage === "transcribing") return ["done", "active", "pending"];
  if (stage === "generating_notes") return ["done", "done", "active"];
  if (stage === "complete") return ["done", "done", "done"];
  if (stage === "failed" || stage === "cancelled") return ["error", "error", "error"];
  return ["pending", "pending", "pending"];
}

export function StepIndicator({ stage, progress }: StepIndicatorProps) {
  const { t } = useTranslation();
  const statuses = getStepStatuses(stage);
  const percentage = Math.round(progress * 100);

  return (
    <div className="w-full max-w-md mx-auto">
      {/* Steps */}
      <div className="flex items-center">
        {STEPS.map((step, i) => {
          const status = statuses[i];
          const isLast = i === STEPS.length - 1;
          return (
            <div key={step.key} className="flex items-center flex-1 last:flex-none">
              <div className="flex flex-col items-center">
                <div
                  className={cn(
                    "w-9 h-9 rounded-full flex items-center justify-center border-2 transition-colors",
                    status === "pending" && "border-muted-foreground/30 bg-background",
                    status === "active" && "border-primary bg-primary text-primary-foreground",
                    status === "done" && "border-green-500 bg-green-500 text-white dark:border-green-400 dark:bg-green-400",
                    status === "error" && "border-destructive bg-destructive text-destructive-foreground"
                  )}
                >
                  {status === "active" && <Loader2 size={16} className="animate-spin" />}
                  {status === "done" && <Check size={16} />}
                  {status === "error" && <X size={16} />}
                  {status === "pending" && (
                    <span className="text-xs font-medium text-muted-foreground/50">{i + 1}</span>
                  )}
                </div>
                <span
                  className={cn(
                    "mt-1.5 text-xs font-medium whitespace-nowrap",
                    status === "pending" && "text-muted-foreground/50",
                    status === "active" && "text-foreground",
                    status === "done" && "text-foreground",
                    status === "error" && "text-destructive"
                  )}
                >
                  {t(step.labelKey)}
                </span>
              </div>
              {!isLast && (
                <div
                  className={cn(
                    "flex-1 h-0.5 mx-2 mt-[-18px] transition-colors",
                    statuses[i] === "done" ? "bg-green-500 dark:bg-green-400" : "bg-muted-foreground/20"
                  )}
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Progress percentage */}
      {stage && stage !== "complete" && stage !== "failed" && stage !== "cancelled" && (
        <p className="text-center text-sm text-muted-foreground mt-4">
          {t("steps.inProgress", { percent: percentage })}
        </p>
      )}
      {(stage === "failed" || stage === "cancelled") && (
        <p className="text-center text-sm text-destructive mt-4">
          {t(stage === "failed" ? "progress.failed" : "progress.cancelled")}
        </p>
      )}
    </div>
  );
}
