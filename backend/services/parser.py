import io
import json
import os
import re
import pdfplumber
import pytesseract
from PIL import Image
from models import ExamEntry, ParsedTimetable
from services.datetime_utils import normalize_date, normalize_time


OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT_SECONDS", "45"))

_openrouter_client = None
_gemini_client = None


def get_openrouter_client():
    """Lazily construct the OpenRouter client (OpenAI-compatible) so a missing
    API key surfaces as a clean request-time error, not a startup crash."""
    global _openrouter_client
    if _openrouter_client is None:
        if not os.getenv("OPENROUTER_API_KEY"):
            raise ValueError(
                "OPENROUTER_API_KEY is not set. Add it to backend/.env to parse timetables."
            )
        from openai import OpenAI

        _openrouter_client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )
    return _openrouter_client


def get_gemini_client():
    """Lazily construct the Gemini client used as a fallback when OpenRouter fails."""
    global _gemini_client
    if _gemini_client is None:
        if not os.getenv("GEMINI_API_KEY"):
            raise ValueError("GEMINI_API_KEY is not set.")
        from google import genai

        # google-genai auto-reads GOOGLE_API_KEY, not GEMINI_API_KEY — pass it.
        _gemini_client = genai.Client(
            api_key=os.getenv("GEMINI_API_KEY"),
            http_options={"timeout": int(LLM_TIMEOUT * 1000)},  # ms
        )
    return _gemini_client


OPENROUTER_HEADERS = {
    "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost:5173"),
    "X-Title": os.getenv("OPENROUTER_SITE_NAME", "ExamSync"),
}


def _call_openrouter(prompt: str) -> str:
    """Single-shot JSON extraction. Forces JSON output, deterministic sampling,
    and excludes reasoning tokens (not needed for a one-turn parse). Retries
    without the strict params if the model rejects them."""
    client = get_openrouter_client()
    messages = [{"role": "user", "content": prompt}]
    try:
        completion = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=messages,
            max_tokens=8192,
            temperature=0,
            response_format={"type": "json_object"},
            extra_headers=OPENROUTER_HEADERS,
            extra_body={"reasoning": {"exclude": True}},
            timeout=LLM_TIMEOUT,
        )
    except Exception:
        # Some models reject response_format / reasoning — retry plainly.
        completion = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=messages,
            max_tokens=8192,
            temperature=0,
            extra_headers=OPENROUTER_HEADERS,
            timeout=LLM_TIMEOUT,
        )
    # OpenRouter can return HTTP 200 with an error body and no choices
    # (model unavailable, rate-limited, etc.) — surface that instead of crashing.
    if not getattr(completion, "choices", None):
        err = getattr(completion, "error", None) or getattr(completion, "model_extra", None)
        raise RuntimeError(f"OpenRouter returned no choices: {err}")
    return (completion.choices[0].message.content or "").strip()


def _call_gemini(prompt: str) -> str:
    response = get_gemini_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    return (response.text or "").strip()


EXTRACTION_PROMPT = """You are an exam timetable parser for students.

The timetable is often a GRID/MATRIX. Read it carefully:
- Each ROW starts with a day and date, e.g. "Monday, 1st June, 2026".
- Each COLUMN corresponds to a fixed exam TIME shown in the header row,
  e.g. "8:30am", "11am", "2pm".
- A single cell can contain MULTIPLE courses (a course code + a course title,
  sometimes several stacked together). EACH course code is its own exam.
- An exam's DATE comes from its row; its TIME comes from the column header
  above it. So a course under the "11am" column on the "Monday, 1st June, 2026"
  row is an exam on 2026-06-01 at 11:00.

{courses_section}

Return a single JSON object: {{"exams": [ ... ]}}
Each exam object must have exactly these fields:
- course_code: string, exactly as written (e.g. "CIT216")
- course_name: string or null
- date: string in YYYY-MM-DD format
- time: string in HH:MM 24h format (8:30am -> "08:30", 11am -> "11:00", 2pm -> "14:00")
- duration_minutes: integer or null, default 120 if not specified
- venue: string or null

Rules:
- If the year is not specified, infer it from context.
- Only output the JSON object, no explanation.

Timetable text:
{text}
"""


