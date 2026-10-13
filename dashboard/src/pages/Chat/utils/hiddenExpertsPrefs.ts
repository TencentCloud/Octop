/** localStorage preference: shared experts the current user has hidden from chat lists. */

export const HIDDEN_SHARED_EXPERTS_STORAGE_KEY = "octop:hidden-shared-experts";

export function hiddenExpertsStorageKey(userId?: number | null): string {
  return userId == null || userId <= 0
    ? HIDDEN_SHARED_EXPERTS_STORAGE_KEY
    : `${HIDDEN_SHARED_EXPERTS_STORAGE_KEY}:${userId}`;
}

function parseIdList(raw: string | null): string[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (x): x is string => typeof x === "string" && x.length > 0,
    );
  } catch {
    return [];
  }
}

export function readHiddenExpertIds(userId?: number | null): Set<string> {
  try {
    return new Set(
      parseIdList(localStorage.getItem(hiddenExpertsStorageKey(userId))),
    );
  } catch {
    return new Set();
  }
}

export function writeHiddenExpertIds(
  ids: Iterable<string>,
  userId?: number | null,
): void {
  try {
    const unique = [...new Set([...ids].filter((id) => id.length > 0))];
    const key = hiddenExpertsStorageKey(userId);
    if (unique.length === 0) {
      localStorage.removeItem(key);
    } else {
      localStorage.setItem(key, JSON.stringify(unique));
    }
  } catch {
    // quota / private mode
  }
}

export function hideExpertId(
  agentId: string,
  userId?: number | null,
): Set<string> {
  const next = readHiddenExpertIds(userId);
  if (!agentId) return next;
  next.add(agentId);
  writeHiddenExpertIds(next, userId);
  return next;
}

export function unhideExpertId(
  agentId: string,
  userId?: number | null,
): Set<string> {
  const next = readHiddenExpertIds(userId);
  next.delete(agentId);
  writeHiddenExpertIds(next, userId);
  return next;
}
