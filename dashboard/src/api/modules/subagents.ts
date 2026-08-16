import { request } from "../request";
import type { LocalizedText } from "../../utils/localizedText";

export interface SubagentCatalogDivision {
  id: string;
  label: string;
  labels?: LocalizedText;
  icon: string | null;
  color: string | null;
  count: number;
}

export interface SubagentCatalogItem {
  slug: string;
  division: string;
  name: LocalizedText;
  description: LocalizedText;
  emoji?: string | null;
  color?: string | null;
  source_path: string;
  available_locales?: string[];
}

export interface SubagentCatalogDetail extends SubagentCatalogItem {
  content: LocalizedText;
}

export interface AgentSubagentSummary {
  slug: string;
  name: string;
  description?: string;
  path: string;
  emoji?: string;
  color?: string | null;
}

export function listSubagentDivisions(): Promise<SubagentCatalogDivision[]> {
  return request<SubagentCatalogDivision[]>("/subagent-catalog/divisions");
}

export function listSubagentCatalog(params?: {
  division?: string;
  q?: string;
}): Promise<SubagentCatalogItem[]> {
  const search = new URLSearchParams();
  if (params?.division) search.set("division", params.division);
  if (params?.q) search.set("q", params.q);
  const qs = search.toString();
  return request<SubagentCatalogItem[]>(
    `/subagent-catalog${qs ? `?${qs}` : ""}`,
  );
}

export function getSubagentCatalogItem(
  slug: string,
): Promise<SubagentCatalogDetail> {
  return request<SubagentCatalogDetail>(
    `/subagent-catalog/${encodeURIComponent(slug)}`,
  );
}

export function installSubagent(
  agentId: string,
  slug: string,
): Promise<{ installed: boolean; slug: string; path: string }> {
  return request(`/agents/${agentId}/subagents/install`, {
    method: "POST",
    body: JSON.stringify({ slug }),
  });
}

export function listAgentSubagents(
  agentId: string,
): Promise<AgentSubagentSummary[]> {
  return request<AgentSubagentSummary[]>(`/agents/${agentId}/subagents`);
}
