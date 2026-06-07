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


# Month names and common abbreviations -> month number. Covers English plus a
# few frequent non-English forms so worldwide timetables still anchor.
MONTHS: dict[str, int] = {}
for _i, _names in enumerate(
    [
        ("january", "jan", "janvier", "januar", "enero"),
        ("february", "feb", "fevrier", "février", "februar", "febrero"),
        ("march", "mar", "mars", "marz", "märz", "marzo"),
        ("april", "apr", "avril", "abril"),
        ("may", "mai", "mayo"),
        ("june", "jun", "juin", "junio"),
        ("july", "jul", "juillet", "juli", "julio"),
        ("august", "aug", "aout", "août", "agosto"),
        ("september", "sep", "sept", "septembre", "septiembre"),
        ("october", "oct", "octobre", "oktober", "octubre"),
        ("november", "nov", "novembre", "noviembre"),
        ("december", "dec", "decembre", "décembre", "dezember", "diciembre"),
    ],
    start=1,
):
    for _n in _names:
        MONTHS[_n] = _i

_TEXTUAL_MONTH = "|".join(sorted(MONTHS.keys(), key=len, reverse=True))
# "1 June 2026", "1st June, 2026", "Mon 1 Jun 26"  (day before month)
_DMY_TEXT_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s*[,.\-]?\s*({_TEXTUAL_MONTH})\b\.?\s*[,.\-]?\s*(\d{{2,4}})\b",
    re.IGNORECASE,
)
# "June 1, 2026", "Jun 1 2026"  (month before day). A real separator is required
# between the day and the year so "June 2026" isn't carved into day=20, year=26.
_MDY_TEXT_RE = re.compile(
    rf"\b({_TEXTUAL_MONTH})\b\.?\s*[,.\-]?\s*(\d{{1,2}})(?:st|nd|rd|th)?[,.\-\s]+(\d{{2,4}})\b",
    re.IGNORECASE,
)


def _coerce_year(y: int) -> int:
    """Expand a 2-digit year to a 4-digit one (e.g. 26 -> 2026, 98 -> 1998)."""
    if y >= 100:
        return y
    return 2000 + y if y <= 69 else 1900 + y


def _build_iso(y: int, mo: int, d: int) -> Optional[str]:
    try:
        return datetime(_coerce_year(y), mo, d).strftime("%Y-%m-%d")
    except ValueError:
        return None


def normalize_date(value) -> Optional[str]:
    """Coerce loose date strings into 'YYYY-MM-DD', or None if unrecoverable.

    Handles ISO (YYYY-MM-DD), numeric DMY/MDY (with 2- or 4-digit years), and
    textual months in either order ('1 June 2026' / 'June 1, 2026'), with common
    abbreviations and a few non-English month names."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None

    # 1. ISO-ish: YYYY-MM-DD / YYYY/MM/DD
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", s)
    if m:
        y, mo, d = map(int, m.groups())
        return _build_iso(y, mo, d)

    # 2. Numeric DMY/MDY: 01/06/2026, 6-1-26, etc.
    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})$", s)
    if m:
        a, b, y = map(int, m.groups())
        # Disambiguate by the >12 rule; default to DMY (the global majority)
        # since the AI is separately prompted to emit ISO.
        if a > 12 and b <= 12:
            d, mo = a, b
        elif b > 12 and a <= 12:
            mo, d = a, b
        else:
            d, mo = a, b
        return _build_iso(y, mo, d)

    # 3. Textual month, day-first: "1st June, 2026"
    m = _DMY_TEXT_RE.search(s)
    if m:
        d = int(m.group(1)); mo = MONTHS[m.group(2).lower()]; y = int(m.group(3))
        return _build_iso(y, mo, d)

    # 4. Textual month, month-first: "June 1, 2026"
    m = _MDY_TEXT_RE.search(s)
    if m:
        mo = MONTHS[m.group(1).lower()]; d = int(m.group(2)); y = int(m.group(3))
        return _build_iso(y, mo, d)

    return None


# Numeric date anywhere in a blob: 01/06/2026, 2026-06-01, 6.1.26
_NUMERIC_DATE_RE = re.compile(
    r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b"          # ISO  (g1-3)
    r"|\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b"        # DMY/MDY (g4-6)
)


def find_date_anchors(text: str) -> list[tuple[int, str]]:
    """Find every date mention in free text as (character_offset, 'YYYY-MM-DD').

    Recognises textual months in both day-first and month-first order plus
    numeric/ISO dates, so the same routine anchors timetables from any locale.
    Used to map course codes to the date of the block they appear under."""
    anchors: list[tuple[int, str]] = []
    for rx, kind in ((_DMY_TEXT_RE, "dmy"), (_MDY_TEXT_RE, "mdy")):
        for m in rx.finditer(text or ""):
            if kind == "dmy":
                iso = _build_iso(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
            else:
                iso = _build_iso(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))
            if iso:
                anchors.append((m.start(), iso))
    for m in _NUMERIC_DATE_RE.finditer(text or ""):
        if m.group(1):  # ISO
            iso = _build_iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        else:
            a, b, y = int(m.group(4)), int(m.group(5)), int(m.group(6))
            if a > 12 and b <= 12:
                d, mo = a, b
            elif b > 12 and a <= 12:
                mo, d = a, b
            else:
                d, mo = a, b  # default DMY
            iso = _build_iso(y, mo, d)
        if iso:
            anchors.append((m.start(), iso))
    anchors.sort(key=lambda p: p[0])
    return anchors


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
