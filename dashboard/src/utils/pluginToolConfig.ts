import type { AgentPluginTool } from "../api/modules/plugins";

export function pluginToolNeedsConfig(tool: AgentPluginTool): boolean {
  return tool.config_fields.some((field) => {
    const value = tool.config[field.name];
    return (
      field.required && (value === undefined || value === null || value === "")
    );
  });
}
