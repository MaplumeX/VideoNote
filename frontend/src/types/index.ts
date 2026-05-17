export type TaskStage =
  | "pending"
  | "downloading"
  | "extracting_subtitles"
  | "transcribing"
  | "generating_notes"
  | "complete"
  | "failed";

export interface TaskProgress {
  stage: TaskStage;
  progress: number;
  message: string;
}

export interface NoteResult {
  job_id: string;
  markdown: string;
  title: string | null;
}

export interface ProcessResponse {
  job_id: string;
}
