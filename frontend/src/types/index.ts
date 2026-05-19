export type TaskStage =
  | "pending"
  | "downloading"
  | "extracting_subtitles"
  | "transcribing"
  | "generating_notes"
  | "complete"
  | "failed"
  | "cancelled";

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

export interface ProviderPreset {
  provider: string;
  models: string[];
  api_base: string;
}

export interface ProvidersResponse {
  asr: ProviderPreset[];
  llm: ProviderPreset[];
}

export interface ProviderConfig {
  provider: string;
  model: string;
  api_key: string;
  api_base: string;
}

export interface ProviderConfigResponse {
  provider: string;
  model: string;
  api_key_masked: string;
  api_base: string;
}

export interface SettingsResponse {
  asr: ProviderConfigResponse | null;
  llm: ProviderConfigResponse | null;
}

export interface SettingsRequest {
  asr?: ProviderConfig | null;
  llm?: ProviderConfig | null;
}

export interface TaskItem {
  job_id: string;
  stage: TaskStage;
  progress: number;
  message: string;
  created_at: string;
  title: string | null;
  video_url: string | null;
  file_name: string | null;
  platform: string | null;
  language: string | null;
  source_type: string | null;
}

export interface TaskListResponse {
  items: TaskItem[];
  total: number;
  page: number;
  limit: number;
}
