import { getApiUrl } from "../../api/config";
import { getAuthToken } from "../../api/request";
import type { InstalledPlugin } from "../../api/modules/plugins";
import { createPluginUiHost } from "./host";
import { unregisterPluginRenderers } from "./registry";
import type { PluginPageDeclaration, PluginUiModule } from "./types";
import {
  parsePluginPageManifest,
  unregisterPluginPages,
} from "../pages/registry";

interface PluginUiLoad {
  id: string;
  signature: string;
  entry: string;
  manifest?: string;
  enabled: boolean;
  loaded: boolean;
  pending?: Promise<void>;
  blobUrls: string[];
}

const pluginLoads = new Map<string, PluginUiLoad>();
const isCurrent = (load: PluginUiLoad) => pluginLoads.get(load.id) === load;

function signature(plugin: InstalledPlugin): string {
  return JSON.stringify([
    plugin.version,
    plugin.enabled !== false,
    plugin.ui?.entry,
    plugin.ui?.manifest,
  ]);
}

function removePluginUi(load: PluginUiLoad): void {
  pluginLoads.delete(load.id);
  unregisterPluginRenderers(load.id);
  unregisterPluginPages(load.id);
  for (const url of load.blobUrls) URL.revokeObjectURL(url);
  load.blobUrls.length = 0;
}

async function fetchAuthedText(path: string): Promise<string> {
  const url = getApiUrl(path);
  const token = getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(url, { headers });
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
  load: PluginUiLoad,
): Promise<PluginUiModule | undefined> {
  // plugin.yaml entry is usually ``ui/dist/index.js``; API paths are under ``…/ui/``.
  const normalized = load.entry.replace(/^\/+/, "");
  const underUi = normalized.startsWith("ui/")
    ? normalized.slice(3)
    : normalized;
  const apiPath = `/plugins/${encodeURIComponent(load.id)}/ui/${underUi}`;
  const source = await fetchAuthedText(apiPath);
  if (!isCurrent(load)) return;
  const blob = new Blob([source], { type: "text/javascript" });
  const blobUrl = URL.createObjectURL(blob);
  load.blobUrls.push(blobUrl);
  return (await import(/* @vite-ignore */ blobUrl)) as PluginUiModule;
}

function runSetup(
  mod: PluginUiModule,
  load: PluginUiLoad,
  pages: PluginPageDeclaration[],
): void {
  const host = createPluginUiHost(load.id, pages, load.enabled, () =>
    isCurrent(load),
  );
  const setup = mod.setup ?? mod.default?.setup;
  if (typeof setup === "function") {
    setup(host);
  }
}

async function loadPluginUi(load: PluginUiLoad): Promise<void> {
  try {
    let pages: PluginPageDeclaration[] = [];
    if (load.enabled && load.manifest) {
      const manifestPath = load.manifest
        .replace(/^\/+/, "")
        .replace(/^ui\//, "");
      try {
        pages = parsePluginPageManifest(
          JSON.parse(
            await fetchAuthedText(
              `/plugins/${encodeURIComponent(load.id)}/ui/${manifestPath}`,
            ),
          ),
        );
      } catch (error) {
        // Legacy tool UIs can still load without valid optional page metadata.
        if (isCurrent(load))
          console.warn(
            `[plugin-ui] page manifest unavailable for ${load.id}:`,
            error,
          );
      }
    }
    if (!isCurrent(load)) return;
    const mod = await importPluginEsm(load);
    if (!mod || !isCurrent(load)) return;
    runSetup(mod, load, pages);
    load.loaded = true;
  } catch (err) {
    if (isCurrent(load)) {
      removePluginUi(load);
      console.warn(`[plugin-ui] failed to load ${load.id}:`, err);
    }
  } finally {
    load.pending = undefined;
  }
}

/** Load UI modules for installed plugins that declare ``ui.entry``. */
export async function loadInstalledPluginUis(
  plugins: InstalledPlugin[],
): Promise<void> {
  const usable = new Map(
    plugins
      .filter((plugin) => !plugin.error && plugin.ui?.entry)
      .map((plugin) => [plugin.id, plugin]),
  );
  // Reconcile the full snapshot before awaiting assets. Old loads and retained
  // setup hosts become invalid as soon as a plugin changes or disappears.
  for (const load of pluginLoads.values()) {
    const plugin = usable.get(load.id);
    if (!plugin || load.signature !== signature(plugin)) removePluginUi(load);
  }
  const snapshot: PluginUiLoad[] = [];
  for (const plugin of usable.values()) {
    let load = pluginLoads.get(plugin.id);
    if (!load) {
      load = {
        id: plugin.id,
        signature: signature(plugin),
        entry: plugin.ui!.entry,
        manifest: plugin.ui!.manifest,
        enabled: plugin.enabled !== false,
        loaded: false,
        blobUrls: [],
      };
      pluginLoads.set(plugin.id, load);
    }
    snapshot.push(load);
  }
  for (const load of snapshot) {
    if (!isCurrent(load) || load.loaded) continue;
    load.pending ??= loadPluginUi(load);
    await load.pending;
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
  for (const load of pluginLoads.values()) removePluginUi(load);
}

export function isPluginUiLoaded(pluginId: string): boolean {
  return pluginLoads.get(pluginId)?.loaded === true;
}
