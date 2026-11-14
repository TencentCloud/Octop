/** Helpers to map Octop cron rows for dashboard display. */

import { formatServerDateTime } from "../../../utils/formatMessageTime";

/** Form value and API token for "follow the channel's latest conversation". */
export const LATEST_SESSION_TARGET = "latest";

/** Stored ``session_key`` prefix that pins a job to one historical thread. */
export const THREAD_TARGET_PREFIX = "thread:";

export function pinnedThreadId(sessionKey: string): string {
  if (!sessionKey.startsWith(THREAD_TARGET_PREFIX)) return "";
  return sessionKey.slice(THREAD_TARGET_PREFIX.length).trim();
}

export function channelFromSessionKey(sessionKey: string): string {
  if (pinnedThreadId(sessionKey)) return "";
  const parts = sessionKey.split(":");
  return parts.length >= 2 ? parts[1] : "dashboard";
}

export function formatCronTimestamp(
  ts: number | null | undefined,
  timeZone?: string,
): string {
  if (!ts) return "—";
  return formatServerDateTime(ts, timeZone);
}

export function extractPromptFromJob(job: {
  task_type?: string;
  text?: string;
  request?: { input?: unknown };
}): string {
  if (job.task_type === "text" && job.text) return job.text;
  const input = job.request?.input;
  if (Array.isArray(input) && input.length > 0) {
    const last = input[input.length - 1] as
      | { content?: Array<{ type: string; text: string }> }
      | undefined;
    const part = last?.content?.find?.((c) => c.type === "text");
    if (part?.text) return part.text;
  }
  if (typeof input === "string") return input;
  return "";
}

/** Short preview for tables and lists (full text via tooltip elsewhere). */
export function truncatePromptPreview(text: string, maxLen = 48): string {
  const trimmed = text.trim();
  if (trimmed.length <= maxLen) return trimmed;
  return `${trimmed.slice(0, maxLen)}…`;
}
