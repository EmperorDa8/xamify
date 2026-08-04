import axios from "axios";
import { supabase } from "./supabase";

/**
 * Attach the Supabase access token to every API request so the backend can
 * verify the caller is a signed-in user (see backend/services/auth.py).
 *
 * Registered as a global interceptor on the default axios instance, so it
 * covers every component that imports axios (App, CalendarSync, …) without
 * each call having to wire the header itself. Import this module once at
 * startup for the side effect.
 */
axios.interceptors.request.use(async (config) => {
  try {
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (session?.access_token) {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${session.access_token}`;
    }
  } catch {
    // No session / Supabase not configured — send the request unauthenticated
    // and let the backend decide (it 401s only when auth is enforced).
  }
  return config;
});

export default axios;
