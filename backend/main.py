import logging
import os
import secrets
from datetime import datetime, timedelta
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException, Request, Depends
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
from services.email_service import send_summary_email, send_reminder_email
from services import reminder_queue
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
    # Warm the queue table. Failure is logged, never fatal: a bad DATABASE_URL
    # must not stop the service binding a port, or /health and /parse go down
    # with it even though neither touches Postgres. The tables are created
    # lazily on first use anyway (services/db.prepare).
    try:
        reminder_queue.init()
    except Exception as e:
        logging.getLogger("xamio").error(
            "Database unavailable at startup — reminders and Google Calendar "
            "sync will fail until DATABASE_URL is correct. Error: %s",
            e,
        )

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


def _validate_exam_schedule(exams) -> list[str]:
    """Check a schedule before it reaches a calendar or an inbox.

    Hard-fails (422) only on what we genuinely cannot turn into an event: a
    missing or unparseable date/time. The review table lets the user fix those.

    Sitting two exams on one day is normal at large multi-faculty universities
    (a morning paper and an afternoon paper), so it is NOT an error — blocking
    it stopped those students exporting at all. Only a genuine *time overlap*
    is reported, and as a returned warning rather than a block: an overlap is
    usually a parse slip worth a second look, but it is the university's
    timetable, and refusing to export it helps nobody.
    """
    from services.datetime_utils import parse_exam_datetime

    problems: list[str] = []
    warnings: list[str] = []
    # date -> (course code, start, end) for the exams we could place in time
    by_date: dict[str, list[tuple[str, datetime, datetime]]] = {}

    for exam in exams:
        start = parse_exam_datetime(exam.date, exam.time)
        if start is None:
            problems.append(
                f"{exam.course_code}: invalid or missing date/time "
                f"(date={exam.date!r}, time={exam.time!r})."
            )
            continue
        end = start + timedelta(minutes=exam.duration_minutes or 120)
        by_date.setdefault(exam.date, []).append((exam.course_code, start, end))

    if problems:
        raise HTTPException(
            status_code=422,
            detail="Schedule check failed: " + " | ".join(problems),
        )

    for date, sittings in by_date.items():
        if len(sittings) < 2:
            continue
        sittings.sort(key=lambda s: s[1])
        for (code_a, _, end_a), (code_b, start_b, _) in zip(sittings, sittings[1:]):
            if start_b < end_a:
                warnings.append(
                    f"{code_a} and {code_b} overlap on {date} "
                    f"({code_a} runs until {end_a:%H:%M}, {code_b} starts at {start_b:%H:%M}). "
                    "Check the times in the review table if that looks wrong."
                )

    return warnings


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
    warnings = _validate_exam_schedule(body.exams)
    try:
        send_summary_email(body.email, body.exams, body.reminder_minutes, body.timezone)
        scheduled = reminder_queue.schedule_exam_reminders(
            body.email,
            body.exams,
            body.reminder_minutes,
            body.timezone,
            user_id=user.get("sub"),
        )
    except ValueError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not send email: {e}")

    if scheduled:
        message = (
            f"Summary sent to {body.email}. "
            f"{scheduled} reminder email(s) queued before your exams."
        )
    else:
        # Nothing queued now means every lead time has already passed — the only
        # remaining reason, since queueing no longer depends on a live scheduler.
        message = (
            f"Summary sent to {body.email} with your full schedule attached. "
            "No timed reminders were queued because every reminder time you "
            "chose has already passed."
        )

    return EmailAlertResult(
        success=True, message=message, scheduled=scheduled, warnings=warnings
    )


def _require_task_key(provided: str | None) -> None:
    """Guard for machine-triggered endpoints.

    Deliberately fails CLOSED, unlike the Supabase user auth: an unconfigured
    TASK_SECRET disables dispatch rather than leaving an endpoint that sends
    mail to anyone who finds it.
    """
    secret = os.getenv("TASK_SECRET")
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Reminder dispatch is not configured. Set TASK_SECRET.",
        )
    if not provided or not secrets.compare_digest(provided, secret):
        raise HTTPException(status_code=401, detail="Invalid task key.")


@app.post("/tasks/dispatch-reminders")
def dispatch_reminders(x_task_key: str | None = Header(default=None)):
    """Send every reminder that has come due. Called on a schedule by pg_cron
    via pg_net; safe to call by hand or to run twice at once.

    Rows are claimed atomically before sending, so overlapping runs take
    disjoint work and no reminder goes out twice. A send that fails goes back on
    the queue until it runs out of attempts, so a transient email outage delays
    delivery instead of losing it.
    """
    _require_task_key(x_task_key)

    reclaimed = reminder_queue.reclaim_stalled()
    due = reminder_queue.claim_due()

    sent = 0
    failed = 0
    for item in due:
        try:
            if item["channel"] == "email":
                send_reminder_email(item["destination"], item["payload"])
            else:
                # whatsapp/sms are queued but have no sender wired up yet.
                raise RuntimeError(f"No sender for channel {item['channel']!r}")
            reminder_queue.mark_sent(item["id"])
            sent += 1
        except Exception as e:
            reminder_queue.mark_failed(
                item["id"], str(e), item["attempts"], item["max_attempts"]
            )
            failed += 1

    return {
        "claimed": len(due),
        "sent": sent,
        "failed": failed,
        "reclaimed": reclaimed,
        "queue": reminder_queue.stats(),
    }


@app.get("/tasks/reminder-stats")
def reminder_stats(x_task_key: str | None = Header(default=None)):
    """Queue health at a glance — the old scheduler could not answer
    "did the reminders actually go out?" at all."""
    _require_task_key(x_task_key)
    return reminder_queue.stats()


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

    warnings = _validate_exam_schedule(body.exams)
    try:
        event_ids, removed = sync_exams_to_google(
            creds,
            body.exams,
            body.reminder_minutes,
            body.timezone,
            stale_keys=body.stale_keys,
        )
        message = f"Synced {len(event_ids)} exam event(s) to Google Calendar."
        if removed:
            message += f" Removed {removed} event(s) for exams that moved or were dropped."
        return SyncResult(
            success=True,
            message=message,
            event_ids=event_ids,
            warnings=warnings,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/auth/google/status")
def google_status(request: Request, user: dict = Depends(require_user)):
    session_key = request.cookies.get("exam_sync_session")
    connected = token_store.has_credentials(session_key)
    return {"connected": connected}
