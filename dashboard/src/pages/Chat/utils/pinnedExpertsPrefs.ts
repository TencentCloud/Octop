/** localStorage preference: experts pinned to the top of the chat nav. */

export const PINNED_EXPERTS_STORAGE_KEY = "octop:pinned-experts";

export function pinnedExpertsStorageKey(userId?: number | null): string {
  return userId == null || userId <= 0
    ? PINNED_EXPERTS_STORAGE_KEY
    : `${PINNED_EXPERTS_STORAGE_KEY}:${userId}`;
}

function parseIdList(raw: string | null): string[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    const ids: string[] = [];
    for (const item of parsed) {
      if (typeof item === "string" && item.length > 0 && !ids.includes(item)) {
        ids.push(item);
      }
    }
    return ids;
  } catch {
    return [];
  }
}

/** Pinned expert ids, most recently pinned first. */
export function readPinnedExpertIds(userId?: number | null): string[] {
  try {
    return parseIdList(localStorage.getItem(pinnedExpertsStorageKey(userId)));
  } catch {
    return [];
  }
}

export function writePinnedExpertIds(
  ids: Iterable<string>,
  userId?: number | null,
): void {
  try {
    const unique: string[] = [];
    for (const id of ids) {
      if (id.length > 0 && !unique.includes(id)) unique.push(id);
    }
    const key = pinnedExpertsStorageKey(userId);
    if (unique.length === 0) {
      localStorage.removeItem(key);
    } else {
      localStorage.setItem(key, JSON.stringify(unique));
    }
  } catch {
    // quota / private mode
  }
}

/** Pin moves the expert to the front; pinning again unpins it. */
export function togglePinnedExpertId(
  agentId: string,
  userId?: number | null,
): string[] {
  const current = readPinnedExpertIds(userId);
  if (!agentId) return current;
  const next = current.includes(agentId)
    ? current.filter((id) => id !== agentId)
    : [agentId, ...current];
  writePinnedExpertIds(next, userId);
  return next;
}

type SortableExpert = { id: number; agent_id: string };

/** Pinned experts first (pin order), then newest id. */
export function sortExpertsByPin<T extends SortableExpert>(
  agents: readonly T[],
  pinnedIds: readonly string[],
): T[] {
  const rank = new Map<string, number>();
  pinnedIds.forEach((id, index) => {
    if (!rank.has(id)) rank.set(id, index);
  });
  return [...agents].sort((a, b) => {
    const aRank = rank.get(a.agent_id);
    const bRank = rank.get(b.agent_id);
    const aPinned = aRank != null;
    const bPinned = bRank != null;
    if (aPinned !== bPinned) return aPinned ? -1 : 1;
    if (aPinned && bPinned && aRank !== bRank) return aRank - bRank;
    return b.id - a.id;
  });
}
