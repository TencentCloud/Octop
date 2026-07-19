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

/**
 * Match known file tools, plus any tool whose name implies a write/edit.
 * The harness may report a localized name (e.g. "写入文件") or alias
 * ``write_file`` under a namespace, so accept both English and Chinese keywords.
 */
export function isWriteToolName(name: string | undefined): boolean {
  return (
    isFileToolName(name) ||
    /write|edit|create|save|overwrite|append|写入|编辑|写文件|改文件|创建文件|保存文件/i.test(
      name ?? "",
    )
  );
}
