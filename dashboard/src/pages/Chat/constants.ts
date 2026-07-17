/** Harness browser tools that activate the in-chat browser workspace. */
export const BROWSER_TOOL_NAMES = ["browser_use", "browser_control"] as const;

/** Harness tools that write into the agent workspace and produce files. */
export const FILE_TOOL_NAMES = ["write_file", "edit_file"] as const;

export const EMPTY_CHAT_SESSION_KEY = "__empty__";
export const PENDING_THREAD_ID = "__pending__";

export function isBrowserToolName(name: string | undefined): boolean {
  return (BROWSER_TOOL_NAMES as readonly string[]).includes(name ?? "");
}

export function isFileToolName(name: string | undefined): boolean {
  return (FILE_TOOL_NAMES as readonly string[]).includes(name ?? "");
}
