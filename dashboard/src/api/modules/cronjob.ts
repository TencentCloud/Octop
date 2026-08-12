import { request } from "../request";
import type {
  OctopCronRow,
  OctopCronCreateBody,
  OctopCronPatchBody,
  OctopCronRunPage,
} from "../types";

export interface OctopCronSettings {
  timezone: string;
}

export const octopCronApi = {
  settings: () => request<OctopCronSettings>("/cron/settings"),

  list: (agentId: string) => request<OctopCronRow[]>(`/agents/${agentId}/cron`),

  create: (agentId: string, body: OctopCronCreateBody) =>
    request<OctopCronRow>(`/agents/${agentId}/cron`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  get: (agentId: string, cronId: string) =>
    request<OctopCronRow>(`/agents/${agentId}/cron/${cronId}`),

  patch: (agentId: string, cronId: string, body: OctopCronPatchBody) =>
    request<OctopCronRow>(`/agents/${agentId}/cron/${cronId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  delete: (agentId: string, cronId: string) =>
    request<void>(`/agents/${agentId}/cron/${cronId}`, { method: "DELETE" }),

  runNow: (agentId: string, cronId: string) =>
    request<void>(`/agents/${agentId}/cron/${cronId}/run-now`, {
      method: "POST",
    }),

  listRuns: (agentId: string, cronId: string, page: number, pageSize: number) =>
    request<OctopCronRunPage>(
      `/agents/${agentId}/cron/${cronId}/runs?page=${page}&page_size=${pageSize}`,
    ),
};
