import type { TaskPhase } from "@/types";

/** Contract §1.1 paths. */
export const URL_PATH: TaskPhase[] = ["fetching", "subtitle", "audio", "transcribe", "notegen"];
export const UPLOAD_PATH: TaskPhase[] = ["audio", "transcribe", "notegen"];

export function pathForSource(sourceType: "url" | "upload" | null | undefined): TaskPhase[] {
  return sourceType === "upload" ? UPLOAD_PATH : URL_PATH;
}

/**
 * Synthesize a global 0–1 progress from the two-level progress model
 * (contract §2): `(phase_index + phase_progress) / phase_count`.
 *
 * A `null` phase (pending / terminal) yields the phase-independent value:
 * pending → 0, complete → 1, failed/cancelled → NaN (caller decides).
 */
export function synthesizeProgress(
  phase: TaskPhase | null,
  phaseProgress: number,
  path: TaskPhase[],
): number {
  if (phase === null) return 0;
  const index = path.indexOf(phase);
  if (index === -1) return 0;
  return (index + Math.min(1, Math.max(0, phaseProgress))) / path.length;
}

/**
 * Map a phase to the 3-step indicator (URL: 下载→转录→生成笔记).
 * Steps are 0-based: fetching|subtitle|audio → 0, transcribe → 1, notegen → 2.
 */
export function stepIndexForPhase(phase: TaskPhase): number {
  switch (phase) {
    case "fetching":
    case "subtitle":
    case "audio":
      return 0;
    case "transcribe":
      return 1;
    case "notegen":
      return 2;
  }
}
