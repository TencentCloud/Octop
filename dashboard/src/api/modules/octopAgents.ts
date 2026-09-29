import type { OctopAgent } from "../../context/AgentContext";
import { request, requestUpload } from "../request";

/** Kanban bucket an agent lands in on the overview board (priority order). */
export type KanbanStatus = "needs_you" | "working" | "done" | "idle";

/** Live activity behind the card (before unseen→idle settling). */
export type KanbanActivityState =
  | "working"
  | "blocked"
  | "waiting"
  | "done"
  | "idle";

/** Live kanban extras merged onto each agent row by ``GET /api/agents/overview``. */
export interface KanbanOverviewAgent extends OctopAgent {
  kanban_status: KanbanStatus;
  /** Mutually exclusive live state: blocked|waiting|working|done|idle. */
  activity_state: KanbanActivityState;
  /** Current activity has not been acknowledged (mark-read / open chat). */
  unseen: boolean;
  /** True while a turn is in flight for this agent. */
  busy: boolean;
  /** Pending HITL approvals/questions for the current viewer, if any. */
  hitl_pending: {
    count: number;
    thread_id: string;
    created_at: number;
  } | null;
  /** At least one thread is waiting for plan approval. */
  pending_plan: boolean;
  /**
   * Thread the card should deep-link to: the one needing the user (pending
   * approval, then pending plan), else the newest thread.
   */
  attention_thread_id: string | null;
  /** Newest thread of this agent for the current viewer. */
  latest_thread: {
    thread_id: string;
    title: string | null;
    last_active: number;
    message: { role: "user" | "assistant"; text: string } | null;
  } | null;
}

export const octopAgentsApi = {
  overview: () => request<KanbanOverviewAgent[]>("/agents/overview"),

  markRead: (agentId: string) =>
    request<void>(`/agents/${encodeURIComponent(agentId)}/read`, {
      method: "POST",
    }),

  uploadAvatar: (agentId: string, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return requestUpload<{ icon_url: string }>(
      `/agents/${encodeURIComponent(agentId)}/avatar`,
      body,
    );
  },

  deleteAvatar: (agentId: string) =>
    request<void>(`/agents/${encodeURIComponent(agentId)}/avatar`, {
      method: "DELETE",
    }),
};
