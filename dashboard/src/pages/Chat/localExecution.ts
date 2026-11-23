import { EMPTY_CHAT_SESSION_KEY, PENDING_THREAD_ID } from "./constants";

export type LocalExecutionChoice = {
  mode: "cloud" | "local";
  directory: string;
  /** Extra directories the user added, besides the default workspace. */
  workspaces: string[];
};

const CLOUD: LocalExecutionChoice = {
  mode: "cloud",
  directory: "",
  workspaces: [],
};

function agentKey(agentId: string): string {
  return `octop.bridge.exec.agent.${agentId}`;
}

function threadKey(agentId: string, threadId: string): string {
  return `octop.bridge.exec.thread.${agentId}.${threadId}`;
}

export function isDraftExecutionThread(
  threadId: string | null | undefined,
): boolean {
  return draftThread(threadId);
}

/** Last path segments, so a chip can show where the directory sits. */
export function pathTail(path: string, segments = 2): string {
  const parts = path
    .trim()
    .replace(/\\/g, "/")
    .replace(/\/+$/, "")
    .split("/")
    .filter(Boolean);
  if (parts.length === 0) return "";
  return parts.slice(-segments).join("/");
}

function draftThread(threadId: string | null | undefined): boolean {
  return (
    !threadId ||
    threadId === EMPTY_CHAT_SESSION_KEY ||
    threadId === PENDING_THREAD_ID
  );
}

function load(key: string): LocalExecutionChoice | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<LocalExecutionChoice>;
    const mode = parsed.mode === "local" ? "local" : "cloud";
    const directory =
      typeof parsed.directory === "string" ? parsed.directory : "";
    const workspaces = Array.isArray(parsed.workspaces)
      ? parsed.workspaces.filter(
          (item): item is string =>
            typeof item === "string" && item.trim() !== "",
        )
      : [];
    return { mode, directory, workspaces };
  } catch {
    return null;
  }
}

function save(key: string, choice: LocalExecutionChoice): void {
  localStorage.setItem(key, JSON.stringify(choice));
}

/** Choice for the composer. A saved thread does not inherit the new-chat default. */
export function readLocalExecution(
  agentId: string,
  threadId: string | null | undefined,
): LocalExecutionChoice {
  if (!agentId.startsWith("bridge:")) return CLOUD;
  if (!draftThread(threadId) && threadId) {
    return load(threadKey(agentId, threadId)) ?? CLOUD;
  }
  return load(agentKey(agentId)) ?? CLOUD;
}

export function writeLocalExecution(
  agentId: string,
  threadId: string | null | undefined,
  choice: LocalExecutionChoice,
): void {
  if (!agentId.startsWith("bridge:")) return;
  if (!draftThread(threadId)) return;
  save(agentKey(agentId), choice);
}

/** Copy the new-chat choice onto a thread id once the server has assigned one. */
export function pinLocalExecution(agentId: string, threadId: string): void {
  if (!agentId.startsWith("bridge:") || draftThread(threadId)) return;
  if (load(threadKey(agentId, threadId))) return;
  save(threadKey(agentId, threadId), readLocalExecution(agentId, null));
}

export function localDirectoryMissing(
  agentId: string,
  threadId: string | null | undefined,
): boolean {
  const choice = readLocalExecution(agentId, threadId);
  return choice.mode === "local" && !choice.directory.trim();
}

/** Directory to send with this turn, or null when the expert should use its own workspace. */
export function localDirectoryForTurn(
  agentId: string,
  threadId: string | null | undefined,
): string | null {
  if (!agentId.startsWith("bridge:") || draftThread(threadId) || !threadId)
    return null;
  const choice = load(threadKey(agentId, threadId));
  if (!choice || choice.mode !== "local") return null;
  const directory = choice.directory.trim();
  return directory || null;
}
