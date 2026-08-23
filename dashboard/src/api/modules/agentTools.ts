import { request } from "../request";

export type ToolSettingsSource = "builtin" | "plugin";

export interface ToolSettingsItem {
  name: string;
  source: ToolSettingsSource;
  category: string;
  label: string;
  description?: string | null;
  enabled: boolean;
  disableable: boolean;
  available?: boolean;
  plugin_id?: string | null;
}

export interface ToolSettingsResponse {
  tools: ToolSettingsItem[];
}

export type AgentPluginsConfig = Record<
  string,
  {
    tools?: Record<
      string,
      {
        enabled?: boolean;
        config?: Record<string, unknown>;
      }
    >;
  }
>;

export interface ToolSettingsPutBody {
  disabled_builtin: string[];
  plugins?: AgentPluginsConfig;
}

export interface ToolSettingPatchBody {
  enabled: boolean;
  source: ToolSettingsSource;
  plugin_id?: string | null;
}

export const agentToolsApi = {
  get(agentId: string): Promise<ToolSettingsResponse> {
    return request<ToolSettingsResponse>(
      `/agents/${encodeURIComponent(agentId)}/tool-settings`,
    );
  },

  put(
    agentId: string,
    body: ToolSettingsPutBody,
  ): Promise<ToolSettingsResponse> {
    return request<ToolSettingsResponse>(
      `/agents/${encodeURIComponent(agentId)}/tool-settings`,
      {
        method: "PUT",
        body: JSON.stringify(body),
      },
    );
  },

  patch(
    agentId: string,
    toolName: string,
    body: ToolSettingPatchBody,
  ): Promise<ToolSettingsResponse> {
    return request<ToolSettingsResponse>(
      `/agents/${encodeURIComponent(
        agentId,
      )}/tool-settings/${encodeURIComponent(toolName)}`,
      {
        method: "PATCH",
        body: JSON.stringify(body),
      },
    );
  },
};
