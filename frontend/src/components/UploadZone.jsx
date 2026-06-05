import { useRef, useState } from "react";

const ACCEPTED = ".pdf,.png,.jpg,.jpeg,.webp,.xlsx,.xls,.csv,.docx,.txt";

export default function UploadZone({ onUpload, loading }) {
  const timetableInputRef = useRef(null);
  const coursesInputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [timetableFile, setTimetableFile] = useState(null);
  const [coursesFile, setCoursesFile] = useState(null);
  const [coursesText, setCoursesText] = useState("");

  const upload = (file = timetableFile) => {
    if (file && !loading) {
      onUpload(file, { coursesText, coursesFile });
    }
  };

  const chooseTimetable = (file) => {
    if (!file) return;
    setTimetableFile(file);
    upload(file);
  };

  const onDrop = (event) => {
    event.preventDefault();
    setDragging(false);
    chooseTimetable(event.dataTransfer.files[0]);
  };

  return (
    <div className="upload-grid">
      <div
        onClick={() => timetableInputRef.current?.click()}
        onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`upload${dragging ? " dragging" : ""}${loading ? " loading" : ""}`}
      >
        <input
          ref={timetableInputRef}
          type="file"
          accept={ACCEPTED}
          hidden
          onChange={(event) => chooseTimetable(event.target.files?.[0])}
        />

        <span className="corner tl" /><span className="corner tr" />
        <span className="corner bl" /><span className="corner br" />

        <div className={`upload-mark${loading ? " spin" : ""}`}>
          {loading ? (
            <svg viewBox="0 0 24 24"><path strokeLinecap="round" d="M12 3a9 9 0 1 0 9 9" /></svg>
          ) : (
            <svg viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
            </svg>
          )}
        </div>

        <div style={{ textAlign: "center" }}>
          <h3>{loading ? <>Reading your <em>timetable</em>...</> : <>Drop your <em>timetable</em> here</>}</h3>
          <p className="sub">PDF, image, Excel, CSV, DOCX, or TXT parsed into exact exam dates</p>
          {timetableFile && <p className="file-name">{timetableFile.name}</p>}
        </div>

        {!loading && <span className="chip">Click to browse</span>}
      </div>

      <div className="course-card">
        <div>
          <h3>Registered courses</h3>
          <p className="sub">Paste course codes or upload your course registration file. Matching happens before review.</p>
        </div>

        <textarea
          value={coursesText}
          onChange={(event) => setCoursesText(event.target.value)}
          placeholder={"CSC 201\nMTH 204\nPHY 101"}
          disabled={loading}
        />

        <input
          ref={coursesInputRef}
          type="file"
          accept={ACCEPTED}
          hidden
          onChange={(event) => setCoursesFile(event.target.files?.[0] || null)}
        />

        <div className="course-actions">
          <button type="button" className="btn btn-ghost" disabled={loading} onClick={() => coursesInputRef.current?.click()}>
            Attach file
          </button>
          {coursesFile && <span className="file-name">{coursesFile.name}</span>}
        </div>
      </div>
    </div>
  );
}
