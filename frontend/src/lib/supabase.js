import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

export const isSupabaseConfigured = Boolean(url && key);

if (!isSupabaseConfigured) {
  console.error(
    "Missing VITE_SUPABASE_URL or VITE_SUPABASE_PUBLISHABLE_KEY. " +
      "Set them in your host's environment variables (e.g. Vercel → Settings → " +
      "Environment Variables) and redeploy. Locally, copy frontend/.env.example " +
      "to frontend/.env. Auth is disabled until they're set."
  );
}

// Fall back to harmless placeholders when unconfigured so createClient does not
// throw at module load — that would blank the entire app, landing page included.
// Auth calls will simply fail until real env vars are provided.
export const supabase = createClient(
  url || "https://placeholder.supabase.co",
  key || "placeholder-anon-key",
  {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true, // needed for the OAuth redirect callback
  },
});
