from pydantic import BaseModel, ConfigDict, Field
from typing import Optional


class ExamEntry(BaseModel):
    course_code: str
    course_name: Optional[str] = None
    date: str  # ISO format: YYYY-MM-DD
    time: str  # HH:MM
    duration_minutes: Optional[int] = 120
    venue: Optional[str] = None


class ParsedTimetable(BaseModel):
    model_config = ConfigDict(protected_namespaces=())  # allow the "model_used" field

    exams: list[ExamEntry]
    raw_text: Optional[str] = None
    registered_courses: list[str] = Field(default_factory=list)
    unmatched_courses: list[str] = Field(default_factory=list)
    model_used: Optional[str] = None  # which LLM served this parse


class SyncRequest(BaseModel):
    exams: list[ExamEntry]
    reminder_minutes: list[int] = Field(default_factory=lambda: [1440, 180])  # 1 day + 3 hours before
    timezone: str = "UTC"  # IANA tz from the browser, e.g. "Africa/Lagos"


class EmailAlertRequest(BaseModel):
    email: str
    exams: list[ExamEntry]
    reminder_minutes: list[int] = Field(default_factory=lambda: [1440, 180])
    timezone: str = "UTC"


class EmailAlertResult(BaseModel):
    success: bool
    message: str
    scheduled: int = 0


class GoogleAuthResponse(BaseModel):
    auth_url: str


class SyncResult(BaseModel):
    success: bool
    message: str
    event_ids: list[str] = Field(default_factory=list)
