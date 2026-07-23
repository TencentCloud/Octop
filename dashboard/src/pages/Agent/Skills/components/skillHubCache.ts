import type { SkillHubSkill } from "./SkillHubDetailDrawer";

const RANKINGS_CACHE_KEY = "octop:skillhub-rankings:v1";
const RANKINGS_CACHE_TTL = 24 * 60 * 60 * 1000;

interface RankingsCache {
  ts: number;
  data: Record<string, SkillHubSkill[]>;
}

export function loadRankingsCache(): Record<string, SkillHubSkill[]> | null {
  try {
    const raw = localStorage.getItem(RANKINGS_CACHE_KEY);
    if (!raw) return null;
    const parsed: RankingsCache = JSON.parse(raw);
    if (Date.now() - parsed.ts > RANKINGS_CACHE_TTL) {
      localStorage.removeItem(RANKINGS_CACHE_KEY);
      return null;
    }
    return parsed.data;
  } catch {
    return null;
  }
}

export function saveRankingsCache(data: Record<string, SkillHubSkill[]>): void {
  try {
    const payload: RankingsCache = { ts: Date.now(), data };
    localStorage.setItem(RANKINGS_CACHE_KEY, JSON.stringify(payload));
  } catch {
    // localStorage may be full or unavailable; ignore silently.
  }
}
