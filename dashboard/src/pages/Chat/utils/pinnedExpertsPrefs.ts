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

export const EXPERT_SORT_STORAGE_KEY = "octop:expert-sort";

/** Chat-nav order under the pin group. */
export type ExpertSortMode = "recent" | "newest" | "oldest";

const EXPERT_SORT_MODES: readonly ExpertSortMode[] = [
  "recent",
  "newest",
  "oldest",
];

export function expertSortStorageKey(userId?: number | null): string {
  return userId == null || userId <= 0
    ? EXPERT_SORT_STORAGE_KEY
    : `${EXPERT_SORT_STORAGE_KEY}:${userId}`;
}

export function readExpertSortMode(userId?: number | null): ExpertSortMode {
  try {
    const raw = localStorage.getItem(expertSortStorageKey(userId));
    if (raw != null && (EXPERT_SORT_MODES as readonly string[]).includes(raw)) {
      return raw as ExpertSortMode;
    }
  } catch {
    // private mode
  }
  return "recent";
}

export function writeExpertSortMode(
  mode: ExpertSortMode,
  userId?: number | null,
): ExpertSortMode {
  const next = (EXPERT_SORT_MODES as readonly string[]).includes(mode)
    ? mode
    : "recent";
  try {
    localStorage.setItem(expertSortStorageKey(userId), next);
  } catch {
    // quota / private mode
  }
  return next;
}

type SortableExpert = {
  id: number;
  agent_id: string;
  /** Unix seconds of this viewer's latest turn. Missing or 0 means never chatted. */
  last_active?: number | null;
};

function chatActivity(agent: SortableExpert): number {
  const value = agent.last_active;
  return typeof value === "number" && value > 0 ? value : 0;
}

function compareCreated<T extends SortableExpert>(
  a: T,
  b: T,
  direction: "newest" | "oldest",
): number {
  return direction === "oldest" ? a.id - b.id : b.id - a.id;
}

/**
 * Pinned experts first (pin order), then the chosen order.
 * Recent chats float up; experts with no turns stay behind them, newest id first.
 */
export function sortExpertsByPin<T extends SortableExpert>(
  agents: readonly T[],
  pinnedIds: readonly string[],
  mode: ExpertSortMode = "recent",
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
    if (mode === "newest" || mode === "oldest") {
      return compareCreated(a, b, mode);
    }
    const aActive = chatActivity(a);
    const bActive = chatActivity(b);
    if (aActive > 0 !== bActive > 0) return aActive > 0 ? -1 : 1;
    if (aActive !== bActive) return bActive - aActive;
    return compareCreated(a, b, "newest");
  });
}
