import type { InstalledPlugin } from "../../api/modules/plugins";

/** tool_name → plugin_id from the last loaded plugin list. */
const toolToPlugin = new Map<string, string>();

export function updateToolPluginIndex(plugins: InstalledPlugin[]): void {
  toolToPlugin.clear();
  for (const plugin of plugins) {
    if (plugin.error) continue;
    for (const tool of plugin.tools ?? []) {
      if (tool.name) {
        toolToPlugin.set(tool.name, plugin.id);
      }
    }
  }
}

export function lookupPluginIdForTool(
  toolName: string | undefined,
): string | null {
  if (!toolName) return null;
  return toolToPlugin.get(toolName) ?? null;
}
