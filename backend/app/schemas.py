from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, EmailStr, HttpUrl


class VideoSource(StrEnum):
    youtube = "youtube"
    bilibili = "bilibili"
    upload = "upload"


class VideoRequest(BaseModel):
    url: HttpUrl
    language: str = "en"


class TaskStage(StrEnum):
    pending = "pending"
    downloading = "downloading"
    extracting_subtitles = "extracting_subtitles"
    transcribing = "transcribing"
    generating_notes = "generating_notes"
    complete = "complete"
    failed = "failed"
    cancelled = "cancelled"


class TaskProgress(BaseModel):
    job_id: str
    stage: TaskStage = TaskStage.pending
    progress: float = 0.0  # 0.0 ~ 1.0
    message: str = ""


class ProcessResponse(BaseModel):
    job_id: str
    title: str = ""
    thumbnail_url: str = ""
    platform: str = ""


class UploadResponse(BaseModel):
    job_id: str
    file_name: str = ""


class NoteResponse(BaseModel):
    job_id: str
    markdown: str
    title: str | None = None


# Auth schemas


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str


class TaskListItem(BaseModel):
    job_id: str
    stage: TaskStage
    progress: float
    message: str
    created_at: str
    title: str | None = None
    video_url: str | None = None
    file_name: str | None = None
    platform: str | None = None
    language: str | None = None
    source_type: str | None = None
    folder_id: str | None = None
    is_favorite: bool = False
    thumbnail_url: str | None = None


class TaskListResponse(BaseModel):
    items: list[TaskListItem]
    total: int
    page: int
    limit: int


# Provider / Settings schemas


class ModelsRequest(BaseModel):
    api_key: str
    api_base: str
    category: Literal["asr", "llm"]


class ModelItem(BaseModel):
    id: str
    object: str | None = None
    created: int | None = None
    owned_by: str | None = None


class ModelsResponse(BaseModel):
    models: list[ModelItem]
    error: str | None = None


class ProviderPreset(BaseModel):
    provider: str
    models: list[str]
    api_base: str


class ProvidersResponse(BaseModel):
    asr: list[ProviderPreset]
    llm: list[ProviderPreset]


class ProviderConfig(BaseModel):
    provider: str = ""
    model: str = ""
    api_key: str = ""
    api_base: str = ""


class SettingsRequest(BaseModel):
    asr: ProviderConfig | None = None
    llm: ProviderConfig | None = None


class ProviderConfigResponse(BaseModel):
    provider: str
    model: str
    api_key_masked: str
    api_base: str


class SettingsResponse(BaseModel):
    asr: ProviderConfigResponse | None = None
    llm: ProviderConfigResponse | None = None


# Tag schemas


class TagCreate(BaseModel):
    name: str
    color: str = ""


class TagUpdate(BaseModel):
    name: str | None = None
    color: str | None = None


class TagResponse(BaseModel):
    id: str
    user_id: str
    name: str
    color: str
    created_at: str


class TagWithCount(TagResponse):
    note_count: int = 0


# Folder schemas


class FolderCreate(BaseModel):
    name: str
    parent_id: str | None = None
    sort_order: int = 0


class FolderUpdate(BaseModel):
    name: str | None = None
    parent_id: str | None = None


class FolderResponse(BaseModel):
    id: str
    user_id: str
    name: str
    parent_id: str | None = None
    sort_order: int = 0
    created_at: str
    updated_at: str


class FolderWithChildren(FolderResponse):
    note_count: int = 0
    children: list["FolderWithChildren"] = []


# Note-Tag association schemas


class NoteTagAdd(BaseModel):
    tag_ids: list[str] = []
    tag_names: list[str] = []


class FavoriteToggle(BaseModel):
    is_favorite: bool


class NoteFolderUpdate(BaseModel):
    folder_id: str | None = None


class NoteContentUpdate(BaseModel):
    markdown: str
    title: str | None = None


# Batch operation schemas


class BatchTagRequest(BaseModel):
    job_ids: list[str]
    tag_id: str


class BatchMoveRequest(BaseModel):
    job_ids: list[str]
    folder_id: str | None = None


class BatchFavoriteRequest(BaseModel):
    job_ids: list[str]
    is_favorite: bool


class BatchDeleteRequest(BaseModel):
    job_ids: list[str]


# Cookie schemas


class CookieInfoResponse(BaseModel):
    platform: str
    has_cookie: bool
    updated_at: str | None = None
