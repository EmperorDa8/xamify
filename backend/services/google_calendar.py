import os
from datetime import timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from models import ExamEntry
from services.datetime_utils import parse_exam_datetime_in_timezone

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def get_flow() -> Flow:
    client_config = {
        "web": {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "redirect_uris": [os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    return Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback"),
    )


def get_auth_url_and_state() -> tuple[str, str]:
    """Return (consent_url, state). The caller stores `state` in a cookie and
    verifies Google echoes it back on the callback (CSRF protection)."""
    flow = get_flow()
    auth_url, state = flow.authorization_url(prompt="consent", access_type="offline")
    return auth_url, state


def exchange_code(code: str) -> dict:
    flow = get_flow()
    flow.fetch_token(code=code)
    creds = flow.credentials
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes),
    }


def _delete_events_by_key(service, exam_key: str) -> int:
    """Remove every event we previously tagged with `exam_key`. Used to clear
    out an exam that was dropped or moved to a different date."""
    deleted = 0
    events = (
        service.events()
        .list(calendarId="primary", privateExtendedProperty=f"xamioKey={exam_key}")
        .execute()
        .get("items", [])
    )
    for event in events:
        try:
            service.events().delete(calendarId="primary", eventId=event["id"]).execute()
            deleted += 1
        except Exception:
            # An event the user already deleted themselves shouldn't fail the sync.
            pass
    return deleted


def sync_exams_to_google(
    credentials_dict: dict,
    exams: list[ExamEntry],
    reminder_minutes: list[int],
    timezone: str = "UTC",
    stale_keys: list[str] | None = None,
) -> tuple[list[str], int]:
    creds = Credentials(
        token=credentials_dict["token"],
        refresh_token=credentials_dict.get("refresh_token"),
        token_uri=credentials_dict["token_uri"],
        client_id=credentials_dict["client_id"],
        client_secret=credentials_dict["client_secret"],
        scopes=credentials_dict["scopes"],
    )
    service = build("calendar", "v3", credentials=creds)
    event_ids = []

    # Clear orphaned events first, so a moved exam never shows up twice — once
    # on the old date and once on the new one.
    removed = 0
    live_keys = {exam.stable_key() for exam in exams}
    for key in stale_keys or []:
        # Guard against deleting an exam that is still in the schedule (e.g. two
        # courses that normalise to the same key).
        if key not in live_keys:
            removed += _delete_events_by_key(service, key)

    for exam in exams:
        dt_start = parse_exam_datetime_in_timezone(exam.date, exam.time, timezone)
        if dt_start is None:
            continue  # skip unrecoverable rows rather than failing the whole sync
        dt_end = dt_start + timedelta(minutes=exam.duration_minutes or 120)

        description_parts = []
        if exam.course_name:
            description_parts.append(f"Course: {exam.course_name}")
        if exam.venue:
            description_parts.append(f"Venue: {exam.venue}")
        description_parts.append(f"Duration: {exam.duration_minutes or 120} minutes")

        exam_key = exam.stable_key()
        event_body = {
            "summary": f"EXAM: {exam.course_code}",
            "description": "\n".join(description_parts),
            "start": {"dateTime": dt_start.isoformat(), "timeZone": timezone},
            "end": {"dateTime": dt_end.isoformat(), "timeZone": timezone},
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": m} for m in reminder_minutes
                ],
            },
            # Tag the event so a re-sync can find and update it (see below).
            "extendedProperties": {"private": {"xamioKey": exam_key}},
        }
        if exam.venue:
            event_body["location"] = exam.venue

        # Idempotent sync: if we already created an event for this exam
        # (same course+date tag), update it in place instead of inserting a
        # duplicate every time the user clicks "Sync".
        existing = (
            service.events()
            .list(
                calendarId="primary",
                privateExtendedProperty=f"xamioKey={exam_key}",
                maxResults=1,
            )
            .execute()
            .get("items", [])
        )
        if existing:
            created = (
                service.events()
                .update(calendarId="primary", eventId=existing[0]["id"], body=event_body)
                .execute()
            )
        else:
            created = service.events().insert(calendarId="primary", body=event_body).execute()
        event_ids.append(created["id"])

    return event_ids, removed
