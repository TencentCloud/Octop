import { useCurrentUser } from "./useCurrentUser";

/**
 * Fetch the current user's role-template id once on mount.
 * Returns null while the request is in-flight or on failure —
 * callers should treat null as "not admin" to avoid info leaks.
 */
export function useUserRole(): string | null {
  const user = useCurrentUser();
  return user?.role ?? null;
}
