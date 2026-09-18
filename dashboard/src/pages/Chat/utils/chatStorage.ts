export const CONNECTORS_STORAGE_PREFIX = "octop:chat-connectors:";

/** When true, process summary (thinking/tools) auto-expands while the live turn streams. Default false (#718). */
export const PROCESS_SUMMARY_EXPAND_WHILE_STREAMING_KEY =
  "octop:chat:process-summary-expand-while-streaming";

const EXPAND_PROCESS_CHANGE_EVENT = "octop:process-summary-expand-change";

export function loadExpandProcessWhileStreaming(): boolean {
  try {
    return (
      localStorage.getItem(PROCESS_SUMMARY_EXPAND_WHILE_STREAMING_KEY) ===
      "true"
    );
  } catch {
    return false;
  }
}

export function saveExpandProcessWhileStreaming(value: boolean): void {
  try {
    localStorage.setItem(
      PROCESS_SUMMARY_EXPAND_WHILE_STREAMING_KEY,
      value ? "true" : "false",
    );
  } catch {
    /* ignore */
  }
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(EXPAND_PROCESS_CHANGE_EVENT));
  }
}

/** Subscribe to same-tab + cross-tab preference changes for useSyncExternalStore. */
export function subscribeExpandProcessWhileStreaming(
  onStoreChange: () => void,
): () => void {
  if (typeof window === "undefined") return () => undefined;
  window.addEventListener(EXPAND_PROCESS_CHANGE_EVENT, onStoreChange);
  window.addEventListener("storage", onStoreChange);
  return () => {
    window.removeEventListener(EXPAND_PROCESS_CHANGE_EVENT, onStoreChange);
    window.removeEventListener("storage", onStoreChange);
  };
}

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
