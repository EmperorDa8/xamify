import base64
import json
import os
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

from models import ExamEntry
from services.ical_service import build_ics

RESEND_ENDPOINT = "https://api.resend.com/emails"


def _send_via_resend(to: str, subject: str, text: str, ics_bytes: bytes | None) -> None:
    """Send over Resend's HTTPS API. Works on hosts (e.g. Render) that block
    outbound SMTP ports, since this rides on port 443."""
    api_key = os.getenv("RESEND_API_KEY")
    # Without a verified domain, Resend only allows its shared onboarding sender.
    sender = os.getenv("RESEND_FROM") or "Xamio <onboarding@resend.dev>"
    payload = {"from": sender, "to": [to], "subject": subject, "text": text}
    if ics_bytes:
        payload["attachments"] = [
            {"filename": "exams.ics", "content": base64.b64encode(ics_bytes).decode()}
        ]
    req = urllib.request.Request(
        RESEND_ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Resend is fronted by Cloudflare, which blocks the default
            # "Python-urllib" agent (403 code 1010). Send a normal UA.
            "User-Agent": "Xamio/1.0 (+https://xamify-ten.vercel.app)",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        # Resend rejects any recipient other than the account owner until a
        # sending domain is verified. Surface a clear, user-friendly message
        # (raised as ValueError -> 501) instead of a raw API dump.
        if e.code == 403 and ("verify a domain" in detail or "your own email address" in detail):
            raise ValueError(
                "Email alerts aren't available for this address yet. For now, use "
                "“Download .ics” or “Connect Google Calendar” to add your exams — "
                "email reminders for everyone are coming soon."
            )
        raise RuntimeError(f"Resend API error {e.code}: {detail}")


def _send_via_smtp(to: str, subject: str, text: str, ics_bytes: bytes | None) -> None:
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM", user or "")
    if not user or not password:
        raise ValueError(
            "Email is not configured. Set RESEND_API_KEY (recommended for hosting), "
            "or SMTP_USER + SMTP_PASSWORD for local SMTP."
        )
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(text)
    if ics_bytes:
        msg.add_attachment(ics_bytes, maintype="text", subtype="calendar", filename="exams.ics")
    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)


def _send(to: str, subject: str, text: str, ics_bytes: bytes | None = None) -> None:
    """Prefer the Resend HTTP API when configured (works on Render and other
    hosts that block SMTP); otherwise fall back to direct SMTP for local dev."""
    if os.getenv("RESEND_API_KEY"):
        _send_via_resend(to, subject, text, ics_bytes)
    else:
        _send_via_smtp(to, subject, text, ics_bytes)


def _format_exam(exam: ExamEntry) -> str:
    bits = [f"{exam.course_code}"]
    if exam.course_name:
        bits.append(f"({exam.course_name})")
    line = " ".join(bits)
    when = f"{exam.date} at {exam.time}"
    venue = f" — {exam.venue}" if exam.venue else ""
    return f"  • {line}\n      {when}{venue}"


def send_summary_email(
    to: str, exams: list[ExamEntry], reminder_minutes: list[int], timezone: str = "UTC"
) -> None:
    """One immediate email listing every exam, with the .ics attached."""
    ordered = sorted(exams, key=lambda e: (e.date or "", e.time or ""))
    lines = [_format_exam(e) for e in ordered]
    body = (
        f"Here is your exam schedule ({len(exams)} exam"
        f"{'s' if len(exams) != 1 else ''}):\n\n"
        + "\n".join(lines)
        + "\n\nThe attached exams.ics can be imported into any calendar app.\n"
        + "You will also receive reminder emails before each exam.\n\n"
        + "— Xamio"
    )
    ics = build_ics(exams, reminder_minutes, timezone)
    _send(to, f"Your exam schedule — {len(exams)} exam(s)", body, ics_bytes=ics)


def send_reminder_email(to: str, exam: dict) -> None:
    """A single reminder, sent by the dispatcher ahead of an exam. `exam` is a
    plain dict — it round-trips through the queue row's JSON payload."""
    code = exam.get("course_code", "Exam")
    name = exam.get("course_name")
    date = exam.get("date", "")
    time = exam.get("time", "")
    venue = exam.get("venue")
    title = f"{code}" + (f" — {name}" if name else "")
    body = (
        f"Reminder: your exam is coming up.\n\n"
        f"  {title}\n"
        f"  {date} at {time}\n"
        + (f"  Venue: {venue}\n" if venue else "")
        + "\nGood luck!\n\n— Xamio"
    )
    _send(to, f"Exam reminder: {code} on {date} at {time}", body)
