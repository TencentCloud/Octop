import { getAuthToken } from "../request";
import { getWsUrl } from "../config";

export function buildDashboardNotifyWsUrl(): string {
  const token = getAuthToken();
  const base = getWsUrl("/notifications/ws");
  if (!token) return base;
  const params = new URLSearchParams({ token });
  return `${base}?${params.toString()}`;
}
