/** Harness browser tools that activate the in-chat browser workspace. */
export const BROWSER_TOOL_NAMES = ["browser_use", "browser_control"] as const;

/** Harness tools that write into the agent workspace and produce files. */
export const FILE_TOOL_NAMES = ["write_file", "edit_file"] as const;

export const EMPTY_CHAT_SESSION_KEY = "__empty__";
export const PENDING_THREAD_ID = "__pending__";

function toolNameBase(name: string): string {
  const trimmed = name.trim();
  const slash = trimmed.lastIndexOf("/");
  return slash >= 0 ? trimmed.slice(slash + 1) : trimmed;
}

export function isBrowserToolName(name: string | undefined): boolean {
  return (BROWSER_TOOL_NAMES as readonly string[]).includes(name ?? "");
}

/** Match ``write_file`` / ``edit_file`` (and ``ns/write_file``), not ``write_todos``. */
export function isFileToolName(name: string | undefined): boolean {
  const base = toolNameBase((name ?? "").trim());
  return (FILE_TOOL_NAMES as readonly string[]).includes(base);
}

/** Alias kept for call sites that mean "opens the chat file panel card". */
export function isWriteToolName(name: string | undefined): boolean {
  return isFileToolName(name);
}
