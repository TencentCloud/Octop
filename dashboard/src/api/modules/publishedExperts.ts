import { request } from "../request";

export interface PublishedExpert {
  id: string;
  slug: string;
  name: string;
  description: string;
  created_by: string;
  creator_username: string | null;
  source_agent_id: string | null;
  icon_name: string | null;
  icon_url?: string | null;
  color: string | null;
  created_at: string;
  updated_at: string;
  welcome_message?: { zh?: string; en?: string };
}

export interface PublishExpertBody {
  name: string;
  description?: string;
  slug?: string;
  welcome_message?: { zh?: string; en?: string };
}

export type RefreshPublishedExpertBody = PublishExpertBody;

export interface InstallPublishedExpertBody {
  name: string;
  description?: string;
  providers?: string[];
  default_model?: string;
  backend?: Record<string, unknown>;
  skill_package_ids?: string[];
  color?: string;
  welcome_message?: string;
  max_iters?: number | null;
  max_input_length?: number | null;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  enable_trajectory?: boolean;
}

export interface InstalledPublishedExpert {
  agent_id: string;
  name: string;
  description: string | null;
  state: string;
  published_expert_id: string;
  bootstrap_pending: boolean;
}

const publishedPath = (expertId: string) =>
  `/experts/published/${encodeURIComponent(expertId)}`;

export const publishedExpertsApi = {
  list: () => request<PublishedExpert[]>("/experts/published"),

  publish: (agentId: string, body: PublishExpertBody) =>
    request<PublishedExpert>(
      `/agents/${encodeURIComponent(agentId)}/publish-expert`,
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),

  refresh: (expertId: string, body?: RefreshPublishedExpertBody) =>
    request<PublishedExpert>(`${publishedPath(expertId)}/refresh`, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    }),

  unpublish: (expertId: string) =>
    request<void>(publishedPath(expertId), { method: "DELETE" }),

  install: (expertId: string, body: InstallPublishedExpertBody) =>
    request<InstalledPublishedExpert>(`${publishedPath(expertId)}/install`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
