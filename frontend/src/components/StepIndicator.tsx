import { useTranslation } from "react-i18next";
import { Check, X, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TaskPhase, TaskStatus } from "@/types";
import { pathForSource, stepIndexForPhase, synthesizeProgress } from "@/lib/phaseProgress";

interface StepIndicatorProps {
  status: TaskStatus | null;
  phase: TaskPhase | null;
  phaseProgress: number;
  /** Phase the task failed/was cancelled in — terminal rows have a null phase;
   * pass the last phase seen during the SSE stream when available. */
  failedPhase?: TaskPhase | null;
  sourceType?: "url" | "upload";
}

type StepStatus = "pending" | "active" | "done" | "error";

interface StepDef {
  key: string;
  labelKey: string;
}

const URL_STEPS: StepDef[] = [
  { key: "download", labelKey: "steps.download" },
  { key: "transcribe", labelKey: "steps.transcribe" },
  { key: "generate", labelKey: "steps.generate" },
];

const UPLOAD_STEPS: StepDef[] = [
  { key: "extract", labelKey: "steps.extractAudio" },
  { key: "transcribe", labelKey: "steps.transcribe" },
  { key: "generate", labelKey: "steps.generate" },
];

export function getStepStatuses(
  status: TaskStatus | null,
  phase: TaskPhase | null,
  failedPhase?: TaskPhase | null,
): StepStatus[] {
  if (!status || status === "pending") return ["pending", "pending", "pending"];
  if (status === "running") {
    if (!phase) return ["pending", "pending", "pending"];
    const active = stepIndexForPhase(phase);
    return [
      active > 0 ? "done" : "active",
      active > 1 ? "done" : active === 1 ? "active" : "pending",
      active === 2 ? "active" : "pending",
    ];
  }
  if (status === "complete") return ["done", "done", "done"];
  // failed / cancelled: mark the failure step (and everything after) as error.
  if (failedPhase) {
    const failed = stepIndexForPhase(failedPhase);
    return [
      failed === 0 ? "error" : "done",
      failed === 1 ? "error" : failed > 1 ? "done" : "pending",
      failed === 2 ? "error" : "pending",
    ];
  }
  // Terminal row without phase info — mark the whole row (legacy behaviour).
  return ["error", "error", "error"];
}

export function StepIndicator({ status, phase, phaseProgress, failedPhase, sourceType }: StepIndicatorProps) {
  const { t } = useTranslation();
  const steps = sourceType === "upload" ? UPLOAD_STEPS : URL_STEPS;
  const statuses = getStepStatuses(status, phase, failedPhase);
  const percentage = Math.round(
    synthesizeProgress(phase, phaseProgress, pathForSource(sourceType)) * 100,
  );
  const isTerminal = status === "failed" || status === "cancelled";

  return (
    <div className="w-full max-w-md mx-auto">
      {/* Steps */}
      <div className="flex items-center">
        {steps.map((step, i) => {
          const status2 = statuses[i];
          const isLast = i === steps.length - 1;
          return (
            <div key={step.key} className="flex items-center flex-1 last:flex-none">
              <div className="flex flex-col items-center">
                <div
                  className={cn(
                    "w-9 h-9 rounded-full flex items-center justify-center border-2 transition-colors",
                    status2 === "pending" && "border-muted-foreground/30 bg-background",
                    status2 === "active" && "border-primary bg-primary text-primary-foreground",
                    status2 === "done" && "border-green-500 bg-green-500 text-white dark:border-green-400 dark:bg-green-400",
                    status2 === "error" && "border-destructive bg-destructive text-destructive-foreground"
                  )}
                >
                  {status2 === "active" && <Loader2 size={16} className="animate-spin" />}
                  {status2 === "done" && <Check size={16} />}
                  {status2 === "error" && <X size={16} />}
                  {status2 === "pending" && (
                    <span className="text-xs font-medium text-muted-foreground/50">{i + 1}</span>
                  )}
                </div>
                <span
                  className={cn(
                    "mt-1.5 text-xs font-medium whitespace-nowrap",
                    status2 === "pending" && "text-muted-foreground/50",
                    status2 === "active" && "text-foreground",
                    status2 === "done" && "text-foreground",
                    status2 === "error" && "text-destructive"
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
      {status && !isTerminal && status !== "complete" && status !== "pending" && (
        <p className="text-center text-sm text-muted-foreground mt-4">
          {t("steps.inProgress", { percent: percentage })}
        </p>
      )}
      {isTerminal && (
        <p className="text-center text-sm text-destructive mt-4">
          {t(status === "failed" ? "progress.failed" : "progress.cancelled")}
        </p>
      )}
    </div>
  );
}
