import { useCallback, useEffect, useState } from "react";
import { isWriteToolName } from "../constants";
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

/** A conservative file-name suffix used as a last-resort path fallback. */
const PATH_EXT_RE = /\.[A-Za-z0-9][A-Za-z0-9._+-]{0,11}$/;

function pickPathFromObject(parsed: Record<string, unknown>): string {
  for (const key of PATH_KEYS) {
    const value = parsed[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

/**
 * Parse a tool argument value that may be a JSON *string* or an already
 * decoded object, then read a path-like value out of it.
 */
function pathFromArgs(raw: unknown): string {
  if (raw === null || raw === undefined) return "";
  if (typeof raw === "object") {
    return pickPathFromObject(raw as Record<string, unknown>);
  }
  if (typeof raw === "string") {
    const s = raw.trim();
    if (!s) return "";
    try {
      const parsed = JSON.parse(s) as Record<string, unknown>;
      if (parsed && typeof parsed === "object") {
        return pickPathFromObject(parsed);
      }
    } catch {
      // Not JSON — fall through to text scanning below.
    }
    return pathFromText(s);
  }
  return "";
}

/**
 * Scan free text (tool ``output``, non-JSON arguments) for a path. Prefers
 * the on-disk workspace absolute path the harness reports, then any
 * file-name-ish token.
 */
function pathFromText(text: string): string {
  if (!text) return "";
  const absMatch = text.match(/\/\.octop\/agents\/[^\s"'<>]+/i);
  if (absMatch) return absMatch[0];
  const relMatch = text.match(/(?:^|\s)([^\s"'<>]+\.[A-Za-z0-9]{1,8})(?=\s|$)/);
  if (relMatch && PATH_EXT_RE.test(relMatch[1])) return relMatch[1];
  return "";
}

function extractFilePath(message: ChatMessage): string | null {
  const name = message.toolData?.name ?? "";
  if (!isWriteToolName(name)) return null;

  const candidates = [
    message.toolData?.arguments,
    message.toolData?.output,
    message.content,
  ].filter(
    (value): value is string =>
      typeof value === "string" && value.trim().length > 0,
  );
  for (const raw of candidates) {
    const found = pathFromArgs(raw);
    if (found) return found;
  }
  return null;
}

/**
 * Collect workspace file paths written by the active thread's write/edit tool
 * calls so the chat can open them in the docked file panel.
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

  return { filePaths };
}
