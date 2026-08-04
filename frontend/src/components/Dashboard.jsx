import { useEffect, useMemo, useState } from "react";

/**
 * The home screen for a student who already has a parsed timetable.
 *
 * Before this, returning to Xamio always meant facing the upload box again —
 * the app behaved like a one-shot tool even though it knew every one of your
 * exam dates. Landing on a countdown turns that stored schedule into something
 * worth opening between uploads.
 */

function examDate(exam) {
  if (!exam?.date) return null;
  // Exams are stored as an ISO date plus HH:MM; treat them as local time, which
  // is what the student means and what the calendar export already assumes.
  const parsed = new Date(`${exam.date}T${exam.time || "00:00"}`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatDay(date) {
  return date.toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

function formatTime(exam) {
  return exam.time || "—";
}

/** Human countdown: the closer the exam, the finer the unit. */
function countdown(target, now) {
  const ms = target - now;
  if (ms <= 0) return null;
  const minutes = Math.floor(ms / 60000);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (days >= 1) {
    const restHours = hours - days * 24;
    return {
      value: days,
      unit: days === 1 ? "day" : "days",
      detail: restHours > 0 ? `and ${restHours} hr${restHours === 1 ? "" : "s"}` : null,
    };
  }
  if (hours >= 1) {
    const restMinutes = minutes - hours * 60;
    return {
      value: hours,
      unit: hours === 1 ? "hour" : "hours",
      detail: restMinutes > 0 ? `and ${restMinutes} min` : null,
    };
  }
  return { value: minutes, unit: minutes === 1 ? "minute" : "minutes", detail: null };
}

export default function Dashboard({
  exams,
  restoredAt,
  onReview,
  onSync,
  onNewUpload,
}) {
  // Re-render each minute so the countdown stays honest without a page refresh.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(timer);
  }, []);

  const { upcoming, past, undated } = useMemo(() => {
    const dated = [];
    const undated = [];
    for (const exam of exams || []) {
      const when = examDate(exam);
      if (when) dated.push({ exam, when });
      else undated.push(exam);
    }
    dated.sort((a, b) => a.when - b.when);
    return {
      upcoming: dated.filter((d) => d.when.getTime() > now),
      past: dated.filter((d) => d.when.getTime() <= now),
      undated,
    };
  }, [exams, now]);

  const next = upcoming[0];
  const remaining = countdown(next?.when ?? 0, now);

  return (
    <div className="stack-lg">
      <div className="dash-head">
        <div>
          <span className="label">
            Your schedule <span className="ix">- No. 01</span>
          </span>
          <h1>
            {upcoming.length > 0 ? (
              <>
                {upcoming.length} exam{upcoming.length === 1 ? "" : "s"} to go
                <span className="dot">.</span>
              </>
            ) : (
              <>
                All done<span className="dot">.</span>
              </>
            )}
          </h1>
        </div>
        <button className="btn btn-ghost" onClick={onNewUpload}>
          Upload a new timetable
        </button>
      </div>

      {next ? (
        <div className="next-exam">
          <div className="ne-left">
            <span className="coord">next exam</span>
            <p className="ne-code">{next.exam.course_code}</p>
            {next.exam.course_name && <p className="ne-name">{next.exam.course_name}</p>}
            <p className="ne-when">
              {formatDay(next.when)} · {formatTime(next.exam)}
              {next.exam.venue ? ` · ${next.exam.venue}` : ""}
            </p>
          </div>
          <div className="ne-right">
            <span className="ne-count">{remaining?.value ?? 0}</span>
            <span className="ne-unit">{remaining?.unit ?? "minutes"}</span>
            {remaining?.detail && <span className="ne-detail">{remaining.detail}</span>}
          </div>
        </div>
      ) : (
        <div className="panel">
          <p className="big">
            <b>No upcoming exams.</b>{" "}
            <span className="roman">
              {past.length > 0 ? "Every exam on this timetable has passed." : "Upload a timetable to get started."}
            </span>
          </p>
        </div>
      )}

      {upcoming.length > 1 && (
        <div>
          <div className="table-head">
            <h2>
              Coming up<span className="count">{upcoming.length - 1}</span>
            </h2>
            <span className="coord">after your next exam</span>
          </div>
          <ul className="exam-feed">
            {upcoming.slice(1).map(({ exam, when }, i) => {
              const away = countdown(when, now);
              return (
                <li key={`${exam.course_code}-${exam.date}-${i}`}>
                  <span className="ef-code">{exam.course_code}</span>
                  <span className="ef-when">
                    {formatDay(when)} · {formatTime(exam)}
                  </span>
                  <span className="ef-venue">{exam.venue || ""}</span>
                  <span className="ef-away">
                    in {away?.value} {away?.unit}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {undated.length > 0 && (
        <div className="alert warn">
          <span className="glyph">⚠</span>
          <div>
            <b>
              {undated.length} exam{undated.length === 1 ? "" : "s"} without a usable date.
            </b>{" "}
            <span>
              {undated.map((e) => e.course_code).join(", ")} — open Review to fix{" "}
              {undated.length === 1 ? "it" : "them"}.
            </span>
          </div>
        </div>
      )}

      {past.length > 0 && (
        <details className="past-exams">
          <summary>
            {past.length} exam{past.length === 1 ? "" : "s"} already sat
          </summary>
          <ul className="exam-feed done">
            {past.map(({ exam, when }, i) => (
              <li key={`${exam.course_code}-${exam.date}-${i}`}>
                <span className="ef-code">{exam.course_code}</span>
                <span className="ef-when">
                  {formatDay(when)} · {formatTime(exam)}
                </span>
                <span className="ef-venue">{exam.venue || ""}</span>
                <span className="ef-away">done</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="row-between dash-actions">
        <button className="link-back" onClick={onReview}>
          Review &amp; edit exams
        </button>
        <button className="btn btn-primary" onClick={onSync}>
          Add to calendar
          <span className="arrow">
            <svg viewBox="0 0 24 24">
              <path d="M5 12h14M13 6l6 6-6 6" />
            </svg>
          </span>
        </button>
      </div>

      {restoredAt && (
        <p className="coord">
          from the timetable you uploaded on{" "}
          {new Date(restoredAt).toLocaleDateString(undefined, {
            day: "numeric",
            month: "long",
            year: "numeric",
          })}
        </p>
      )}
    </div>
  );
}
