// Hand-drawn, single-stroke line icons in the editorial style used across
// Xamio (currentColor, fill:none, ~1.5 stroke). These are placeholders the
// hero/feature sections render — swap freely for a branded set later.

const base = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round",
  strokeLinejoin: "round",
};

/* AI parsing — a page being read, with a spark */
export const IconScan = (p) => (
  <svg {...base} {...p}>
    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-8" />
    <path d="M8 8h5M8 12h7M8 16h4" />
    <path d="M18 3l.9 2.1L21 6l-2.1.9L18 9l-.9-2.1L15 6l2.1-.9z" />
  </svg>
);

/* Course matching — crosshair / target */
export const IconTarget = (p) => (
  <svg {...base} {...p}>
    <circle cx="12" cy="12" r="8" />
    <circle cx="12" cy="12" r="3.4" />
    <path d="M12 1.5v3M12 19.5v3M1.5 12h3M19.5 12h3" />
  </svg>
);

/* Calendar sync — calendar with a tick */
export const IconCalendar = (p) => (
  <svg {...base} {...p}>
    <rect x="3.5" y="5" width="17" height="15" rx="2" />
    <path d="M3.5 9.5h17M8 3v4M16 3v4" />
    <path d="M9 14.5l2 2 4-4" />
  </svg>
);

/* Email reminders — bell */
export const IconBell = (p) => (
  <svg {...base} {...p}>
    <path d="M6 9a6 6 0 0 1 12 0c0 6 2 7 2 7H4s2-1 2-7z" />
    <path d="M10.2 20a2 2 0 0 0 3.6 0" />
  </svg>
);

/* Any format — stacked documents */
export const IconLayers = (p) => (
  <svg {...base} {...p}>
    <path d="M9 3.5h6l4 4V18a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V5.5a2 2 0 0 1 2-2z" />
    <path d="M14.5 3.5V8h4.5" />
    <path d="M5 7.5A2 2 0 0 0 3.5 9.5V20a2 2 0 0 0 2 2H15" opacity="0.5" />
  </svg>
);

/* ICS export — tray with down arrow */
export const IconDownload = (p) => (
  <svg {...base} {...p}>
    <path d="M12 3.5v10" />
    <path d="M8 10l4 4 4-4" />
    <path d="M4.5 16.5V18a2.5 2.5 0 0 0 2.5 2.5h10a2.5 2.5 0 0 0 2.5-2.5v-1.5" />
  </svg>
);

/* Offline fallback — lightning */
export const IconBolt = (p) => (
  <svg {...base} {...p}>
    <path d="M13 2.5 4.5 13.5H11l-1 8 8.5-11H12z" />
  </svg>
);

/* Course/privacy — shield with check */
export const IconShield = (p) => (
  <svg {...base} {...p}>
    <path d="M12 2.5l7 2.8v5.4c0 4.6-3 8.4-7 10.8-4-2.4-7-6.2-7-10.8V5.3z" />
    <path d="M8.8 12l2.2 2.2 4.2-4.4" />
  </svg>
);

export const IconArrow = (p) => (
  <svg {...base} {...p}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </svg>
);
