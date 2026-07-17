import { useCallback, useEffect, useState } from "react";
import { isFileToolName } from "../constants";
import type { ChatMessage } from "./useChat";

/**
 * Candidate JSON keys that may carry the written file's workspace path.
 * Harness tool schemas differ across versions, so we accept several names.
 */
const PATH_KEYS = [
  "path",
  "file_path",
  "filepath",
  "filename",
  "dest",
  "target_path",
  "output_path",
] as const;

function pickPath(parsed: Record<string, unknown>): string {
  for (const key of PATH_KEYS) {
    const value = parsed[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function extractFilePath(message: ChatMessage): string | null {
  const name = message.toolData?.name ?? "";
  // Match known file tools, plus any tool whose name implies a write/edit
  // (the harness occasionally aliases ``write_file`` under a different name).
  const isWriteTool =
    isFileToolName(name) ||
    /write|edit|create|save|overwrite|append/i.test(name);
  if (!isWriteTool) return null;

  const candidates = [message.toolData?.arguments, message.toolData?.output].filter(
    (value): value is string =>
      typeof value === "string" && value.trim().length > 0,
  );
  for (const raw of candidates) {
    try {
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      const path = pickPath(parsed);
      if (path) return path;
    } catch {
      // Arguments stream incrementally; ignore until the JSON is complete.
    }
  }
  return null;
}

/**
 * Collect the workspace file paths written by the active thread's
 * ``write_file`` / ``edit_file`` tool calls, plus a boolean flag.
 *
 * Reusing ``FileViewer`` directly (inside a dialog), the chat surfaces the
 * generated documents for preview / edit / download — mirroring
 * ``useBrowserToolDetection`` but tracking concrete file paths so the popup
 * can open the document rather than the full workspace tree.
 */
export function useChatFileDetection(
  _activeThreadId: string | null,
  messages: ChatMessage[],
) {
  const [filePaths, setFilePaths] = useState<string[]>([]);

  const collect = useCallback((msgs: ChatMessage[]): string[] => {
    const paths: string[] = [];
    const seen = new Set<string>();
    for (const m of msgs) {
      const path = extractFilePath(m);
      if (path && !seen.has(path)) {
        seen.add(path);
        paths.push(path);
      }
    }
    return paths;
  }, []);

  useEffect(() => {
    setFilePaths(collect(messages));
  }, [messages, collect]);

  return { filePaths, hasFileTool: filePaths.length > 0 };
}
