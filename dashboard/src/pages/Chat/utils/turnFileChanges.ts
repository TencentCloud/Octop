/**
 * Line stats for one assistant turn, taken from ``write_file`` / ``edit_file``
 * arguments. No workspace read: a write counts the new body, an edit counts
 * the hunk (``old_string`` → ``new_string``).
 */

import { isFileToolName } from "../constants";
import type { ChatMessage } from "../hooks/sseHelpers";
import {
  canonicalizeDockFilePath,
  isHostAbsolutePath,
  normalizeDockFilePath,
} from "./dockFilePath";

const PATH_KEYS = [
  "file_path",
  "path",
  "filepath",
  "filename",
  "target_path",
  "output_path",
] as const;

/** LCS above this many lines falls back to a multiset so a huge hunk stays cheap. */
const LINE_DIFF_CAP = 400;

export interface TurnFileChange {
  /** Path passed to the file tab. Host-absolute tool paths stay absolute. */
  openPath: string;
  /** Workspace-relative path when we can tell; otherwise ``openPath``. */
  displayPath: string;
  agentId: string | null;
  additions: number;
  deletions: number;
  /** True once a patch body contributed to the totals. */
  measured: boolean;
  /** The latest write/edit of this file is still streaming. */
  pending: boolean;
}

export interface TurnFileChangeSummary {
  files: TurnFileChange[];
  additions: number;
  deletions: number;
  /** At least one file has a non-zero line count. */
  measured: boolean;
  /** File the agent is writing or editing right now. */
  activePath: string | null;
}

interface Region {
  before: string;
  after: string;
}

interface FileAcc {
  openPath: string;
  displayPath: string;
  agentId: string | null;
  additions: number;
  deletions: number;
  measured: boolean;
  pending: boolean;
  regions: Region[];
  wrote: boolean;
  extraAdditions: number;
  extraDeletions: number;
}

/** Chip label: the file name, with its parent directory when there is one. */
export function fileChangeChipLabel(displayPath: string): string {
  const parts = displayPath.replace(/\\/g, "/").split("/").filter(Boolean);
  if (parts.length <= 1) return parts[0] || displayPath;
  return `${parts[parts.length - 2]}/${parts[parts.length - 1]}`;
}

function applyTimes(
  text: string,
  oldStr: string,
  newStr: string,
  times: number,
): { text: string; applied: number } {
  if (!oldStr || times <= 0) return { text, applied: 0 };
  let out = text;
  let applied = 0;
  while (applied < times) {
    const idx = out.indexOf(oldStr);
    if (idx < 0) break;
    const next = out.slice(0, idx) + newStr + out.slice(idx + oldStr.length);
    if (next === out) break;
    out = next;
    applied += 1;
    if (newStr.includes(oldStr)) break;
  }
  return { text: out, applied };
}

function finalizeFile(acc: FileAcc) {
  if (acc.wrote && acc.regions[0]) {
    const finalText = acc.regions[0].after;
    const delta = lineChangeStats("", finalText);
    acc.additions = delta.additions + acc.extraAdditions;
    acc.deletions = delta.deletions + acc.extraDeletions;
  } else {
    let additions = acc.extraAdditions;
    let deletions = acc.extraDeletions;
    for (const region of acc.regions) {
      const delta = lineChangeStats(region.before, region.after);
      additions += delta.additions;
      deletions += delta.deletions;
    }
    acc.additions = additions;
    acc.deletions = deletions;
  }
  acc.measured = acc.additions + acc.deletions > 0;
}

function toolBase(name: string | undefined): string {
  const trimmed = (name ?? "").trim();
  const slash = trimmed.lastIndexOf("/");
  return (slash >= 0 ? trimmed.slice(slash + 1) : trimmed).toLowerCase();
}

function toLines(text: string): string[] {
  if (text === "") return [];
  const parts = text.split(/\r?\n/);
  if (parts[parts.length - 1] === "") parts.pop();
  return parts;
}

function lcsLength(a: string[], b: string[]): number {
  const width = b.length;
  let prev = new Array<number>(width + 1).fill(0);
  let curr = new Array<number>(width + 1).fill(0);
  for (let i = 0; i < a.length; i++) {
    const line = a[i];
    for (let j = 1; j <= width; j++) {
      curr[j] =
        line === b[j - 1] ? prev[j - 1] + 1 : Math.max(prev[j], curr[j - 1]);
    }
    const swap = prev;
    prev = curr;
    curr = swap;
    curr.fill(0);
  }
  return prev[width];
}

function multisetStats(
  before: string[],
  after: string[],
): { additions: number; deletions: number } {
  const counts = new Map<string, number>();
  for (const line of before) counts.set(line, (counts.get(line) ?? 0) + 1);
  let additions = 0;
  for (const line of after) {
    const n = counts.get(line) ?? 0;
    if (n > 0) counts.set(line, n - 1);
    else additions += 1;
  }
  let deletions = 0;
  for (const n of counts.values()) deletions += n;
  return { additions, deletions };
}

/** Additions and deletions between two texts, ignoring a shared trailing newline. */
export function lineChangeStats(
  before: string,
  after: string,
): { additions: number; deletions: number } {
  const a = toLines(before);
  const b = toLines(after);
  if (a.length === 0) return { additions: b.length, deletions: 0 };
  if (b.length === 0) return { additions: 0, deletions: a.length };
  if (a.length > LINE_DIFF_CAP || b.length > LINE_DIFF_CAP) {
    return multisetStats(a, b);
  }
  const same = lcsLength(a, b);
  return { additions: b.length - same, deletions: a.length - same };
}

