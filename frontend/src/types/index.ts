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
