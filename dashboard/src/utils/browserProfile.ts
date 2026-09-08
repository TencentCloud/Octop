/**
 * Harness browser profile for one Octop user.
 *
 * Shared across that user's agents and conversations. The backend also
 * derives this from the authenticated user and ignores client-supplied names.
 * A leftover on-disk ``default`` profile is not reused.
 */
export function resolveBrowserProfile(userId?: number | null): string | null {
  return userId == null || userId <= 0 ? null : `user-${userId}`;
}
