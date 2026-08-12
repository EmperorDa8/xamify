import {
  IconScan,
  IconTarget,
  IconCalendar,
  IconBell,
  IconLayers,
  IconDownload,
  IconBolt,
  IconShield,
  IconArrow,
} from "./icons";

const HERO_ICONS = [
  { Icon: IconScan, title: "AI parsing", note: "Reads any timetable" },
  { Icon: IconTarget, title: "Course matching", note: "Only your exams" },
  { Icon: IconCalendar, title: "Calendar sync", note: "One-click export" },
  { Icon: IconBell, title: "Email reminders", note: "Timed before each" },
];

const STEPS = [
  { n: "I", t: "Upload", d: "Drop your timetable — PDF, image, spreadsheet, Word, whatever you've got. Add your registered courses too." },
  { n: "II", t: "Review", d: "AI extracts every exam and matches it to the courses you actually take. Edit anything before you commit." },
  { n: "III", t: "Alerts", d: "Choose your reminder timing — 24 hours and 3 hours before, or whatever keeps you on track." },
  { n: "IV", t: "Sync", d: "Push straight to Google Calendar, download a .ics, and get email alerts before every exam." },
];

const FEATURES = [
  { Icon: IconScan, t: "AI-powered parsing", d: "OpenRouter and Gemini read your timetable in seconds, with an offline rule-based extractor as backup." },
  { Icon: IconLayers, t: "Any file format", d: "PDF, PNG, JPG, XLSX, CSV, DOCX, TXT — if it holds exam data, Xamio can read it." },
  { Icon: IconTarget, t: "Course matching", d: "Upload the courses you registered for and we filter the full timetable down to only your exams." },
  { Icon: IconCalendar, t: "Google Calendar sync", d: "One-click OAuth drops every exam into your calendar with proper titles, times, and venues." },
  { Icon: IconDownload, t: "ICS download", d: "No Google account? Export a standard .ics file and import it into any calendar app." },
  { Icon: IconBell, t: "Email reminders", d: "Scheduled emails land X hours and minutes before each exam — fully configurable." },
];

