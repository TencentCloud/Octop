export const TAG_FILTER_CLICKS_PREFIX = "octop.tagFilterClicks.";
const MAX_TAG_FILTER_CLICKS = 50;

function storageKey(agentId: string): string {
  return `${TAG_FILTER_CLICKS_PREFIX}${agentId}`;
}

function normalizeClicks(value: unknown): Record<string, number> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};

  const clicks: Record<string, number> = {};
  for (const [tag, count] of Object.entries(value)) {
    if (
      tag.trim() &&
      typeof count === "number" &&
      Number.isFinite(count) &&
      count > 0
    ) {
      clicks[tag] = Math.floor(count);
    }
  }
  return clicks;
}

function trimClicks(clicks: Record<string, number>): Record<string, number> {
  return Object.fromEntries(
    Object.entries(clicks)
      .sort(([tagA, countA], [tagB, countB]) => {
        if (countB !== countA) return countB - countA;
        return tagA.localeCompare(tagB);
      })
      .slice(0, MAX_TAG_FILTER_CLICKS),
  );
}

export function readTagClicks(agentId: string): Record<string, number> {
  try {
    const raw = localStorage.getItem(storageKey(agentId));
    return raw ? normalizeClicks(JSON.parse(raw) as unknown) : {};
  } catch {
    return {};
  }
}

export function recordTagClick(agentId: string, tag: string): void {
  const normalizedTag = tag.trim();
  if (!normalizedTag) return;

  try {
    const clicks = readTagClicks(agentId);
    clicks[normalizedTag] = (clicks[normalizedTag] ?? 0) + 1;
    localStorage.setItem(
      storageKey(agentId),
      JSON.stringify(trimClicks(clicks)),
    );
  } catch {
    /* ignore */
  }
}
