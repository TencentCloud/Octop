import { getAuthToken } from "../request";
import { resolveWsUrl } from "../../utils/desktopWsUrl";

export function buildDashboardChatWsUrl(agentId: string): string {
  const token = getAuthToken();
  const encoded = encodeURIComponent(agentId);
  const base = resolveWsUrl(`/api/agents/${encoded}/chat/ws`);
  const params = new URLSearchParams();
  if (token) params.set("token", token);
  return params.toString() ? `${base}?${params.toString()}` : base;
}
