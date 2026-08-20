import { useCallback, useEffect, useState } from "react";
import {
  collectToolMediaFromToolData,
  workspacePathFromAccessUrl,
} from "../../../utils/toolMediaBlocks";
import { isWriteToolName } from "../constants";
import {
  canonicalizeDockFilePath,
  dedupeDockFilePaths,
  normalizeDockFilePath,
} from "../utils/dockFilePath";
import type { ChatMessage } from "./useChat";

/**
 * Candidate JSON keys that may carry a workspace file path.
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
  "source",
] as const;

/** A conservative file-name suffix used as a last-resort path fallback. */
const PATH_EXT_RE = /\.[A-Za-z][A-Za-z0-9._+-]{0,11}$/;

function pickPathFromObject(parsed: Record<string, unknown>): string {
  for (const key of PATH_KEYS) {
    const value = parsed[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

/** Reject version tokens (``1.0.2``) and built-in skill docs from the list. */
function isDockListablePath(path: string): boolean {
  const posix = path.replace(/\\/g, "/");
  if (!posix) return false;
  if (/(^|\/)_builtin_skills(\/|$)/i.test(posix)) return false;
  const base = posix.split("/").filter(Boolean).pop() || posix;
  if (/^[\d.]+$/.test(base)) return false;
  if (!PATH_EXT_RE.test(base)) return false;
  return true;
}

/**
 * Read a path-like key from tool arguments (object or JSON string).
 * Does not scan free text — that is a last-resort fallback.
 */
function pathFromStructuredArgs(raw: unknown): string {
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
      return "";
    }
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
  // Prefer full absolute path ending at ``/.octop/agents/…`` (keep ``/home/…``).
  const absMatch = text.match(/(?:\/[\w.-]+)*\/\.octop\/agents\/[^\s"'<>]+/i);
  if (absMatch) return absMatch[0];
  const outbound = text.match(
    /(?:^|[\s"'`])((?:outbound|inbound)\/[^\s"'<>]+)/i,
  );
  if (outbound) return outbound[1];
  const relMatch = text.match(
    /(?:^|\s)((?:generated|outbound|inbound)\/[^\s"'<>]+)/i,
  );
  if (relMatch) return relMatch[1];
  const fileMatch = text.match(
    /(?:^|\s)([^\s"'<>]+\/[^\s"'<>]+\.[A-Za-z][A-Za-z0-9._+-]{0,11})(?=\s|$)/,
  );
  if (fileMatch && isDockListablePath(fileMatch[1])) return fileMatch[1];
  return "";
}

function extractWriteToolPath(message: ChatMessage): string | null {
  const name = message.toolData?.name ?? "";
  if (!isWriteToolName(name)) return null;

  const fromArgs = pathFromStructuredArgs(message.toolData?.arguments);
  if (fromArgs) return fromArgs;

  const fallbacks = [
    message.toolData?.arguments,
    message.toolData?.output,
    message.content,
  ].filter(
    (value): value is string =>
      typeof value === "string" && value.trim().length > 0,
  );
  for (const raw of fallbacks) {
    const found = pathFromText(raw);
    if (found) return found;
  }
  return null;
}

function addPath(
  paths: string[],
  path: string | null,
  agentId?: string | null,
) {
  const key = path ? canonicalizeDockFilePath(path, agentId) : "";
  if (!key || !isDockListablePath(key)) return;
  // Keep the original (richer) path for folder display; dedupe collapses later.
  paths.push(normalizeDockFilePath(path!) || key);
}

/**
 * Collect workspace file paths from the active thread so the docked file
 * panel can switch among written / previewable / attached files together.
 */
export function useChatFileDetection(
  _activeThreadId: string | null,
  messages: ChatMessage[],
  agentId?: string | null,
) {
  const [filePaths, setFilePaths] = useState<string[]>([]);
  const collect = useCallback(
    (msgs: ChatMessage[]): string[] => collectChatFilePaths(msgs, agentId),
    [agentId],
  );

  useEffect(() => {
    setFilePaths(collect(messages));
  }, [messages, collect]);

  return { filePaths };
}

/** Collect unique workspace file paths from a slice of chat messages. */
export function collectChatFilePaths(
  messages: ChatMessage[],
  agentId?: string | null,
): string[] {
  const paths: string[] = [];
  for (const m of messages) {
    addPath(paths, extractWriteToolPath(m), agentId);
    for (const att of m.attachments ?? []) {
      if (att.workspacePath) {
        addPath(paths, att.workspacePath, agentId);
      } else if (att.url) {
        addPath(paths, workspacePathFromAccessUrl(att.url) ?? null, agentId);
      }
    }
    const media = collectToolMediaFromToolData(
      m.toolData,
      agentId,
      m.attachments,
    );
    for (const file of media.files) {
      addPath(paths, workspacePathFromAccessUrl(file.url) ?? null, agentId);
    }
    for (const img of media.images) {
      addPath(paths, workspacePathFromAccessUrl(img.url) ?? null, agentId);
    }
    for (const video of media.videos) {
      addPath(paths, workspacePathFromAccessUrl(video.url) ?? null, agentId);
    }
  }
  return dedupeDockFilePaths(paths, agentId);
}
