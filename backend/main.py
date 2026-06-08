import os
import secrets
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, RedirectResponse
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from models import (
    ParsedTimetable,
    SyncRequest,
    SyncResult,
    GoogleAuthResponse,
    EmailAlertRequest,
    EmailAlertResult,
)
from services.parser import parse_timetable
from services.ical_service import build_ics
from services.google_calendar import get_auth_url, exchange_code, sync_exams_to_google
from services.email_service import send_summary_email
from services import scheduler
from services import token_store

load_dotenv()

# Reject uploads larger than this to protect memory and AI token spend.
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Exam Timer API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.on_event("startup")
def _startup():
    scheduler.start()


@app.on_event("shutdown")
def _shutdown():
    scheduler.shutdown()

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Allow the configured production frontend plus localhost. Vercel also issues a
# new preview domain per deploy (e.g. xamify-<hash>-<team>.vercel.app), so we
# additionally allow this project's Vercel subdomains via a regex — overridable
# with FRONTEND_URL_REGEX. This stops CORS from breaking on every redeploy.
_allowed_origins = list({FRONTEND_URL, "http://localhost:5173"})
_origin_regex = os.getenv(
    "FRONTEND_URL_REGEX",
    r"https://xamify[\w-]*\.vercel\.app",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/parse", response_model=ParsedTimetable)
@limiter.limit("5/minute")
async def parse(
    request: Request,
    file: UploadFile = File(...),
    courses_file: UploadFile | None = File(None),
    courses_text: str = Form(""),
):
    allowed = {"pdf", "png", "jpg", "jpeg", "webp", "tiff", "bmp", "xlsx", "xls", "csv", "docx", "txt"}
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )
    courses_bytes = None
    if courses_file and courses_file.filename:
        courses_ext = courses_file.filename.rsplit(".", 1)[-1].lower() if "." in courses_file.filename else ""
        if courses_ext not in allowed:
            raise HTTPException(status_code=400, detail=f"Unsupported course-list file type: .{courses_ext}")
        courses_bytes = await courses_file.read()
        if len(courses_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Course list file too large. Maximum size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
            )

    try:
        result = parse_timetable(
            file.filename,
            file_bytes,
            registered_courses_text=courses_text,
            registered_courses_filename=courses_file.filename if courses_file else None,
            registered_courses_bytes=courses_bytes,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    return result


@app.post("/download/ics")
async def download_ics(body: SyncRequest):
    ics_bytes = build_ics(body.exams, body.reminder_minutes, body.timezone)
    return Response(
        content=ics_bytes,
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=exams.ics"},
    )


@app.post("/alerts/email", response_model=EmailAlertResult)
@limiter.limit("5/minute")
async def email_alerts(request: Request, body: EmailAlertRequest):
    if not body.exams:
        raise HTTPException(status_code=400, detail="No exams to send.")
    try:
        send_summary_email(body.email, body.exams, body.reminder_minutes, body.timezone)
        scheduled = scheduler.schedule_exam_reminders(
            body.email, body.exams, body.reminder_minutes, body.timezone
        )
    except ValueError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not send email: {e}")

    return EmailAlertResult(
        success=True,
        message=(
            f"Summary sent to {body.email}. "
            f"{scheduled} reminder email(s) scheduled before your exams."
        ),
        scheduled=scheduled,
    )


@app.get("/auth/google", response_model=GoogleAuthResponse)
def google_auth():
    if not os.getenv("GOOGLE_CLIENT_ID"):
        raise HTTPException(status_code=501, detail="Google Calendar not configured. Add GOOGLE_CLIENT_ID to .env")
    return {"auth_url": get_auth_url()}


@app.get("/auth/google/callback")
async def google_callback(code: str, request: Request):
    try:
        creds = exchange_code(code)
        # Persist credentials keyed to the session cookie so they survive restarts.
        session_key = request.cookies.get("exam_sync_session") or secrets.token_urlsafe(24)
        token_store.save_credentials(session_key, creds)
        response = RedirectResponse(f"{FRONTEND_URL}?google_connected=true")
        response.set_cookie(
            "exam_sync_session",
            session_key,
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 7,
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/sync/google", response_model=SyncResult)
async def sync_google(body: SyncRequest, request: Request):
    session_key = request.cookies.get("exam_sync_session")
    creds = token_store.get_credentials(session_key)
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated with Google. Connect Google Calendar first.")

    try:
        event_ids = sync_exams_to_google(creds, body.exams, body.reminder_minutes, body.timezone)
        return SyncResult(
            success=True,
            message=f"Created {len(event_ids)} exam event(s) in Google Calendar.",
            event_ids=event_ids,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/auth/google/status")
def google_status(request: Request):
    session_key = request.cookies.get("exam_sync_session")
    connected = token_store.has_credentials(session_key)
    return {"connected": connected}
