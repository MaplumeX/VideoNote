from enum import StrEnum

from pydantic import BaseModel, HttpUrl


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
