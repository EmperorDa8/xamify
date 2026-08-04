/**
 * What changed between the timetable the student uploaded before and the one
 * they just uploaded.
 *
 * Universities move exams mid-semester, and students typically hear about it
 * second-hand. Showing the delta explicitly — rather than silently swapping the
 * schedule — is the difference between "I re-uploaded a file" and "MTH301 moved
 * to the 7th".
 */
export default function ChangeSummary({ diff, onDismiss }) {
  if (!diff?.hasChanges) return null;

  const { added, removed, changed } = diff;

  // A date change is a genuine reschedule; a venue or time-only edit is not, and
  // calling it "moved" would overstate what happened.
  const isMove = (entry) => entry.changes.some((c) => c.field === "date");
  const movedCount = changed.filter(isMove).length;
  const updatedCount = changed.length - movedCount;

  const headline = [
    movedCount && `${movedCount} moved`,
    updatedCount && `${updatedCount} updated`,
    added.length && `${added.length} added`,
    removed.length && `${removed.length} removed`,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="changes">
      <div className="changes-head">
        <div>
          <span className="coord">since your last upload</span>
          <h2 className="section-h2">
            Your timetable <em>changed</em>
          </h2>
        </div>
        <span className="changes-tally">{headline}</span>
      </div>

      <ul className="change-list">
        {changed.map((entry, i) => (
          <li key={`c-${i}`} className={`ch ${isMove(entry) ? "moved" : "updated"}`}>
            <span className="ch-tag">{isMove(entry) ? "moved" : "updated"}</span>
            <span className="ch-code">{entry.after.course_code}</span>
            <span className="ch-detail">
              {entry.changes.map((c, j) => (
                <span key={j} className="ch-field">
                  {c.label}: <s>{c.from}</s> <b>{c.to}</b>
                </span>
              ))}
            </span>
          </li>
        ))}

        {added.map((exam, i) => (
          <li key={`a-${i}`} className="ch added">
            <span className="ch-tag">added</span>
            <span className="ch-code">{exam.course_code}</span>
            <span className="ch-detail">
              <span className="ch-field">
                {exam.date || "no date"} {exam.time ? `· ${exam.time}` : ""}
                {exam.venue ? ` · ${exam.venue}` : ""}
              </span>
            </span>
          </li>
        ))}

        {removed.map((exam, i) => (
          <li key={`r-${i}`} className="ch removed">
            <span className="ch-tag">removed</span>
            <span className="ch-code">{exam.course_code}</span>
            <span className="ch-detail">
              <span className="ch-field">
                was {exam.date || "undated"} {exam.time ? `· ${exam.time}` : ""}
              </span>
            </span>
          </li>
        ))}
      </ul>

      <p className="table-note">
        Re-sync to update your calendar — events for exams that moved or were removed
        are deleted so an old date can't linger as a phantom exam.
        {onDismiss && (
          <>
            {" "}
            <button className="link-back" onClick={onDismiss}>
              Dismiss
            </button>
          </>
        )}
      </p>
    </div>
  );
}
