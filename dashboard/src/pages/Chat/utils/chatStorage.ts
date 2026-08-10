export const CONNECTORS_STORAGE_PREFIX = "octop:chat-connectors:";
export const SKILLS_STORAGE_PREFIX = "octop:chat-skills:";

function loadSavedStringList(key: string): string[] {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed)
      ? parsed.filter((x) => typeof x === "string")
      : [];
  } catch {
    return [];
  }
}

export function loadSavedConnectors(agentId: string): string[] {
  return loadSavedStringList(`${CONNECTORS_STORAGE_PREFIX}${agentId}`);
}

/** True when the user has an explicit saved preference (including empty). */
export function hasSavedConnectors(agentId: string): boolean {
  try {
    return (
      localStorage.getItem(`${CONNECTORS_STORAGE_PREFIX}${agentId}`) != null
    );
  } catch {
    return false;
  }
}

export function loadSavedSkills(agentId: string): string[] {
  return loadSavedStringList(`${SKILLS_STORAGE_PREFIX}${agentId}`);
}

export function saveConnectors(agentId: string, names: string[]): void {
  try {
    localStorage.setItem(
      `${CONNECTORS_STORAGE_PREFIX}${agentId}`,
      JSON.stringify(names),
    );
  } catch {
    /* ignore */
  }
}

export function saveSkills(agentId: string, names: string[]): void {
  try {
    localStorage.setItem(
      `${SKILLS_STORAGE_PREFIX}${agentId}`,
      JSON.stringify(names),
    );
  } catch {
    /* ignore */
  }
}
