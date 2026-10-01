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
