import hashlib
import re
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional


class ExamEntry(BaseModel):
    course_code: str
    course_name: Optional[str] = None
    date: str  # ISO format: YYYY-MM-DD
    time: str  # HH:MM
    duration_minutes: Optional[int] = 120
    venue: Optional[str] = None
    # Set by the date verifier (services.parser.verify_and_correct_dates):
    #   True  -> date confirmed against the uploaded timetable
    #   False -> could not be confirmed; needs the user's attention
    #   None  -> not checked
    date_verified: Optional[bool] = None
    date_note: Optional[str] = None  # human-readable explanation when not a clean match

    def stable_key(self) -> str:
        """Stable identity for calendar exports: same course+date -> same key,
        so a re-export UPDATES the existing event instead of duplicating it
        (used as the ICS UID and as the Google event tag)."""
        code = re.sub(r"[^a-z0-9]", "", (self.course_code or "").lower())
        return hashlib.sha1(f"{code}|{self.date}".encode()).hexdigest()


class ParsedTimetable(BaseModel):
    model_config = ConfigDict(protected_namespaces=())  # allow the "model_used" field

    exams: list[ExamEntry]
    raw_text: Optional[str] = None
    registered_courses: list[str] = Field(default_factory=list)
    unmatched_courses: list[str] = Field(default_factory=list)
    model_used: Optional[str] = None  # which LLM served this parse
    date_warnings: list[str] = Field(default_factory=list)  # date checks that need review


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
