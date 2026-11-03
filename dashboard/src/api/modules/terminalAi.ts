import { request } from "../request";

export interface TerminalContext {
  os: string;
  distro: string;
  shell: string;
  hostname: string;
  username: string;
  workspace_dir: string;
  agent_id: string;
  agent_name: string;
}

export const terminalAiApi = {
  getContext: (agentId: string) =>
    request<TerminalContext>(`/agents/${agentId}/terminal/context`),

  createGeneralAssistant: () =>
    request<{
      id: number;
      agent_id: string;
      name: string;
      description: string;
      state: string;
      expert_id: string;
    }>("/agents/from-expert/general-assistant", {
      method: "POST",
      body: JSON.stringify({}),
    }),
};
