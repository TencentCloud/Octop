import { request } from "../request";

export interface CreatedSkill {
  slug: string;
  name: string;
  description: string;
  artifact_type: "skill" | "hybrid";
  revision: string;
  published_at: string;
  installed: boolean;
  source: "created";
}

export const createdSkillsApi = {
  list(agentId: string): Promise<CreatedSkill[]> {
    return request<CreatedSkill[]>(
      `/agents/${encodeURIComponent(agentId)}/created-skills`,
      { cache: "no-store" },
    );
  },

  install(agentId: string, slug: string, overwrite: boolean): Promise<unknown> {
    return request(
      `/agents/${encodeURIComponent(
        agentId,
      )}/created-skills/${encodeURIComponent(slug)}/install`,
      {
        method: "POST",
        body: JSON.stringify({ overwrite }),
      },
    );
  },
};
