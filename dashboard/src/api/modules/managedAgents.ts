import { request } from "../request";
import type { OctopAgent } from "../../context/AgentContext";
import type { ResourceVisibilityMode } from "./userGroups";

export interface ManagedWorkspaceFile {
  name: string;
  content: string;
}

export interface ManagedQuickPrompt {
  title: { zh?: string; en?: string };
  description?: { zh?: string; en?: string };
  prompt: { zh?: string; en?: string };
  color?: string;
  icon_name?: string | null;
}

export interface ManagedTemplate {
  files: ManagedWorkspaceFile[];
  quick_prompts: ManagedQuickPrompt[];
  home: string;
}

/** `{home}/{agentId}` using the separator already present in `home`. */
export function managedWorkspaceDir(home: string, agentId: string): string {
  const base = home.replace(/[\\/]+$/, "");
  const sep = base.includes("\\") ? "\\" : "/";
  return `${base}${sep}${agentId}`;
}

export interface ManagedAgentCreate {
  name: string;
  runner: string;
  workspace_dir: string;
  description?: string;
  welcome_message?: string;
  agent_id?: string;
  color?: string;
  icon_url?: string;
  enable_trajectory?: boolean;
  visibility?: ResourceVisibilityMode;
  group_ids?: string[];
  quick_prompts?: ManagedQuickPrompt[];
  file_overrides?: ManagedWorkspaceFile[];
  skill_package_ids?: string[];
  knowledge_base_ids?: string[];
  mcp_servers?: string[];
  permission_mode?: "ask" | "yolo";
}

export const managedAgentsApi = {
  template: () => request<ManagedTemplate>("/managed-agents/template"),
  create: (body: ManagedAgentCreate) =>
    request<OctopAgent>("/managed-agents", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
