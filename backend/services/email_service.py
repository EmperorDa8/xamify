import os
import smtplib
from email.message import EmailMessage

from models import ExamEntry
from services.ical_service import build_ics


def _config() -> dict:
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM", user or "")
    if not user or not password:
        raise ValueError(
            "Email is not configured. Set SMTP_USER and SMTP_PASSWORD (a Gmail "
            "app password) in backend/.env."
        )
    return {"host": host, "port": port, "user": user, "password": password, "sender": sender}


def _send(to: str, subject: str, text: str, ics_bytes: bytes | None = None) -> None:
    cfg = _config()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["sender"]
    msg["To"] = to
    msg.set_content(text)
    if ics_bytes:
        msg.add_attachment(
            ics_bytes,
            maintype="text",
            subtype="calendar",
            filename="exams.ics",
        )
    with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
        server.starttls()
        server.login(cfg["user"], cfg["password"])
        server.send_message(msg)


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
        + "— ExamSync"
    )
    ics = build_ics(exams, reminder_minutes, timezone)
    _send(to, f"Your exam schedule — {len(exams)} exam(s)", body, ics_bytes=ics)


def send_reminder_email(to: str, exam: dict) -> None:
    """A single reminder, fired by the scheduler ahead of an exam. `exam` is a
    plain dict so it pickles cleanly into the persistent job store."""
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
        + "\nGood luck!\n\n— ExamSync"
    )
    _send(to, f"Exam reminder: {code} on {date} at {time}", body)
