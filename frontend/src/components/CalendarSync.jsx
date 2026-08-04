import { useEffect, useState } from "react";
import axios from "axios";

// Same base as App.jsx: the deployed API (VITE_API_URL) or the same-origin
// "/api" proxy. Hardcoding localhost here broke calendar/ics/email in prod.
const API = import.meta.env.VITE_API_URL || "/api";

export default function CalendarSync({
  exams,
  reminders,
  onSuccess,
  defaultEmail = "",
  // Calendar keys for exams that moved or were dropped since the last upload —
  // the backend deletes those events so an old date can't linger.
  staleKeys = [],
}) {
  const [googleConnected, setGoogleConnected] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [email, setEmail] = useState(defaultEmail);
  const [emailing, setEmailing] = useState(false);
  const [message, setMessage] = useState(null);

  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("google_connected") === "true") {
      setGoogleConnected(true);
      setMessage({ type: "success", text: "Google Calendar connected - ready to sync." });
      window.history.replaceState({}, "", window.location.pathname);
    } else {
      axios.get(`${API}/auth/google/status`, { withCredentials: true })
        .then((response) => setGoogleConnected(response.data.connected))
        .catch(() => {});
    }
  }, []);

  const connectGoogle = async () => {
    try {
      const { data } = await axios.get(`${API}/auth/google`, { withCredentials: true });
      window.location.href = data.auth_url;
    } catch (e) {
      setMessage({ type: "error", text: e.response?.data?.detail || "Google Calendar not configured." });
    }
  };

  const syncGoogle = async () => {
    setSyncing(true);
    setMessage(null);
    try {
      const { data } = await axios.post(
        `${API}/sync/google`,
        { exams, reminder_minutes: reminders, timezone, stale_keys: staleKeys },
        { withCredentials: true },
      );
      setMessage({ type: "success", text: data.message, notes: data.warnings });
      onSuccess?.("google");
    } catch (e) {
      setMessage({ type: "error", text: e.response?.data?.detail || "Sync failed." });
    } finally {
      setSyncing(false);
    }
  };

  const downloadIcs = async () => {
    setDownloading(true);
    setMessage(null);
    try {
      const response = await axios.post(
        `${API}/download/ics`,
        { exams, reminder_minutes: reminders, timezone },
        { responseType: "blob", withCredentials: true },
      );
      const url = URL.createObjectURL(new Blob([response.data], { type: "text/calendar" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "exams.ics";
      anchor.click();
      URL.revokeObjectURL(url);
      setMessage({ type: "success", text: "Downloaded exams.ics - open it to import into any calendar app." });
      onSuccess?.("ics");
    } catch {
      setMessage({ type: "error", text: "Download failed." });
    } finally {
      setDownloading(false);
    }
  };

  const sendEmailAlerts = async () => {
    setEmailing(true);
    setMessage(null);
    try {
      const { data } = await axios.post(
        `${API}/alerts/email`,
        { email, exams, reminder_minutes: reminders, timezone },
        { withCredentials: true },
      );
      setMessage({ type: "success", text: data.message, notes: data.warnings });
      onSuccess?.("email");
    } catch (e) {
      let text;
      if (e.response) {
        if (e.response.status === 429) {
          text = "Too many attempts in a short time. Please wait a minute and try again.";
        } else {
          text =
            e.response.data?.detail ||
            e.response.data?.error ||
            `Server error (${e.response.status}). Please try again.`;
        }
      } else {
        // No response — usually the backend is waking from sleep (free tier).
        text = "Couldn't reach the server — it may be waking up. Wait ~30 seconds and try again.";
      }
      setMessage({ type: "error", text });
    } finally {
      setEmailing(false);
    }
  };

  const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  const disabled = exams.length === 0 || reminders.length === 0;

  return (
    <div>
      <h2 className="section-h2">Add to your <em>calendar</em></h2>
      <p className="coord" style={{ marginBottom: 20 }}>{exams.length} exam{exams.length !== 1 ? "s" : ""} - {reminders.length} alert{reminders.length !== 1 ? "s" : ""} each</p>

      <div className="sync-grid">
        <button onClick={downloadIcs} disabled={disabled || downloading} className="sync-option">
          <div className="so-mark">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5" />
            </svg>
          </div>
          <div>
            <div className="so-title">{downloading ? "Preparing..." : "Download .ics"}</div>
            <div className="so-sub">Apple Calendar, Outlook, and other calendar apps</div>
          </div>
        </button>

        <button onClick={googleConnected ? syncGoogle : connectGoogle}
          disabled={googleConnected && (disabled || syncing)} className="sync-option">
          <div className="so-mark">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2zm-1 14.5v-9l7 4.5-7 4.5z" />
            </svg>
          </div>
          <div>
            <div className="so-title">
              {!googleConnected ? "Connect Google" : syncing ? "Syncing..." : "Sync to Google"}
            </div>
            <div className="so-sub">{googleConnected ? "Connected - push events now" : "Sign in with Google Calendar"}</div>
          </div>
          {googleConnected && <span className="so-status" />}
        </button>
      </div>

      <div className="email-alerts">
        <div>
          <h3 className="so-title">Email me alerts</h3>
          <p className="so-sub">A schedule summary now, plus a reminder email before each exam.</p>
        </div>
        <div className="email-row">
          <input
            type="email"
            className="email-input"
            placeholder="you@example.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            disabled={emailing}
          />
          <button
            className="btn btn-primary"
            onClick={sendEmailAlerts}
            disabled={disabled || emailing || !emailValid}
          >
            {emailing ? "Sending..." : "Send alerts"}
          </button>
        </div>
      </div>

      {message && (
        <div className={`alert ${message.type}`} style={{ marginTop: 18 }}>
          <span className="glyph">{message.type === "success" ? "✓" : "!"}</span>
          <span>{message.text}</span>
        </div>
      )}

      {/* Non-blocking schedule notes from the backend — e.g. two exams whose
          times overlap on the same day. The export already went through; this
          is a nudge to double-check, not a failure. */}
      {message?.notes?.length > 0 && (
        <div className="alert warn" style={{ marginTop: 12 }}>
          <span className="glyph">⚠</span>
          <div>
            <b>Worth a second look:</b>
            <ul className="warn-list">
              {message.notes.map((note, i) => <li key={i}>{note}</li>)}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
