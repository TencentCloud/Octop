export type DashboardPushEvent = {
  type: "dashboard_push";
  agent_id: string;
  thread_id: string;
  text: string;
  agent_name?: string;
};

export function parseDashboardPushFrame(
  raw: unknown,
): DashboardPushEvent | null {
  if (raw === null || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  if (obj.type !== "dashboard_push") return null;
  const agentId = typeof obj.agent_id === "string" ? obj.agent_id.trim() : "";
  const threadId =
    typeof obj.thread_id === "string" ? obj.thread_id.trim() : "";
  const text = typeof obj.text === "string" ? obj.text : "";
  if (!agentId || !threadId || !text.trim()) return null;
  const name = typeof obj.agent_name === "string" ? obj.agent_name.trim() : "";
  return {
    type: "dashboard_push",
    agent_id: agentId,
    thread_id: threadId,
    text,
    ...(name ? { agent_name: name } : {}),
  };
}

export type ThreadActivityEvent = {
  type: "thread_activity";
  agent_id: string;
  thread_id: string;
  reason: string;
};

/** Parse a proactive (cron) thread create/reuse notice from the notify socket. */
export function parseThreadActivityFrame(
  raw: unknown,
): ThreadActivityEvent | null {
  if (raw === null || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  if (obj.type !== "thread_activity") return null;
  const agentId = typeof obj.agent_id === "string" ? obj.agent_id.trim() : "";
  const threadId =
    typeof obj.thread_id === "string" ? obj.thread_id.trim() : "";
  if (!agentId || !threadId) return null;
  const reason = typeof obj.reason === "string" ? obj.reason.trim() : "";
  return {
    type: "thread_activity",
    agent_id: agentId,
    thread_id: threadId,
    reason,
  };
}

export function truncatePushText(text: string, max = 240): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max)}…`;
}
