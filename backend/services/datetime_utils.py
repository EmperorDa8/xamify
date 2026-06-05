import re
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_MERIDIEM_RE = re.compile(r"(a\.?m\.?|p\.?m\.?)", re.IGNORECASE)


def normalize_time(value) -> Optional[str]:
    """Coerce loose time strings into 'HH:MM' 24h, or None if unrecoverable."""
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None

    meridiem = None
    m = _MERIDIEM_RE.search(s)
    if m:
        meridiem = "pm" if m.group(1).lower().startswith("p") else "am"
        s = _MERIDIEM_RE.sub("", s).strip()

    m = re.match(r"^(\d{1,2})[:.\s]?(\d{2})(?:[:.\s]?\d{2})?$", s)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
    else:
        bare = re.match(r"^(\d{1,2})$", s)
        if bare and meridiem:  # e.g. "2 PM"
            hour, minute = int(bare.group(1)), 0
        else:
            return None

    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    if hour == 24:  # midnight written as 24:00
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def normalize_date(value) -> Optional[str]:
    """Coerce loose date strings into 'YYYY-MM-DD', or None if unrecoverable."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None

    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$", s)
        if not m:
            return None
        a, b, y = map(int, m.groups())
        # Ambiguous separators: assume DD/MM/YYYY. University timetables outside
        # the US dominate this app's audience, and Claude is prompted for ISO —
        # this branch only fires on messy OCR fallbacks.
        if a > 12 and b <= 12:
            d, mo = a, b
        elif b > 12 and a <= 12:
            mo, d = a, b
        else:
            d, mo = a, b

    try:
        return datetime(y, mo, d).strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_exam_datetime(date, time) -> Optional[datetime]:
    """Normalize then parse a (date, time) pair into a naive local datetime."""
    nd = normalize_date(date)
    nt = normalize_time(time)
    if not nd or not nt:
        return None
    try:
        return datetime.fromisoformat(f"{nd}T{nt}:00")
    except ValueError:
        return None


def parse_exam_datetime_in_timezone(date, time, timezone: str = "UTC") -> Optional[datetime]:
    dt = parse_exam_datetime(date, time)
    if dt is None:
        return None
    try:
        tz = ZoneInfo(timezone or "UTC")
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
    return dt.replace(tzinfo=tz)
