import { supabase } from "./supabase";

/**
 * Append a product-engagement event to public.activity_events.
 *
 * RLS guarantees a user can only write rows for their own user_id, so we read
 * the current user and stamp it explicitly. Failures are swallowed: analytics
 * must never break the product flow.
 *
 * These rows are what power the retention views (distinct active days per
 * user) on top of the single last_sign_in_at that Supabase auth keeps.
 */
export async function logEvent(eventType, metadata = {}) {
  try {
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (!user) return;

    await supabase
      .from("activity_events")
      .insert({ user_id: user.id, event_type: eventType, metadata });
  } catch (err) {
    console.debug("logEvent failed (non-fatal):", err);
  }
}
