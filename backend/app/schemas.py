from enum import StrEnum

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
    video_url: str | None = None
    file_name: str | None = None
    platform: str | None = None
    language: str | None = None
    source_type: str | None = None


class TaskListResponse(BaseModel):
    items: list[TaskListItem]
    total: int
    page: int
    limit: int


# Provider / Settings schemas


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
