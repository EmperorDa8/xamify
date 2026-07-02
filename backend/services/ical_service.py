# timezone aliased: build_ics has a `timezone: str` parameter that would
# otherwise shadow the datetime module's timezone.
from datetime import datetime, timedelta, timezone as dt_timezone
from icalendar import Calendar, Event, Alarm
from models import ExamEntry
from services.datetime_utils import parse_exam_datetime_in_timezone


def build_ics(exams: list[ExamEntry], reminder_minutes: list[int], timezone: str = "UTC") -> bytes:
    cal = Calendar()
    cal.add("prodid", "-//Exam Timer//exam-timer//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "My Exam Schedule")

    for exam in exams:
        dt_start = parse_exam_datetime_in_timezone(exam.date, exam.time, timezone)
        if dt_start is None:
            continue  # skip rows with unrecoverable date/time rather than failing the batch
        dt_end = dt_start + timedelta(minutes=exam.duration_minutes or 120)

        event = Event()
        # Deterministic UID: re-importing the same schedule updates events
        # in place rather than creating duplicates in the calendar app.
        event.add("uid", f"{exam.stable_key()}@xamio.app")
        event.add("dtstamp", datetime.now(dt_timezone.utc))

        event.add("dtstart", dt_start)
        event.add("dtend", dt_end)
        event.add("summary", f"EXAM: {exam.course_code}")

        description_parts = []
        if exam.course_name:
            description_parts.append(f"Course: {exam.course_name}")
        if exam.venue:
            description_parts.append(f"Venue: {exam.venue}")
        description_parts.append(f"Duration: {exam.duration_minutes or 120} minutes")
        event.add("description", "\n".join(description_parts))

        if exam.venue:
            event.add("location", exam.venue)

        for minutes in reminder_minutes:
            alarm = Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("description", f"Exam reminder: {exam.course_code}")
            alarm.add("trigger", timedelta(minutes=-minutes))
            event.add_component(alarm)

        cal.add_component(event)

    return cal.to_ical()
