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
  folder_id: string | null;
  is_favorite: boolean;
}

export interface TaskListResponse {
  items: TaskItem[];
  total: number;
  page: number;
  limit: number;
}

// --- Tag types ---

export interface Tag {
  id: string;
  user_id: string;
  name: string;
  color: string;
  created_at: string;
}

export interface TagWithCount extends Tag {
  note_count: number;
}

// --- Folder types ---

export interface Folder {
  id: string;
  user_id: string;
  name: string;
  parent_id: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface FolderTreeNode extends Folder {
  note_count: number;
  children: FolderTreeNode[];
}

// --- Batch / association request types ---

export interface NoteTagAddRequest {
  tag_ids?: string[];
  tag_names?: string[];
}

export interface NoteFolderUpdateRequest {
  folder_id: string | null;
}

export interface FavoriteToggleRequest {
  is_favorite: boolean;
}

export interface BatchTagRequest {
  job_ids: string[];
  tag_id: string;
}

export interface BatchMoveRequest {
  job_ids: string[];
  folder_id: string | null;
}

export interface BatchFavoriteRequest {
  job_ids: string[];
  is_favorite: boolean;
}

// --- Filter state ---

export interface HistoryFilter {
  folder?: string;
  tag?: string;
  is_favorite?: boolean;
  search?: string;
  sort_by?: string;
  sort_order?: string;
}
