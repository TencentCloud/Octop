/** Helpers to map Octop cron rows for dashboard display. */

import { formatServerDateTime } from "../../../utils/formatMessageTime";

export function channelFromSessionKey(sessionKey: string): string {
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
