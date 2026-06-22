import { useState } from "react";
import { supabase } from "../lib/supabase";

export default function Auth({ initialMode = "signin", onBack }) {
  const [mode, setMode] = useState(initialMode); // "signin" | "signup"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  const isSignup = mode === "signup";

  const handleEmail = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      if (isSignup) {
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
          options: { data: { full_name: fullName.trim() || null } },
        });
        if (error) throw error;
        // When email confirmation is on, there's no active session yet.
        if (!data.session) {
          setNotice("Check your inbox to confirm your email, then sign in.");
        }
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
        // On success, AuthProvider's listener swaps this screen for the app.
      }
    } catch (err) {
      setError(err.message || "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleGoogle = async () => {
    setError(null);
    setNotice(null);
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin },
    });
    if (error) setError(error.message);
  };

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        {onBack && (
          <button type="button" className="link-back auth-back" onClick={onBack}>
            ← Back to home
          </button>
        )}
        <div className="auth-head">
          <span className="brand-mark">X</span>
          <h1>{isSignup ? "Create your account" : "Welcome back"}</h1>
          <p className="lead">
            {isSignup
              ? "Sign up to turn your exam timetable into calendar events and reminders."
              : "Sign in to upload timetables and manage your exam reminders."}
          </p>
        </div>

        <button type="button" className="btn btn-google" onClick={handleGoogle}>
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z" />
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23z" />
            <path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84z" />
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.06l3.66 2.84C6.71 7.3 9.14 5.38 12 5.38z" />
          </svg>
          Continue with Google
        </button>

        <div className="auth-divider"><span>or</span></div>

        <form onSubmit={handleEmail} className="auth-form">
          {isSignup && (
            <label className="auth-field">
              <span>Name</span>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Your name"
                autoComplete="name"
              />
            </label>
          )}
          <label className="auth-field">
            <span>Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@university.edu"
              autoComplete="email"
            />
          </label>
          <label className="auth-field">
            <span>Password</span>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={isSignup ? "At least 8 characters" : "Your password"}
              autoComplete={isSignup ? "new-password" : "current-password"}
            />
          </label>

          {error && <div className="alert error"><span className="glyph">!</span><span>{error}</span></div>}
          {notice && <div className="alert warn"><span className="glyph">✓</span><span>{notice}</span></div>}

          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? "Please wait…" : isSignup ? "Create account" : "Sign in"}
            <span className="arrow"><svg viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6" /></svg></span>
          </button>
        </form>

        <p className="auth-switch">
          {isSignup ? "Already have an account?" : "New to Xamio?"}{" "}
          <button
            type="button"
            className="link-back"
            onClick={() => {
              setMode(isSignup ? "signin" : "signup");
              setError(null);
              setNotice(null);
            }}
          >
            {isSignup ? "Sign in" : "Create one"}
          </button>
        </p>
      </div>
    </div>
  );
}
