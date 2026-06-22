import { createContext, useContext, useEffect, useRef, useState } from "react";
import { supabase } from "../lib/supabase";
import { logEvent } from "../lib/analytics";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  // Avoid double-logging "app_open" when onAuthStateChange fires repeatedly
  // (token refreshes, tab focus) within the same browser session.
  const openLoggedFor = useRef(null);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });

    const { data: sub } = supabase.auth.onAuthStateChange((event, sess) => {
      setSession(sess);

      // Log a daily-active signal once per sign-in / restored session.
      if (
        sess?.user &&
        (event === "SIGNED_IN" || event === "INITIAL_SESSION") &&
        openLoggedFor.current !== sess.user.id
      ) {
        openLoggedFor.current = sess.user.id;
        logEvent("app_open");
      }
      if (event === "SIGNED_OUT") openLoggedFor.current = null;
    });

    return () => sub.subscription.unsubscribe();
  }, []);

  const value = {
    session,
    user: session?.user ?? null,
    loading,
    signOut: () => supabase.auth.signOut(),
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
