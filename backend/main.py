import os
import secrets
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Depends
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
from services.google_calendar import get_auth_url_and_state, exchange_code, sync_exams_to_google
from services.email_service import send_summary_email
from services import scheduler
from services import token_store
from services.auth import require_user

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

# In production the frontend (xamio.app) calls this API cross-site
# (onrender.com), and browsers only attach cross-site XHR cookies when they are
# SameSite=None; Secure. Local dev over http://localhost stays Lax (same-site).
_SECURE_COOKIES = FRONTEND_URL.startswith("https")

# Allow the configured production frontend plus localhost. The production site
# is served from the xamio.app custom domain; Vercel also issues a new preview
# domain per deploy (e.g. xamify-<hash>-<team>.vercel.app). We allow the custom
# domain (apex + any subdomain) and this project's Vercel subdomains via a regex
# — overridable with FRONTEND_URL_REGEX. This stops CORS from breaking on every
# redeploy or domain change.
_allowed_origins = list(
    {FRONTEND_URL, "https://xamio.app", "https://www.xamio.app", "http://localhost:5173"}
)
_origin_regex = os.getenv(
    "FRONTEND_URL_REGEX",
    r"https://([\w-]+\.)?xamio\.app|https://xamify[\w-]*\.vercel\.app",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


def _validate_exam_schedule(exams) -> None:
    """Block calendar/email export of a schedule with invalid or clashing
    dates. The review table lets the user fix anything flagged here, so a bad
    date never reaches their calendar silently."""
    from services.datetime_utils import parse_exam_datetime

    problems: list[str] = []
    by_date: dict[str, list[str]] = {}
    for exam in exams:
        if parse_exam_datetime(exam.date, exam.time) is None:
            problems.append(
                f"{exam.course_code}: invalid or missing date/time "
                f"(date={exam.date!r}, time={exam.time!r})."
            )
        if exam.date:
            by_date.setdefault(exam.date, []).append(exam.course_code)

    for date, codes in by_date.items():
        if len(codes) > 1:
            problems.append(
                f"{', '.join(codes)} share the same date ({date}). "
                "Each course must be on its own exam day — fix the dates in the review table."
            )

    if problems:
        raise HTTPException(
            status_code=422,
            detail="Schedule check failed: " + " | ".join(problems),
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
    user: dict = Depends(require_user),
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
async def download_ics(body: SyncRequest, user: dict = Depends(require_user)):
    _validate_exam_schedule(body.exams)
    ics_bytes = build_ics(body.exams, body.reminder_minutes, body.timezone)
    return Response(
        content=ics_bytes,
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=exams.ics"},
    )


@app.post("/alerts/email", response_model=EmailAlertResult)
@limiter.limit("5/minute")
async def email_alerts(
    request: Request, body: EmailAlertRequest, user: dict = Depends(require_user)
):
    if not body.exams:
        raise HTTPException(status_code=400, detail="No exams to send.")
    # With auth enforced, only send to the signed-in user's own address — this
    # endpoint must not double as a spam relay for arbitrary recipients.
    token_email = (user.get("email") or "").strip().lower()
    if token_email and body.email.strip().lower() != token_email:
        raise HTTPException(
            status_code=403,
            detail=f"Alerts can only be sent to your sign-in email ({token_email}).",
        )
    _validate_exam_schedule(body.exams)
    try:
        send_summary_email(body.email, body.exams, body.reminder_minutes, body.timezone)
        scheduled = scheduler.schedule_exam_reminders(
            body.email, body.exams, body.reminder_minutes, body.timezone
        )
    except ValueError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not send email: {e}")

    if scheduled:
        message = (
            f"Summary sent to {body.email}. "
            f"{scheduled} reminder email(s) scheduled before your exams."
        )
    else:
        # No timed reminders were scheduled — either every lead time has already
        # passed, or this host can't run the background scheduler (e.g. a
        # serverless deploy). Don't promise reminders we won't send.
        message = (
            f"Summary sent to {body.email} with your full schedule attached. "
            "Timed reminder emails aren't available right now — add the .ics or "
            "sync to Google Calendar to get alerts before each exam."
        )

    return EmailAlertResult(success=True, message=message, scheduled=scheduled)


@app.get("/auth/google", response_model=GoogleAuthResponse)
def google_auth(request: Request, user: dict = Depends(require_user)):
    if not os.getenv("GOOGLE_CLIENT_ID"):
        raise HTTPException(status_code=501, detail="Google Calendar not configured. Add GOOGLE_CLIENT_ID to .env")
    # Hand back our own /start URL: the browser navigates there top-level, so
    # the CSRF state cookie is set first-party on this origin before Google.
    base = str(request.base_url).rstrip("/")
    return {"auth_url": f"{base}/auth/google/start"}


@app.get("/auth/google/start")
def google_auth_start():
    """Top-level navigation target: stamp the CSRF state cookie, then redirect
    to Google's consent screen. No auth needed — starting a consent flow has no
    side effects and the client id is public anyway."""
    if not os.getenv("GOOGLE_CLIENT_ID"):
        raise HTTPException(status_code=501, detail="Google Calendar not configured. Add GOOGLE_CLIENT_ID to .env")
    auth_url, state = get_auth_url_and_state()
    response = RedirectResponse(auth_url)
    response.set_cookie(
        "oauth_state",
        state,
        httponly=True,
        samesite="lax",  # sent on the top-level redirect back from Google
        secure=_SECURE_COOKIES,
        max_age=600,
    )
    return response


@app.get("/auth/google/callback")
async def google_callback(code: str, request: Request, state: str | None = None):
    # CSRF check: the state Google echoes back must match the cookie stamped by
    # /auth/google/start in this same browser — otherwise an attacker could
    # bind THEIR Google account to the victim's session.
    expected_state = request.cookies.get("oauth_state")
    if not expected_state or not state or not secrets.compare_digest(expected_state, state):
        raise HTTPException(
            status_code=400,
            detail="OAuth state mismatch — restart the Google Calendar connection from the app.",
        )
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
            # None+Secure so later cross-site XHRs (sync/status) include it.
            samesite="none" if _SECURE_COOKIES else "lax",
            secure=_SECURE_COOKIES,
            max_age=60 * 60 * 24 * 7,
        )
        response.delete_cookie("oauth_state")
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/sync/google", response_model=SyncResult)
async def sync_google(
    body: SyncRequest, request: Request, user: dict = Depends(require_user)
):
    session_key = request.cookies.get("exam_sync_session")
    creds = token_store.get_credentials(session_key)
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated with Google. Connect Google Calendar first.")

    _validate_exam_schedule(body.exams)
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
def google_status(request: Request, user: dict = Depends(require_user)):
    session_key = request.cookies.get("exam_sync_session")
    connected = token_store.has_credentials(session_key)
    return {"connected": connected}
