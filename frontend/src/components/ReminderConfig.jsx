const PRESETS = [
  { label: "1 week", minutes: 10080 },
  { label: "3 days", minutes: 4320 },
  { label: "1 day", minutes: 1440 },
  { label: "12 hours", minutes: 720 },
  { label: "3 hours", minutes: 180 },
  { label: "1 hour", minutes: 60 },
  { label: "30 min", minutes: 30 },
];

export default function ReminderConfig({ reminders, onChange }) {
  const toggle = (minutes) => {
    if (reminders.includes(minutes)) onChange(reminders.filter((m) => m !== minutes));
    else onChange([...reminders, minutes].sort((a, b) => b - a));
  };

  return (
    <div>
      <h2 className="section-h2">When should we <em>alert</em> you?</h2>
      <p className="coord" style={{ marginBottom: 18 }}>each alert fires before the exam begins</p>
      <div className="presets">
        {PRESETS.map(({ label, minutes }) => {
          const on = reminders.includes(minutes);
          return (
            <button key={minutes} onClick={() => toggle(minutes)} className={`preset${on ? " on" : ""}`}>
              {on && <span className="tick">✓</span>}
              {label} before
            </button>
          );
        })}
      </div>
      {reminders.length === 0 && (
        <p className="alert error" style={{ marginTop: 16 }}>
          <span className="glyph">!</span> Pick at least one reminder time.
        </p>
      )}
    </div>
  );
}