function parseArgs(raw: unknown): Record<string, unknown> | null {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    return raw as Record<string, unknown>;
  }
  if (typeof raw !== "string") return null;
  const text = raw.trim();
  if (!text.startsWith("{")) return null;
  try {
    const parsed = JSON.parse(text) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    return null;
  }
  return null;
}

function pathFromLoose(raw: string): string {
  const match = raw.match(
    /"(?:file_path|path|filepath)"\s*:\s*"((?:\\.|[^"\\])*)"/,
  );
  if (!match) return "";
  try {
    const parsed = JSON.parse(`"${match[1]}"`) as unknown;
    return typeof parsed === "string" ? parsed.trim() : "";
  } catch {
    return "";
  }
}

function pathFromTool(raw: unknown): string {
  const args = parseArgs(raw);
  if (args) {
    for (const key of PATH_KEYS) {
      const value = args[key];
      if (typeof value === "string" && value.trim()) return value.trim();
    }
  }
  if (typeof raw === "string") return pathFromLoose(raw);
  return "";
}

function toolFailed(message: ChatMessage): boolean {
  if (message.status === "streaming") return false;
  if (message.status === "error") return true;
  if (message.toolData?.errorCode) return true;
  return /^error\b/i.test((message.toolData?.output ?? "").trim());
}

function replacedInstances(output: string | undefined): number | null {
  if (!output) return null;
  const match = output.match(/Successfully replaced (\d+) instance/);
  if (!match) return null;
  const count = Number(match[1]);
  return Number.isFinite(count) ? count : null;
}

function preferOpenPath(current: string, next: string): string {
  const nextAbs = isHostAbsolutePath(normalizeDockFilePath(next));
  const currentAbs = isHostAbsolutePath(normalizeDockFilePath(current));
  if (nextAbs && !currentAbs) return next;
  return current;
}

function ownerId(message: ChatMessage, agentId?: string | null): string | null {
  return message.speakerAgentId?.trim() || agentId?.trim() || null;
}

function fileKey(path: string, agentId: string | null): string {
  const canonical = canonicalizeDockFilePath(path, agentId);
  return `${agentId ?? ""}\0${
    canonical || normalizeDockFilePath(path) || path
  }`;
}

export function summarizeTurnFileChanges(
  messages: readonly ChatMessage[],
  agentId?: string | null,
): TurnFileChangeSummary {
  const order: string[] = [];
  const files = new Map<string, FileAcc>();

  const ensure = (path: string, owner: string | null): FileAcc => {
    const key = fileKey(path, owner);
    const existing = files.get(key);
    if (existing) {
      existing.openPath = preferOpenPath(existing.openPath, path);
      const canonical = canonicalizeDockFilePath(existing.openPath, owner);
      existing.displayPath = canonical || existing.openPath;
      return existing;
    }
    const canonical = canonicalizeDockFilePath(path, owner);
    const created: FileAcc = {
      openPath: path,
      displayPath: canonical || path,
      agentId: owner,
      additions: 0,
      deletions: 0,
      measured: false,
      pending: false,
      regions: [],
      wrote: false,
      extraAdditions: 0,
      extraDeletions: 0,
    };
    files.set(key, created);
    order.push(key);
    return created;
  };

  for (const message of messages) {
    const owner = ownerId(message, agentId);
    const base = toolBase(message.toolData?.name);
    const isWrite = base === "write_file";
    const isEdit = base === "edit_file";
    if ((isWrite || isEdit || isFileToolName(base)) && message.toolData) {
      const path = pathFromTool(message.toolData.arguments);
      const pending = message.status === "streaming";
      const failed = toolFailed(message);
      if (path && !failed) {
        const acc = ensure(path, owner);
        if (isWrite || isEdit) acc.pending = pending;
        const args = parseArgs(message.toolData.arguments);
        if (isWrite && typeof args?.content === "string") {
          acc.wrote = true;
          acc.regions = [{ before: "", after: args.content }];
          acc.extraAdditions = 0;
          acc.extraDeletions = 0;
        } else if (
          isEdit &&
          typeof args?.old_string === "string" &&
          typeof args?.new_string === "string"
        ) {
          const times = replacedInstances(message.toolData.output) ?? 1;
          if (times > 0) {
            const oldStr = args.old_string;
            const newStr = args.new_string;
            const region = acc.regions.find(
              (item) => oldStr && item.after.includes(oldStr),
            );
            const { text, applied } = applyTimes(
              region ? region.after : oldStr,
              oldStr,
              newStr,
              times,
            );
            if (region) {
              region.after = text;
            } else {
              acc.regions.push({ before: oldStr, after: text });
            }
            const missed = times - applied;
            if (missed > 0 && !acc.wrote) {
              const delta = lineChangeStats(oldStr, newStr);
              acc.extraAdditions += delta.additions * missed;
              acc.extraDeletions += delta.deletions * missed;
            }
          }
        }
      }
    }
    for (const edited of message.editedFiles ?? []) {
      const path = edited.trim();
      if (path) ensure(path, owner);
    }
  }

  const listed = order.map((key) => files.get(key)!);
  for (const file of listed) finalizeFile(file);
  let additions = 0;
  let deletions = 0;
  let activePath: string | null = null;
  for (const file of listed) {
    if (file.measured) {
      additions += file.additions;
      deletions += file.deletions;
    }
    if (file.pending) activePath = file.displayPath;
  }
  return {
    files: listed,
    additions,
    deletions,
    measured: additions + deletions > 0,
    activePath,
  };
}
