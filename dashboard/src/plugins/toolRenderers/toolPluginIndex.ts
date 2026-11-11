import { useSyncExternalStore } from "react";
import type { InstalledPlugin } from "../../api/modules/plugins";

/** tool_name → plugin_id from the last loaded plugin list. */
const toolToPlugin = new Map<string, string>();
let indexReady = false;
let indexVersion = 0;
const listeners = new Set<() => void>();

function bumpIndex(): void {
  indexVersion += 1;
  for (const listener of listeners) {
    try {
      listener();
    } catch {
      /* ignore */
    }
  }
}

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
  indexReady = true;
  bumpIndex();
}

/** Drop the catalog (tests). Lookups stay unknown until the next update. */
export function clearToolPluginIndex(): void {
  toolToPlugin.clear();
  indexReady = false;
  bumpIndex();
}

export function isToolPluginIndexReady(): boolean {
  return indexReady;
}

export function subscribeToolPluginIndex(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getToolPluginIndexVersion(): number {
  return indexVersion;
}

/** Re-render after the installed-plugin list arrives. */
export function useToolPluginIndexVersion(): number {
  return useSyncExternalStore(
    subscribeToolPluginIndex,
    getToolPluginIndexVersion,
    getToolPluginIndexVersion,
  );
}

export function lookupPluginIdForTool(
  toolName: string | undefined,
): string | null {
  if (!toolName) return null;
  return toolToPlugin.get(toolName) ?? null;
}
