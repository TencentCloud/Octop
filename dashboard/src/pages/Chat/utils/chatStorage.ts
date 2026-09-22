export const CONNECTORS_STORAGE_PREFIX = "octop:chat-connectors:";

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

/** An unsent selection in this tab; null is absent, [] is an explicit opt-out. */
export function loadKnowledgeBaseDraft(key: string): string[] | null {
  try {
    const raw = sessionStorage.getItem(`octop:chat-knowledge-bases:${key}`);
    if (raw == null) return null;
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) && parsed.every((id) => typeof id === "string")
      ? parsed
      : null;
  } catch {
    return null;
  }
}

export function saveKnowledgeBaseDraft(
  key: string,
  ids: string[] | null,
): void {
  try {
    const storageKey = `octop:chat-knowledge-bases:${key}`;
    if (ids === null) sessionStorage.removeItem(storageKey);
    else sessionStorage.setItem(storageKey, JSON.stringify(ids));
  } catch {
    // sessionStorage unavailable or quota exceeded.
  }
}

export const KNOWLEDGE_STORAGE_PREFIX = "octop:chat-knowledge:";

export function loadSavedKnowledgeBaseIds(agentId: string): string[] {
  return loadSavedStringList(`${KNOWLEDGE_STORAGE_PREFIX}${agentId}`);
}

/** True when the user has an explicit saved preference (including empty). */
export function hasSavedKnowledgeBaseIds(agentId: string): boolean {
  try {
    return (
      localStorage.getItem(`${KNOWLEDGE_STORAGE_PREFIX}${agentId}`) != null
    );
  } catch {
    return false;
  }
}

export function saveKnowledgeBaseIds(agentId: string, ids: string[]): void {
  try {
    localStorage.setItem(
      `${KNOWLEDGE_STORAGE_PREFIX}${agentId}`,
      JSON.stringify(ids),
    );
  } catch {
    /* ignore */
  }
}
