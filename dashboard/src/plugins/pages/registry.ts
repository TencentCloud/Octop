import type {
  PluginPageDeclaration,
  PluginPageRegistration,
} from "../toolRenderers/types";

const pages = new Map<string, PluginPageRegistration>();
const listeners = new Set<() => void>();
let version = 0;
const key = (pluginId: string, id: string) => `${pluginId}::${id}`;

/** Optional page metadata; old renderer-only manifests remain valid. */
export function parsePluginPageManifest(
  value: unknown,
): PluginPageDeclaration[] {
  if (!value || typeof value !== "object" || !("pages" in value)) return [];
  const raw = (value as { pages: unknown }).pages;
  if (!Array.isArray(raw) || raw.length > 20)
    throw new Error("Invalid plugin pages manifest");
  const seen = new Set<string>();
  return raw.map((page) => {
    if (
      !page ||
      typeof page.id !== "string" ||
      !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(page.id) ||
      seen.has(page.id) ||
      typeof page.title !== "string" ||
      !page.title.trim() ||
      page.title.length > 120
    ) {
      throw new Error("Invalid plugin page declaration");
    }
    seen.add(page.id);
    return { id: page.id, title: page.title.trim() };
  });
}

function changed() {
  version += 1;
  for (const listener of listeners) listener();
}

export function subscribePluginPages(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export const getPluginPagesVersion = () => version;

export function registerPluginPage(page: PluginPageRegistration): void {
  pages.set(key(page.pluginId, page.id), page);
  changed();
}

export function resolvePluginPage(
  pluginId: string,
  id: string,
): PluginPageRegistration | null {
  return pages.get(key(pluginId, id)) ?? null;
}

export function listPluginPages(): PluginPageRegistration[] {
  return [...pages.values()];
}

export function unregisterPluginPages(pluginId: string): void {
  let removed = false;
  for (const [pageKey, page] of pages) {
    if (page.pluginId === pluginId) {
      pages.delete(pageKey);
      removed = true;
    }
  }
  if (removed) changed();
}

export function clearPluginPages(): void {
  pages.clear();
  changed();
}