def build_prompt(raw_text: str, registered: list[str]) -> str:
    if registered:
        codes = ", ".join(registered)
        courses_section = (
            "ONLY return exams for these registered courses (match the course code "
            "ignoring spaces, punctuation and case). Ignore every other course:\n"
            f"{codes}"
        )
    else:
        courses_section = "Extract EVERY exam in the timetable. Do not omit any course."
    return EXTRACTION_PROMPT.format(text=raw_text, courses_section=courses_section)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            # Try extracting tables first for structured data
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if row:
                        text_parts.append(" | ".join(str(c) for c in row if c))
            # Also grab raw text
            raw = page.extract_text()
            if raw:
                text_parts.append(raw)
    return "\n".join(text_parts)


def extract_text_from_image(file_bytes: bytes) -> str:
    image = Image.open(io.BytesIO(file_bytes))
    return pytesseract.image_to_string(image)


def extract_text_from_excel(file_bytes: bytes) -> str:
    import pandas as pd
    sheets = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None)
    return "\n\n".join(
        f"Sheet: {name}\n{df.to_string(index=False)}" for name, df in sheets.items()
    )


def extract_text_from_csv(file_bytes: bytes) -> str:
    import pandas as pd
    df = pd.read_csv(io.BytesIO(file_bytes))
    return df.to_string(index=False)


def extract_text_from_docx(file_bytes: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(file_bytes))
    text_parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                text_parts.append(" | ".join(cells))
    return "\n".join(text_parts)


def extract_text_from_plaintext(file_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("utf-8", errors="replace")


def extract_raw_text(filename: str, file_bytes: bytes) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "pdf":
        return extract_text_from_pdf(file_bytes)
    elif ext in ("png", "jpg", "jpeg", "webp", "tiff", "bmp"):
        return extract_text_from_image(file_bytes)
    elif ext in ("xlsx", "xls"):
        return extract_text_from_excel(file_bytes)
    elif ext == "csv":
        return extract_text_from_csv(file_bytes)
    elif ext == "docx":
        return extract_text_from_docx(file_bytes)
    elif ext in ("txt", "text"):
        return extract_text_from_plaintext(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def normalize_course_lines(raw_text: str) -> list[str]:
    courses = []
    seen = set()
    for line in re.split(r"[\n,;]+", raw_text or ""):
        cleaned = re.sub(r"\s+", " ", line).strip(" -\t")
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key not in seen:
            seen.add(key)
            courses.append(cleaned)
    return courses


def parse_json_object(content: str) -> dict:
    content = content.strip()
    # Reasoning models (e.g. nemotron) may leak a <think>...</think> block into
    # the content before the JSON. Strip it defensively.
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    if content.startswith("```"):
        parts = content.split("```")
        content = parts[1] if len(parts) > 1 else content
        if content.lstrip().startswith("json"):
            content = content.lstrip()[4:]

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(content[start : end + 1])

    if isinstance(parsed, list):
        return {"exams": parsed, "registered_courses": [], "unmatched_courses": []}
    if not isinstance(parsed, dict):
        raise ValueError("Model returned JSON, but not an object.")
    return parsed


def _norm_code(value: str) -> str:
    """Strip everything but alphanumerics and uppercase, so 'CSC 201', 'csc-201'
    and 'CSC201' all compare equal."""
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def match_exams(
    exams: list[ExamEntry], registered: list[str]
) -> tuple[list[ExamEntry], list[str]]:
    """Filter exams to those matching a registered course, and report which
    registered courses had no exam. Matching is done on normalized course codes
    and names, tolerant of spacing/punctuation/case."""
    if not registered:
        return exams, []

    matched: list[ExamEntry] = []
    matched_regs: set[str] = set()

    for exam in exams:
        code = _norm_code(exam.course_code)
        name = _norm_code(exam.course_name or "")
        for reg in registered:
            r = _norm_code(reg)
            if not r:
                continue
            if r == code or r in code or code in r or (name and r in name):
                matched.append(exam)
                matched_regs.add(reg)
                break

    unmatched = [reg for reg in registered if reg not in matched_regs]
    return matched, unmatched


# --- Deterministic (no-AI) fallback extractor -------------------------------

_MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"],
        start=1,
    )
}

