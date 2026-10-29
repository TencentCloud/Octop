import { getApiUrl } from "../../api/config";
import { getAuthToken } from "../../api/request";
import type { InstalledPlugin } from "../../api/modules/plugins";
import { createPluginUiHost } from "./host";
import { unregisterPluginRenderers } from "./registry";
import type { PluginUiModule } from "./types";

const loadedPlugins = new Set<string>();
const cleanups = new Map<string, () => void>();
const pending = new Map<string, Promise<void>>();
let generation = 0;
let abort: AbortController | null = null;
const blobUrls: string[] = [];

async function fetchAuthedText(
  path: string,
  signal: AbortSignal,
): Promise<string> {
  const url = getApiUrl(path);
  const token = getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(url, { headers, signal });
  if (!res.ok) {
    throw new Error(`plugin UI fetch failed: ${res.status} ${path}`);
  }
  return res.text();
}

/**
 * Dynamically import a plugin ESM via authenticated fetch + blob URL.
 * Plugins must ship a self-contained ``ui/dist/index.js`` (no relative imports).
 */
async function importPluginEsm(
  pluginId: string,
  entryRel: string,
  currentGeneration: number,
  signal: AbortSignal,
): Promise<PluginUiModule | undefined> {
  // plugin.yaml entry is usually ``ui/dist/index.js``; API paths are under ``…/ui/``.
  const normalized = entryRel.replace(/^\/+/, "");
  const underUi = normalized.startsWith("ui/")
    ? normalized.slice(3)
    : normalized;
  const apiPath = `/plugins/${encodeURIComponent(pluginId)}/ui/${underUi}`;
  const source = await fetchAuthedText(apiPath, signal);
  if (generation !== currentGeneration) return;
  const blob = new Blob([source], { type: "text/javascript" });
  const blobUrl = URL.createObjectURL(blob);
  blobUrls.push(blobUrl);
  const mod = (await import(/* @vite-ignore */ blobUrl)) as PluginUiModule;
  if (generation !== currentGeneration) return;
  return mod;
}

/** Run ``setup``; if a reset lands while an async setup is pending, undo it. */
async function runSetup(
  mod: PluginUiModule,
  pluginId: string,
  currentGeneration: number,
): Promise<void> {
  const host = createPluginUiHost(pluginId);
  const setup = mod.setup ?? mod.default?.setup;
  if (typeof setup !== "function") return;
  const cleanup = await setup(host);
  if (typeof cleanup !== "function") return;
  if (generation !== currentGeneration) {
    try {
      cleanup();
    } catch (err) {
      console.warn(`[plugin-ui] failed to clean up ${pluginId}:`, err);
    }
    return;
  }
  cleanups.set(pluginId, cleanup);
}

/** Load UI modules for installed plugins that declare ``ui.entry``. */
export async function loadInstalledPluginUis(
  plugins: InstalledPlugin[],
): Promise<void> {
  const requestedGeneration = generation;
  for (const plugin of plugins) {
    if (generation !== requestedGeneration) return;
    const entry = plugin.ui?.entry;
    if (plugin.error || plugin.enabled === false || !entry) continue;
    if (loadedPlugins.has(plugin.id)) continue;
    let loading = pending.get(plugin.id);
    if (!loading) {
      const currentGeneration = generation;
      const signal = (abort ??= new AbortController()).signal;
      loading = (async () => {
        try {
          const mod = await importPluginEsm(
            plugin.id,
            entry,
            currentGeneration,
            signal,
          );
          if (!mod || generation !== currentGeneration) return;
          unregisterPluginRenderers(plugin.id);
          await runSetup(mod, plugin.id, currentGeneration);
          if (generation === currentGeneration) loadedPlugins.add(plugin.id);
        } catch (err) {
          if (!signal.aborted) {
            console.warn(`[plugin-ui] failed to load ${plugin.id}:`, err);
          }
        }
      })();
      pending.set(plugin.id, loading);
    }
    await loading;
    if (pending.get(plugin.id) === loading) {
      pending.delete(plugin.id);
    }
  }
}

/**
 * Force re-fetch and re-register UI modules (after install/uninstall in Admin).
 * Keeps builtin renderers; drops previously loaded third-party UI blobs.
 */
export async function reloadPluginToolUis(
  plugins: InstalledPlugin[],
): Promise<void> {
  resetPluginUiLoader();
  await loadInstalledPluginUis(plugins);
}

/** Drop cached load state (e.g. after uninstall); blob URLs are revoked. */
export function resetPluginUiLoader(): void {
  generation += 1;
  abort?.abort();
  abort = null;
  pending.clear();
  for (const [id, cleanup] of cleanups) {
    try {
      cleanup();
    } catch (err) {
      console.warn(`[plugin-ui] failed to clean up ${id}:`, err);
    }
  }
  cleanups.clear();
  for (const id of loadedPlugins) {
    unregisterPluginRenderers(id);
  }
  loadedPlugins.clear();
  while (blobUrls.length) {
    const url = blobUrls.pop();
    if (url) URL.revokeObjectURL(url);
  }
}

export function isPluginUiLoaded(pluginId: string): boolean {
  return loadedPlugins.has(pluginId);
}
