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
    stage: str
    progress: float
    message: str
    created_at: str
