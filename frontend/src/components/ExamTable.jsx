import { useState } from "react";

function Cell({ value, onChange, type = "text", className = "" }) {
  return (
    <input
      type={type}
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value)}
      className={`cell-input ${className}`}
    />
  );
}

export default function ExamTable({ exams, onChange }) {
  const [selected, setSelected] = useState(new Set(exams.map((_, i) => i)));

  const emit = (updated, sel) => onChange(updated, sel);

  const toggleAll = () => {
    const next = selected.size === exams.length ? new Set() : new Set(exams.map((_, i) => i));
    setSelected(next);
    emit(exams, next);
  };

  const toggle = (i) => {
    const next = new Set(selected);
    next.has(i) ? next.delete(i) : next.add(i);
    setSelected(next);
    emit(exams, next);
  };

  const updateExam = (index, field, value) => {
    const updated = exams.map((e, i) => (i === index ? { ...e, [field]: value } : e));
    emit(updated, selected);
  };

  const selectedCount = [...selected].filter((i) => i < exams.length).length;

  return (
    <div>
      <div className="table-head">
        <h2>Detected exams<span className="count">{selectedCount}/{exams.length}</span></h2>
        <span className="coord">click any cell to edit</span>
      </div>

      <div className="table-wrap">
        <table className="exams">
          <thead>
            <tr>
              <th style={{ width: 44 }}>
                <input type="checkbox" className="cb"
                  checked={selected.size === exams.length && exams.length > 0}
                  onChange={toggleAll} />
              </th>
              <th>Code</th>
              <th>Course</th>
              <th>Date</th>
              <th>Time</th>
              <th>Min</th>
              <th>Venue</th>
            </tr>
          </thead>
          <tbody>
            {exams.map((exam, i) => (
              <tr key={i} className={selected.has(i) ? "" : "off"}>
                <td>
                  <input type="checkbox" className="cb"
                    checked={selected.has(i)} onChange={() => toggle(i)} />
                </td>
                <td><Cell className="code" value={exam.course_code} onChange={(v) => updateExam(i, "course_code", v)} /></td>
                <td><Cell value={exam.course_name} onChange={(v) => updateExam(i, "course_name", v)} /></td>
                <td><Cell type="date" value={exam.date} onChange={(v) => updateExam(i, "date", v)} /></td>
                <td><Cell type="time" value={exam.time} onChange={(v) => updateExam(i, "time", v)} /></td>
                <td><Cell type="number" value={exam.duration_minutes}
                  onChange={(v) => updateExam(i, "duration_minutes", parseInt(v) || 120)} /></td>
                <td><Cell value={exam.venue} onChange={(v) => updateExam(i, "venue", v)} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="table-note">Uncheck rows to exclude them from your calendar.</p>
    </div>
  );
}