_DATE_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\.?,?\s*(\d{4})?",
    re.IGNORECASE,
)
_CODE_RE = re.compile(r"\b([A-Za-z]{2,4})\s?(\d{3,4})\b")
_TIME_TOKEN_RE = re.compile(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b", re.IGNORECASE)


def _detect_time_columns(text: str) -> list[str]:
    """Find the ordered exam times from the timetable header (e.g. 8:30am, 11am,
    2pm -> ['08:30', '11:00', '14:00'])."""
    for line in text.splitlines():
        tokens = _TIME_TOKEN_RE.findall(line)
        if len(tokens) >= 2:
            return [normalize_time(t.replace(" ", "")) for t in tokens]
    out: list[str] = []
    for t in _TIME_TOKEN_RE.findall(text[:2000]):
        nt = normalize_time(t.replace(" ", ""))
        if nt and nt not in out:
            out.append(nt)
    return out


def manual_extract(raw_text: str, registered: list[str]) -> list[ExamEntry]:
    """No-AI fallback. Locates each registered course code in the timetable grid
    and infers its date (nearest preceding date row) and time (column position).
    Best-effort — anything imperfect can be fixed in the editable review table."""
    if not registered:
        return []

    # Repair a year that wrapped onto the next line: "June,\n2026" -> "June 2026".
    text = re.sub(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\.?,?\s*\n\s*(\d{4})",
        r"\1 \2",
        raw_text,
        flags=re.IGNORECASE,
    )

    times = _detect_time_columns(text)
    reg_norm = {_norm_code(r) for r in registered if _norm_code(r)}

    exams: list[ExamEntry] = []
    found: set[str] = set()
    current_date: str | None = None
    current_year: int | None = None

    for line in text.splitlines():
        dm = _DATE_RE.search(line)
        if dm:
            day = int(dm.group(1))
            month = _MONTHS[dm.group(2).lower()]
            if dm.group(3):
                current_year = int(dm.group(3))
            if current_year:
                try:
                    current_date = f"{current_year:04d}-{month:02d}-{day:02d}"
                except Exception:
                    pass

        # Collect genuine course codes, filtering false positives like a month +
        # year ("June 2026") so column indexing stays aligned.
        code_cells = []
        for m in _CODE_RE.finditer(line):
            letters, digits = m.group(1), m.group(2)
            if letters.lower() in _MONTHS:
                continue
            if len(digits) == 4 and digits[:2] in ("19", "20"):  # looks like a year
                continue
            code_cells.append(f"{letters}{digits}")

        # Each code maps to a time column by its order (0 -> 1st time, …).
        for pair_index, code_raw in enumerate(code_cells):
            cn = _norm_code(code_raw)
            if cn in reg_norm and cn not in found:
                if pair_index < len(times) and times[pair_index]:
                    time = times[pair_index]
                elif times:
                    time = times[0]
                else:
                    time = "09:00"
                exams.append(
                    ExamEntry(
                        course_code=code_raw.upper(),
                        course_name=None,
                        date=current_date or "",
                        time=time,
                        duration_minutes=120,
                        venue=None,
                    )
                )
                found.add(cn)

    return exams


def focus_timetable_text(raw_text: str, registered: list[str], max_chars: int = 16000) -> str:
    """Shrink the timetable to only the rows the AI needs: the time-header row,
    every date row (for context), and any row containing a registered course.
    Cuts a 55k-char document to a few KB, so the model responds far faster.
    Falls back to the full text if filtering leaves too little."""
    if not registered:
        return raw_text

    reg = {_norm_code(r) for r in registered if _norm_code(r)}
    kept: list[str] = []
    for line in raw_text.splitlines():
        keep = bool(_TIME_TOKEN_RE.search(line) or _DATE_RE.search(line))
        if not keep:
            for m in _CODE_RE.finditer(line):
                if _norm_code(f"{m.group(1)}{m.group(2)}") in reg:
                    keep = True
                    break
        if keep:
            kept.append(line)

    focused = "\n".join(kept)
    if len(focused) < 40:  # filtered too aggressively — keep the original
        return raw_text
    return focused[:max_chars]


def _exams_from_content(content: str) -> list[ExamEntry]:
    data = parse_json_object(content)
    exams = []
    for entry in data.get("exams", []):
        if not isinstance(entry, dict):
            continue
        # Models sometimes emit placeholder/empty rows (e.g. {"": ""}); skip any
        # row missing the required fields rather than failing the whole parse.
        if not entry.get("course_code") or not entry.get("date") or not entry.get("time"):
            continue
        try:
            exams.append(ExamEntry(**entry))
        except Exception:
            continue
    return exams


def parse_with_claude(raw_text: str, registered: list[str]) -> tuple[list[ExamEntry], str]:
    """Extract exams from the timetable text. Tries OpenRouter first; if it errors
    OR returns zero exams, falls back to Gemini. Returns (exams, model_used)."""
    prompt = build_prompt(raw_text, registered)
    providers = [
        ("gemini", _call_gemini, GEMINI_MODEL),
        ("openrouter", _call_openrouter, OPENROUTER_MODEL),
    ]

    errors = []
    last_model = GEMINI_MODEL
    for name, call, model in providers:
        try:
            content = call(prompt)
        except Exception as e:
            errors.append(f"{name}: {e}")
            continue
        last_model = model
        try:
            exams = _exams_from_content(content)
        except Exception as e:
            errors.append(f"{name} (bad JSON): {e}")
            continue
        if exams:
            return exams, model
        # Got a valid response but zero exams — try the next provider.

    if len(errors) == len(providers):
        raise RuntimeError("All parsers failed. " + " | ".join(errors))
    return [], last_model


def normalize_entries(exams: list[ExamEntry]) -> list[ExamEntry]:
    """Clean recoverable date/time values; leave unrecoverable ones as-is so the
    user can fix them in the editable review table."""
    for exam in exams:
        nd = normalize_date(exam.date)
        nt = normalize_time(exam.time)
        if nd:
            exam.date = nd
        if nt:
            exam.time = nt
    return exams


def parse_timetable(
    filename: str,
    file_bytes: bytes,
    registered_courses_text: str = "",
    registered_courses_filename: str | None = None,
    registered_courses_bytes: bytes | None = None,
) -> ParsedTimetable:
    raw_text = extract_raw_text(filename, file_bytes)
    course_text_parts = [registered_courses_text.strip()] if registered_courses_text.strip() else []
    if registered_courses_filename and registered_courses_bytes:
        course_text_parts.append(extract_raw_text(registered_courses_filename, registered_courses_bytes))
    course_text = "\n".join(part for part in course_text_parts if part)
    registered = normalize_course_lines(course_text) if course_text else []

    exams: list[ExamEntry] = []
    model_used = None

    # Fast path: the instant deterministic extractor. If it cleanly resolves
    # EVERY registered course (with a date and time), skip the AI entirely.
    if registered:
        manual = manual_extract(raw_text, registered)
        if (
            len(manual) == len(registered)
            and all(e.date and e.time for e in manual)
        ):
            exams, model_used = manual, "manual-extractor"

    # Otherwise use AI — on a focused subset of the timetable so it's fast.
    if not exams:
        try:
            exams, model_used = parse_with_claude(
                focus_timetable_text(raw_text, registered), registered
            )
        except Exception as e:
            print(f"[parse] AI extraction failed, using manual fallback: {e}")
            exams, model_used = [], None
        # Last resort: partial manual result rather than nothing.
        if not exams and registered:
            manual = manual_extract(raw_text, registered)
            if manual:
                exams, model_used = manual, "manual-extractor"

    exams = normalize_entries(exams)
    matched, unmatched = match_exams(exams, registered)

    print(f"[parse] {filename} | model={model_used} | matched {len(matched)}/{len(registered)}")

    return ParsedTimetable(
        exams=matched,
        registered_courses=registered,
        unmatched_courses=unmatched,
        raw_text=raw_text,
        model_used=model_used,
    )
