import type { HitlPendingPayload } from "../types/hitl";
import { request } from "../request";

export interface OctopThread {
  thread_id: string;
  title: string | null;
  channel_type: string;
  session_key: string;
  last_active: number;
  created_at: number;
  is_active?: boolean;
  has_messages?: boolean;
  pinned?: boolean;
  unread_count?: number;
  model_ref?: string | null;
  reasoning_mode?: "auto" | "enabled" | "disabled" | null;
  reasoning_effort?: string | null;
}

export interface OctopThreadHistory {
  thread_id: string;
  messages: Array<{
    role: string;
    content: unknown;
    id?: string;
    usage?: unknown;
    timestamp?: number;
  }>;
  pinned?: boolean;
  model_ref?: string | null;
  reasoning_mode?: "auto" | "enabled" | "disabled" | null;
  reasoning_effort?: string | null;
  has_more?: boolean;
  limit?: number;
  offset?: number;
  /** True while a turn is still streaming server-side for this thread. */
  turn_active?: boolean;
  /** Pending tool approval for this thread (survives page reload). */
  hitl_pending?: HitlPendingPayload | null;
}

export interface OctopThreadPatch {
  title?: string;
  pinned?: boolean;
  model_ref?: string | null;
  reasoning_mode?: "auto" | "enabled" | "disabled" | null;
  reasoning_effort?: string | null;
}

export type ContextUsageSegmentKey =
  | "system_prompt"
  | "tool_definitions"
  | "rules"
  | "skills"
  | "mcp"
  | "subagent_definitions"
  | "conversation";

export interface ContextUsageSegment {
  key: ContextUsageSegmentKey;
  tokens: number;
}

export interface ContextUsageBreakdown {
  max_tokens: number;
  used_tokens: number;
  segments: ContextUsageSegment[];
}

export const CHAT_HISTORY_PAGE_SIZE = 25;

export const octopThreadsApi = {
  list: (agentId: string, limit = 50) =>
    request<OctopThread[]>(
      `/agents/${encodeURIComponent(agentId)}/threads?limit=${limit}`,
    ),

  create: (agentId: string) =>
    request<{ thread_id: string; session_key: string }>(
      `/agents/${encodeURIComponent(agentId)}/threads`,
      { method: "POST" },
    ),

  history: (
    agentId: string,
    threadId: string,
    params: { limit?: number; offset?: number } = {},
  ) => {
    const limit = params.limit ?? CHAT_HISTORY_PAGE_SIZE;
    const offset = params.offset ?? 0;
    return request<OctopThreadHistory>(
      `/agents/${encodeURIComponent(agentId)}/threads/${encodeURIComponent(
        threadId,
      )}/history?limit=${limit}&offset=${offset}`,
    );
  },

  contextUsage: (
    agentId: string,
    threadId: string,
    params: {
      maxTokens?: number;
      inputTokens?: number;
      mcpServers?: string[];
      skills?: string[];
    } = {},
  ) => {
    const search = new URLSearchParams();
    if (params.maxTokens != null) {
      search.set("max_tokens", String(params.maxTokens));
    }
    if (params.inputTokens != null && params.inputTokens > 0) {
      search.set("input_tokens", String(params.inputTokens));
    }
    if (params.mcpServers != null && params.mcpServers.length > 0) {
      search.set("mcp_servers", params.mcpServers.join(","));
    }
    if (params.skills != null && params.skills.length > 0) {
      search.set("skills", params.skills.join(","));
    }
    const qs = search.toString();
    return request<ContextUsageBreakdown>(
      `/agents/${encodeURIComponent(agentId)}/threads/${encodeURIComponent(
        threadId,
      )}/context-usage${qs ? `?${qs}` : ""}`,
    );
  },

  rename: (agentId: string, threadId: string, title: string) =>
    octopThreadsApi.patch(agentId, threadId, { title }),

  patch: (agentId: string, threadId: string, body: OctopThreadPatch) =>
    request<{
      thread_id: string;
      title: string | null;
      pinned?: boolean;
      model_ref?: string | null;
      reasoning_mode?: "auto" | "enabled" | "disabled" | null;
      reasoning_effort?: string | null;
    }>(
      `/agents/${encodeURIComponent(agentId)}/threads/${encodeURIComponent(
        threadId,
      )}`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),

  delete: (agentId: string, threadId: string) =>
    request<void>(
      `/agents/${encodeURIComponent(agentId)}/threads/${encodeURIComponent(
        threadId,
      )}`,
      { method: "DELETE" },
    ),

  fork: (
    agentId: string,
    threadId: string,
    body: {
      message_id: string;
      content?: string;
      user_turns_from_end?: number;
    },
  ) =>
    request<{
      thread_id: string;
      session_key: string;
      source_thread_id: string;
      copied_messages: number;
      title: string | null;
      last_active: number;
      created_at: number;
    }>(
      `/agents/${encodeURIComponent(agentId)}/threads/${encodeURIComponent(
        threadId,
      )}/fork`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  markRead: (agentId: string, threadId: string) =>
    request<void>(
      `/agents/${encodeURIComponent(agentId)}/threads/${encodeURIComponent(
        threadId,
      )}/read`,
      { method: "POST" },
    ),

  rebind: (agentId: string, threadId: string) =>
    request<{ session_key: string; thread_id: string }>(
      `/agents/${encodeURIComponent(agentId)}/session`,
      { method: "PATCH", body: JSON.stringify({ thread_id: threadId }) },
    ),
};
