/**
 * Single source of truth for the harness browser profile identifier.
 *
 * All conversations currently map to one shared "default" profile so the
 * headed chat browser stays consistent with headless/standalone usage (instead
 * of spawning a per-conversation ``thr_*`` profile). The chat status bubble
 * and the chat browser panel must both derive the profile from here rather
 * than hardcoding "default" on independent paths.
 */

export const DEFAULT_BROWSER_PROFILE = "default";

/**
 * Resolve the browser profile for a conversation.
 *
 * Currently always the shared default profile; the conversation id is accepted
 * (and ignored) so per-conversation profiles can be introduced later without
 * touching every caller.
 */
export function resolveBrowserProfile(): string {
  return DEFAULT_BROWSER_PROFILE;
}
