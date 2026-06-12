<h1 align="center">
  <img src="frontend/public/hero-illustration.png" alt="Xamio" width="60" /><br/>
  Xamio
</h1>

<p align="center">
  <strong>Upload your exam timetable. AI reads it. Your calendar gets it.</strong><br/>
  Never miss an exam — Xamio turns any timetable file into Google Calendar events and email reminders in under a minute.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/AI--Powered-OpenRouter%20%7C%20Gemini-blueviolet?style=flat-square" />
  <img src="https://img.shields.io/badge/Stack-FastAPI%20%2B%20React-informational?style=flat-square" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" />
</p>

---

## What is Xamio?

Universities hand you a timetable. They expect you to manually copy every exam into your calendar. Nobody does. People miss exams.

**Xamio fixes that.**

Drop in your timetable — PDF, image, spreadsheet, Word doc, whatever — and Xamio's AI pipeline extracts every exam, matches it to the courses you're actually registered for, and exports everything straight to Google Calendar with email reminders timed exactly how you want them.

---

## Key Features

| Feature | Details |
|---|---|
| 🤖 **AI Parsing** | Uses OpenRouter (GPT-4o / Claude) with Gemini 2.5 Flash as fallback, plus an offline manual extractor |
| 📄 **Any Format** | PDF, PNG, JPG, XLSX, CSV, DOCX, TXT — if it has exam data, Xamio can read it |
| 🎯 **Course Matching** | Upload your registered courses; AI matches them to the full timetable and filters only your exams |
| 📅 **Google Calendar Sync** | One-click OAuth — all your exams land in your calendar with proper titles, times, and venues |
| 📥 **ICS Download** | No Google account? Download a standard `.ics` file and import it anywhere |
| 📧 **Email Reminders** | Scheduled emails sent X hours/minutes before each exam — fully configurable |
| ⚡ **Offline Fallback** | Works without any AI API key using the built-in rule-based extractor |

---

## How It Works

```
1. Upload  →  Drop your timetable file (+ optional course list)
2. Review  →  AI extracts and matches your exams — edit anything you need
3. Alerts  →  Choose reminder timing (e.g. 24 hrs + 3 hrs before)
4. Sync    →  Push to Google Calendar or download .ics + get email alerts
```

---

## Tech Stack

**Backend** — Python / FastAPI
- `openrouter` + `google-generativeai` for AI parsing
- `pytesseract` for OCR on image timetables
- `google-api-python-client` for Calendar sync
- `APScheduler` for timed email reminders
- `SQLite` for reminder persistence

**Frontend** — React / Vite
- Clean 4-step wizard UI
- Axios for API calls

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) — for image-based timetables
  - **Windows:** `winget install UB-Mannheim.TesseractOCR`
  - **Mac:** `brew install tesseract`

---

## Setup

### 1. Clone

```bash
git clone https://github.com/<your-username>/xamify.git
cd xamify
```

### 2. Backend

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate
# Mac / Linux
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and fill in your keys:

```env
OPENROUTER_API_KEY=sk-or-...        # Required for AI parsing
GEMINI_API_KEY=...                  # Optional fallback
GOOGLE_CLIENT_ID=...                # Optional — for Google Calendar
GOOGLE_CLIENT_SECRET=...            # Optional — for Google Calendar
SMTP_HOST=smtp.gmail.com            # Optional — for email reminders
SMTP_USER=you@gmail.com
SMTP_PASS=your-app-password
```

### 3. Frontend

```bash
cd frontend
npm install
```

### 4. Google Calendar (optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → enable the **Google Calendar API**
3. Create **OAuth 2.0 credentials** (Web Application type)
4. Add `http://localhost:8000/auth/google/callback` as an Authorised Redirect URI
5. Copy `Client ID` and `Client Secret` into `backend/.env`

---

## Running Locally

```bash
# Terminal 1 — backend
cd backend && uvicorn main:app --reload

# Terminal 2 — frontend
cd frontend && npm run dev
```

Open **http://localhost:5173**

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/parse` | Upload timetable → returns structured exam list |
| `POST` | `/download/ics` | Generate downloadable `.ics` calendar file |
| `POST` | `/alerts/email` | Send summary + schedule reminder emails |
| `GET` | `/auth/google` | Get Google OAuth URL |
| `GET` | `/auth/google/callback` | Handle OAuth callback |
| `GET` | `/auth/google/status` | Check if Google is connected |
| `POST` | `/sync/google` | Push exams to Google Calendar |

---

## Contributing

Pull requests are welcome. For major changes, please open an issue first.

---

## License

MIT © Xamio
