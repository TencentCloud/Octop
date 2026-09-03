export type DashboardPushEvent = {
  type: "dashboard_push";
  agent_id: string;
  thread_id: string;
  text: string;
  agent_name?: string;
};

export type HistoryReadyEvent = {
  type: "history_ready";
  agent_id: string;
  thread_id: string;
  channel_type: string;
};

export function parseHistoryReadyFrame(raw: unknown): HistoryReadyEvent | null {
  if (raw === null || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  if (obj.type !== "history_ready") return null;
  const agentId = typeof obj.agent_id === "string" ? obj.agent_id.trim() : "";
  const threadId =
    typeof obj.thread_id === "string" ? obj.thread_id.trim() : "";
  if (!agentId || !threadId) return null;
  const channelType =
    typeof obj.channel_type === "string" ? obj.channel_type.trim() : "";
  return {
    type: "history_ready",
    agent_id: agentId,
    thread_id: threadId,
    channel_type: channelType,
  };
}

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

export function truncatePushText(text: string, max = 240): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max)}…`;
}
