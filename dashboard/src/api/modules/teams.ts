import { request } from "../request";

export interface TeamMemberSummary {
  agent_id: string;
  name: string;
  color?: string | null;
  icon_name?: string | null;
  icon_url?: string | null;
  state?: string;
  is_shared?: boolean;
  user_id?: number | null;
}

export interface TeamRecord {
  team_id: string;
  agent_id: string;
  name: string;
  description?: string | null;
  default_model?: string | null;
  color?: string | null;
  icon_name?: string | null;
  icon_url?: string | null;
  welcome_message?: string | null;
  state?: string;
  kind: "team";
  member_ids: string[];
  members: TeamMemberSummary[];
}

export interface TeamWriteBody {
  name?: string;
  description?: string | null;
  default_model?: string | null;
  color?: string | null;
  icon_name?: string | null;
  icon_url?: string | null;
  welcome_message?: string | null;
  member_ids?: string[];
}

export interface TeamTemplateFile {
  name: string;
  content: string;
}

export const teamsApi = {
  list: () => request<TeamRecord[]>("/teams"),
  templateFiles: () => request<TeamTemplateFile[]>("/teams/template"),
  get: (teamId: string) => request<TeamRecord>(`/teams/${teamId}`),
  create: (body: TeamWriteBody & { name: string; member_ids: string[] }) =>
    request<TeamRecord>("/teams", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (teamId: string, body: TeamWriteBody) =>
    request<TeamRecord>(`/teams/${teamId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  remove: (teamId: string) =>
    request<void>(`/teams/${teamId}`, { method: "DELETE" }),
};
