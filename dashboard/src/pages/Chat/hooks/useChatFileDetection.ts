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
 * Path of the most recent workspace write/edit tool call in this turn, so the
 * "edit file" card can jump straight to the generated file (falls back to the
 * file list when no listable path is found).
 */
export function lastWriteToolPath(
  messages: ChatMessage[],
  agentId?: string | null,
): string | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const raw = extractWriteToolPath(messages[i]);
    if (!raw) continue;
    const key = canonicalizeDockFilePath(raw, agentId);
    if (key && isDockListablePath(key)) return raw;
  }
  return null;
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
    (msgs: ChatMessage[]): string[] => {
      const paths: string[] = [];

      for (const m of msgs) {
        // Write / edit / send tools only — avoid listing every read_file skill doc.
        addPath(paths, extractWriteToolPath(m), agentId);

        for (const att of m.attachments ?? []) {
          if (att.workspacePath) {
            addPath(paths, att.workspacePath, agentId);
          } else if (att.url) {
            addPath(
              paths,
              workspacePathFromAccessUrl(att.url) ?? null,
              agentId,
            );
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
          addPath(
            paths,
            workspacePathFromAccessUrl(video.url) ?? null,
            agentId,
          );
        }
      }

      return dedupeDockFilePaths(paths, agentId);
    },
    [agentId],
  );

  useEffect(() => {
    setFilePaths(collect(messages));
  }, [messages, collect]);

  return { filePaths };
}
