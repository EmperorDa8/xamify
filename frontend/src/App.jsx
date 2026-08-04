import { useEffect, useState } from "react";
import axios from "axios";
import UploadZone from "./components/UploadZone";
import ExamTable from "./components/ExamTable";
import ReminderConfig from "./components/ReminderConfig";
import CalendarSync from "./components/CalendarSync";
import PublicSite from "./components/PublicSite";
import Dashboard from "./components/Dashboard";
import ChangeSummary from "./components/ChangeSummary";
import { useAuth } from "./auth/AuthProvider";
import { logEvent } from "./lib/analytics";
import {
  saveSchedule,
  loadLatestSchedule,
  replaceScheduleExams,
  diffSchedules,
  staleKeysFor,
} from "./lib/schedules";

const API = import.meta.env.VITE_API_URL || "/api";
const STEPS = ["Upload", "Review", "Alerts", "Sync"];
const ROMAN = ["I", "II", "III", "IV"];

export default function App() {
  const { user, loading: authLoading, signOut } = useAuth();
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [exams, setExams] = useState([]);
  const [selectedExams, setSelectedExams] = useState([]);
  const [registeredCourses, setRegisteredCourses] = useState([]);
  const [unmatchedCourses, setUnmatchedCourses] = useState([]);
  const [reminders, setReminders] = useState([1440, 180]);
  const [synced, setSynced] = useState(false);
  const [modelUsed, setModelUsed] = useState(null);
  const [dateWarnings, setDateWarnings] = useState([]);
  // Persistence: id of the stored schedule backing what's on screen, plus a
  // note when this session's state came from the database rather than an upload.
  const [scheduleId, setScheduleId] = useState(null);
  const [restoredAt, setRestoredAt] = useState(null);
  const [startedFresh, setStartedFresh] = useState(false);
  // "dashboard" is the home for someone who already has a schedule; "wizard" is
  // the upload → review → alerts → sync flow.
  const [view, setView] = useState("wizard");
  // What a re-upload changed versus the stored timetable, plus the calendar keys
  // that re-syncing needs to delete.
  const [changes, setChanges] = useState(null);
  const [staleKeys, setStaleKeys] = useState([]);
  // The schedule as it stood before this upload — kept so a re-upload can be
  // diffed against it rather than silently overwriting it.
  const [previousExams, setPreviousExams] = useState([]);

  // Bring back the last schedule this user parsed. Without this, a refresh (or
  // simply returning the next day) dropped everything and forced a re-upload —
  // and another AI parse — for data we already had.
  useEffect(() => {
    if (!user || startedFresh || exams.length > 0) return;
    let cancelled = false;

    (async () => {
      try {
        const saved = await loadLatestSchedule();
        if (cancelled || !saved?.exams?.length) return;
        setExams(saved.exams);
        setSelectedExams(saved.exams);
        setPreviousExams(saved.exams);
        setRegisteredCourses(saved.registeredCourses);
        setUnmatchedCourses(saved.unmatchedCourses);
        setDateWarnings(saved.dateWarnings);
        setModelUsed(saved.modelUsed);
        setScheduleId(saved.id);
        setRestoredAt(saved.createdAt);
        setView("dashboard"); // a countdown home, not the upload box
      } catch (err) {
        // Restoring is a convenience — never block the upload flow over it.
        console.debug("Could not restore saved schedule:", err);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [user, startedFresh, exams.length]);

  const handleUpload = async (file, courseContext = {}) => {
    setLoading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      if (courseContext.coursesText?.trim()) form.append("courses_text", courseContext.coursesText.trim());
      if (courseContext.coursesFile) form.append("courses_file", courseContext.coursesFile);

      const { data } = await axios.post(`${API}/parse`, form);
      setExams(data.exams);
      setSelectedExams(data.exams);
      setRegisteredCourses(data.registered_courses || []);
      setUnmatchedCourses(data.unmatched_courses || []);
      setModelUsed(data.model_used || null);
      setDateWarnings(data.date_warnings || []);

      // Re-uploading a revised timetable should say what moved, not quietly
      // swap the schedule. Also collect the calendar keys that are now orphaned
      // so the next sync can delete those events.
      const diff = previousExams.length
        ? diffSchedules(previousExams, data.exams || [])
        : null;
      setChanges(diff?.hasChanges ? diff : null);
      setStaleKeys(diff?.hasChanges ? await staleKeysFor(diff) : []);

      logEvent("upload", {
        exams: data.exams?.length ?? 0,
        model: data.model_used || null,
        changed: diff?.hasChanges ? diff.changed.length : 0,
        added: diff?.hasChanges ? diff.added.length : 0,
        removed: diff?.hasChanges ? diff.removed.length : 0,
      });

      // Persist immediately, so the parse survives a refresh even if the user
      // never finishes the wizard. A failure here costs them persistence, not
      // the flow — the parsed exams are already in state.
      setRestoredAt(null);
      try {
        setScheduleId(
          await saveSchedule({
            exams: data.exams || [],
            registeredCourses: data.registered_courses || [],
            unmatchedCourses: data.unmatched_courses || [],
            dateWarnings: data.date_warnings || [],
            modelUsed: data.model_used || null,
            sourceFilename: file?.name || null,
          }),
        );
      } catch (err) {
        console.debug("Could not save schedule:", err);
        setScheduleId(null);
      }

      setPreviousExams(data.exams || []);
      setView("wizard");
      setStep(1);
    } catch (e) {
      let msg;
      if (e.response) {
        // Backend responded with an error — show its reason.
        if (e.response.status === 429) {
          msg = "Too many uploads in a short time. Wait a minute and try again.";
        } else {
          msg =
            e.response.data?.detail ||
            e.response.data?.error ||
            `Server error (${e.response.status}). Check the backend logs.`;
        }
      } else {
        // No response at all — the request never reached the backend.
        msg =
          "Can't reach the server. Is the backend running and is VITE_API_URL pointing to it?";
      }
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleExamChange = (updated, selSet) => {
    setExams(updated);
    setSelectedExams(selSet ? updated.filter((_, i) => selSet.has(i)) : updated);
  };

  // Leaving Review is the point the user has signed off on the rows, so that's
  // what we store — otherwise their date corrections would be lost on refresh.
  const handleReviewContinue = async () => {
    if (scheduleId) {
      try {
        await replaceScheduleExams(scheduleId, exams);
      } catch (err) {
        console.debug("Could not save edited exams:", err);
      }
    }
    setStep(2);
  };

  const reset = () => {
    setStep(0);
    setExams([]);
    setSelectedExams([]);
    setRegisteredCourses([]);
    setUnmatchedCourses([]);
    setReminders([1440, 180]);
    setSynced(false);
    setModelUsed(null);
    setDateWarnings([]);
    setError(null);
    setScheduleId(null);
    setRestoredAt(null);
    setChanges(null);
    setStaleKeys([]);
    setPreviousExams([]);
    setView("wizard");
    // Starting over is a deliberate "give me the upload screen", so don't let
    // the restore effect immediately pull the old schedule back in. The stored
    // copy stays put until a new upload replaces it.
    setStartedFresh(true);
  };

  /** From the dashboard: upload a revised timetable. Unlike "start over" this
   *  KEEPS the current schedule in memory, because that is exactly what the new
   *  upload gets diffed against. */
  const startNewUpload = () => {
    setChanges(null);
    setStaleKeys([]);
    setError(null);
    setSynced(false);
    setView("wizard");
    setStep(0);
  };

  /** Back to the countdown home — only meaningful once a schedule exists. */
  const goToDashboard = () => {
    setView("dashboard");
    setError(null);
  };

  const modelLabel = modelUsed
    ? modelUsed.toLowerCase().includes("gemini")
      ? "Gemini 2.5 Flash"
      : modelUsed.toLowerCase().includes("manual")
        ? "Manual extractor (offline)"
        : `OpenRouter (${modelUsed})`
    : null;

  // Auth gate: the whole app requires a signed-in user.
  if (authLoading) {
    return (
      <div className="auth-wrap">
        <div className="auth-loading"><span className="pulse" /> Loading…</div>
      </div>
    );
  }
  if (!user) return <PublicSite />;

  return (
    <>
      <div className="side-rail left"><span className="rail-text">Exam Schedule - {new Date().getFullYear()}</span></div>
      <div className="side-rail right"><span className="rail-text">Never miss - Always on time</span></div>

      <div className="shell">
        <div className="topbar">
          <div className="container topbar-inner">
            <span><b className="coral">●</b> Xamio</span>
            <span className="mid">
              <span>Parsed by AI</span>
              <span>Course matching</span>
              <span>BYO Calendar</span>
            </span>
            <span className="right auth-chip">
              <span className="pulse" />
              <span className="auth-email">{user.email}</span>
              <button className="auth-signout" onClick={signOut}>Sign out</button>
            </span>
          </div>
        </div>

        <header className="nav">
          <div className="container nav-inner">
            <a
              className="brand"
              href="#"
              onClick={(event) => {
                event.preventDefault();
                // With a schedule in hand, home is the countdown — not a blank
                // upload box that throws away what we already parsed.
                exams.length > 0 ? goToDashboard() : reset();
              }}
            >
              <span className="brand-mark">X</span>
              Xamio
              <span className="brand-meta">Timetable<b>to Calendar</b></span>
            </a>
            {view === "wizard" && exams.length > 0 && (
              <button className="nav-reset" onClick={goToDashboard}>My schedule</button>
            )}
            {view === "wizard" && step > 0 && (
              <button className="nav-reset" onClick={reset}>Start over</button>
            )}
          </div>
        </header>

        <main className="container page">
          {view === "dashboard" ? (
            <Dashboard
              exams={exams}
              restoredAt={restoredAt}
              onReview={() => { setView("wizard"); setStep(1); }}
              onSync={() => { setView("wizard"); setStep(3); }}
              onNewUpload={startNewUpload}
            />
          ) : (
          <>
          <div className="sec-rule">
            <span className="roman">{ROMAN[step]}.</span>
            <span className="meta-grp">
              <span>Step {step + 1} of {STEPS.length}</span>
              <span>{STEPS[step]}</span>
            </span>
          </div>

          <div className="stepper" style={{ marginBottom: 56 }}>
            {STEPS.map((label, i) => (
              <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
                <span className={`step${i === step ? " active" : i < step ? " done" : ""}`}>
                  <span className="ring">{i < step ? "✓" : ROMAN[i]}</span>
                  {label}
                </span>
                {i < STEPS.length - 1 && <span className={`bar${i < step ? " on" : ""}`} />}
              </span>
            ))}
          </div>

          {step === 0 && (
            <div className="stack-lg">
              <div className="hero-split">
                <div className="hero-head">
                  <span className="label">Exam logistics, automated <span className="ix">- No. 01</span></span>
                  <h1>Never miss an <em>exam</em> again<span className="dot">.</span></h1>
                  <p className="lead">
                    Upload your university exam timetable and the courses you registered for.
                    AI maps each registered course to the correct exam day, time, code, and venue,
                    then turns the result into calendar and email alerts.
                  </p>
                  <ul className="hero-trust">
                    <li><span className="ht-dot" />AI parsing with an offline fallback</li>
                    <li><span className="ht-dot" />Google Calendar &amp; .ics export</li>
                    <li><span className="ht-dot" />Email reminders before every exam</li>
                  </ul>
                </div>
                <figure className="hero-art" aria-hidden="true">
                  <img
                    src="/hero-illustration.png"
                    alt=""
                    onError={(e) => {
                      const split = e.currentTarget.closest(".hero-split");
                      if (split) split.style.gridTemplateColumns = "1fr";
                      e.currentTarget.closest(".hero-art").style.display = "none";
                    }}
                  />
                </figure>
              </div>
              <UploadZone onUpload={handleUpload} loading={loading} />
              {error && <div className="alert error"><span className="glyph">!</span><span>{error}</span></div>}
            </div>
          )}

          {step === 1 && (
            <div className="stack-lg">
              {restoredAt && (
                <div className="alert info">
                  <span className="glyph">↺</span>
                  <div>
                    <b>Picked up where you left off.</b>{" "}
                    <span>
                      This is the timetable you uploaded on{" "}
                      {new Date(restoredAt).toLocaleDateString(undefined, {
                        day: "numeric", month: "long", year: "numeric",
                      })}
                      .
                    </span>{" "}
                    <button className="link-back" onClick={startNewUpload}>
                      Upload a revised one
                    </button>
                  </div>
                </div>
              )}
              <ChangeSummary diff={changes} onDismiss={() => setChanges(null)} />
              {modelLabel && (
                <span className="coord">parsed by {modelLabel}</span>
              )}
              {dateWarnings.length > 0 && (
                <div className="alert warn">
                  <span className="glyph">⚠</span>
                  <div>
                    <b>{dateWarnings.length} date{dateWarnings.length > 1 ? "s" : ""} checked against your timetable.</b>
                    <ul className="warn-list">
                      {dateWarnings.map((w, i) => <li key={i}>{w}</li>)}
                    </ul>
                    <span className="coord">Rows flagged with ⚠ couldn't be auto-confirmed — please verify before syncing.</span>
                  </div>
                </div>
              )}
              {(registeredCourses.length > 0 || unmatchedCourses.length > 0) && (
                <div className="match-summary">
                  <div>
                    <span className="coord">course matching</span>
                    <p>
                      <b>{selectedExams.length}</b> exam{selectedExams.length !== 1 ? "s" : ""} matched
                      {registeredCourses.length > 0 ? ` from ${registeredCourses.length} registered course${registeredCourses.length === 1 ? "" : "s"}` : ""}.
                    </p>
                  </div>
                  {unmatchedCourses.length > 0 && (
                    <div className="unmatched">
                      <span className="coord">not found</span>
                      <p>{unmatchedCourses.join(", ")}</p>
                    </div>
                  )}
                </div>
              )}
              <ExamTable exams={exams} onChange={handleExamChange} />
              <div className="row-end">
                <button className="btn btn-primary" disabled={selectedExams.length === 0} onClick={handleReviewContinue}>
                  Continue
                  <span className="arrow"><svg viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6" /></svg></span>
                </button>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="stack-lg">
              <div className="panel">
                <p className="big">
                  <b>{selectedExams.length} exam{selectedExams.length !== 1 ? "s" : ""}</b> ready to schedule.
                </p>
              </div>
              <ReminderConfig reminders={reminders} onChange={setReminders} />
              <div className="row-between">
                <button className="link-back" onClick={() => setStep(1)}>Back</button>
                <button className="btn btn-primary" disabled={reminders.length === 0} onClick={() => setStep(3)}>
                  Continue
                  <span className="arrow"><svg viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6" /></svg></span>
                </button>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="stack-lg">
              {synced && (
                <div className="panel" style={{ borderColor: "var(--olive)" }}>
                  <p className="big"><b>You're all set.</b> <span className="roman">Good luck on your exams.</span></p>
                </div>
              )}
              <CalendarSync
                exams={selectedExams}
                reminders={reminders}
                defaultEmail={user.email || ""}
                staleKeys={staleKeys}
                onSuccess={(channel) => {
                  setSynced(true);
                  // Events for moved/dropped exams are cleared on the first
                  // sync; keeping the keys would re-delete on every later sync.
                  setStaleKeys([]);
                  logEvent("sync", { exams: selectedExams.length, channel: channel || null });
                }}
              />
              <div className="row-between">
                <button className="link-back" onClick={() => setStep(2)}>Back</button>
                {exams.length > 0 && (
                  <button className="link-back" onClick={goToDashboard}>My schedule</button>
                )}
              </div>
            </div>
          )}
          </>
          )}
        </main>
      </div>
    </>
  );
}
