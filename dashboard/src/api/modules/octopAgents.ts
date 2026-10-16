import { request, requestUpload } from "../request";

export const octopAgentsApi = {
  markRead: (agentId: string) =>
    request<void>(`/agents/${encodeURIComponent(agentId)}/read`, {
      method: "POST",
    }),

  /** Per-user pin toggle (schema v21, cross-device). */
  pin: (agentId: string, pinned: boolean) =>
    request<void>(`/agents/${encodeURIComponent(agentId)}/pin`, {
      method: "POST",
      body: JSON.stringify({ pinned }),
    }),

  /** Persist the full manual sequence (schema v21, cross-device). */
  reorder: (order: string[]) =>
    request<void>("/agents/order", {
      method: "PUT",
      body: JSON.stringify({ order }),
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