export default function Landing({ onStart }) {
  return (
    <>
      <div className="side-rail left"><span className="rail-text">Exam Schedule - {new Date().getFullYear()}</span></div>
      <div className="side-rail right"><span className="rail-text">Never miss - Always on time</span></div>

      <div className="shell">
        {/* top bar */}
        <div className="topbar">
          <div className="container topbar-inner">
            <span><b className="coral">●</b> Xamio</span>
            <span className="mid">
              <span>Parsed by AI</span>
              <span>Course matching</span>
              <span>BYO Calendar</span>
            </span>
            <span className="right"><span className="pulse" />Now in early access</span>
          </div>
        </div>

        {/* nav */}
        <header className="nav">
          <div className="container nav-inner">
            <a className="brand" href="#" onClick={(e) => e.preventDefault()}>
              <span className="brand-mark">X</span>
              Xamio
              <span className="brand-meta">Timetable<b>to Calendar</b></span>
            </a>
            <span className="lp-nav-actions">
              <button className="lp-nav-link" onClick={() => onStart("signin")}>Sign in</button>
              <button className="btn btn-primary lp-nav-cta" onClick={() => onStart("signup")}>
                Get started
                <span className="arrow"><IconArrow /></span>
              </button>
            </span>
          </div>
        </header>

        <main className="container">
          {/* hero */}
          <section className="lp-hero">
            <span className="lp-bignum" aria-hidden="true">01</span>
            <div className="lp-hero-head">
              <span className="label">Exam logistics, automated <span className="ix">— No. 01</span></span>
              <h1>
                Never miss an <em>exam</em> again<span className="dot">.</span>
              </h1>
              <p className="lead">
                Upload your university exam timetable and the courses you registered for.
                AI maps each course to the right day, time, code, and venue — then turns it
                into calendar events and email reminders in under a minute.
              </p>
              <div className="lp-cta-row">
                <button className="btn btn-primary" onClick={() => onStart("signup")}>
                  Get started — it's free
                  <span className="arrow"><IconArrow /></span>
                </button>
                <a className="btn btn-ghost" href="#how">See how it works</a>
              </div>
              <p className="lp-microtrust">
                <span className="pulse" /> No credit card · Works with any timetable · Free to start
              </p>
            </div>

            {/* the requested icons, sitting in the hero */}
            <div className="lp-hero-icons">
              {HERO_ICONS.map(({ Icon, title, note }, i) => (
                <article className="lp-icard" key={title} style={{ "--d": `${0.15 + i * 0.09}s` }}>
                  <span className="lp-icard-mark"><Icon /></span>
                  <div>
                    <h3>{title}</h3>
                    <p>{note}</p>
                  </div>
                </article>
              ))}
            </div>
          </section>

          {/* format ticker */}
          <div className="lp-ticker" aria-hidden="true">
            <div className="lp-ticker-row">
              {Array(2).fill(["PDF", "PNG", "JPG", "XLSX", "CSV", "DOCX", "TXT", "GOOGLE CALENDAR", "ICS"]).flat().map((f, i) => (
                <span key={i}>{f}<b>·</b></span>
              ))}
            </div>
          </div>

          {/* how it works */}
          <section className="lp-section" id="how">
            <div className="sec-rule">
              <span className="roman">How it works</span>
              <span className="meta-grp"><span>Four steps</span><span>Under a minute</span></span>
            </div>
            <div className="lp-steps">
              {STEPS.map(({ n, t, d }) => (
                <article className="lp-step" key={n}>
                  <span className="lp-step-n">{n}</span>
                  <h3>{t}</h3>
                  <p>{d}</p>
                </article>
              ))}
            </div>
          </section>

          {/* features */}
          <section className="lp-section">
            <div className="sec-rule">
              <span className="roman">Everything you need</span>
              <span className="meta-grp"><span>Built for students</span></span>
            </div>
            <h2 className="lp-section-title">
              From a messy timetable to a <em>calendar that just works</em>.
            </h2>
            <div className="lp-features">
              {FEATURES.map(({ Icon, t, d }) => (
                <article className="lp-feature" key={t}>
                  <span className="lp-feature-mark"><Icon /></span>
                  <h3>{t}</h3>
                  <p>{d}</p>
                </article>
              ))}
            </div>
          </section>

          {/* final CTA */}
          <section className="lp-finalcta">
            <span className="lp-finalcta-glyph" aria-hidden="true"><IconShield /></span>
            <h2>Stop copying exam dates <em>by hand</em>.</h2>
            <p>Create a free account and turn your timetable into reminders before your next deadline sneaks up.</p>
            <button className="btn btn-primary" onClick={() => onStart("signup")}>
              Get started — it's free
              <span className="arrow"><IconArrow /></span>
            </button>
          </section>
        </main>

        {/* footer */}
        <footer className="lp-footer">
          <div className="container lp-footer-inner">
            <span className="brand">
              <span className="brand-mark">X</span>
              Xamio
            </span>
            <span className="lp-footer-meta">Upload · Review · Alerts · Sync</span>
            <span className="coord">© {new Date().getFullYear()} Xamio — never miss an exam</span>
          </div>

          {/* launch-directory badge — sits on its own line so the footer row above keeps its balance */}
          <div className="container lp-footer-badges">
            <a
              href="https://productwatch.io/products/xamio?utm_source=badge"
              target="_blank"
              rel="noopener noreferrer"
              className="lp-badge"
            >
              <img
                src="https://productwatch.io/backend/api/v1/badge/featured?productId=4f9886c3-3497-4eb7-8939-217f21e6ba3b&darkMode=false"
                alt="Xamio — featured on ProductWatch"
                width="260"
                height="54"
                loading="lazy"
              />
            </a>
          </div>
        </footer>
      </div>
    </>
  );
}
