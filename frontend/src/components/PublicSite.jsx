import { useState } from "react";
import Landing from "./Landing";
import Auth from "./Auth";

/**
 * Logged-out experience: a marketing landing page that hands off to the auth
 * screen. The whole app stays gated — this just gives visitors something
 * compelling before they sign up, which is what we measure traction against.
 */
export default function PublicSite() {
  const [view, setView] = useState("landing"); // "landing" | "auth"
  const [authMode, setAuthMode] = useState("signup");

  const start = (mode = "signup") => {
    setAuthMode(mode);
    setView("auth");
    window.scrollTo({ top: 0 });
  };

  if (view === "auth") {
    return <Auth initialMode={authMode} onBack={() => setView("landing")} />;
  }
  return <Landing onStart={start} />;
}
