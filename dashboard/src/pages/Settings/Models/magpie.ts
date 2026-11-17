import type { ProviderModel } from "./useProviders";

export const MAGPIE_PRESET_ID = "magpie";
export const MAGPIE_PRESET_NAME = "Magpie";
export const MAGPIE_INTEGRATION = "magpie";
export const MAGPIE_DEFAULT_BASE_URL = "http://127.0.0.1:3425/v1";
export const MAGPIE_LOCAL_API_KEY = "magpie-octop";

export interface MagpieCatalogModel {
  id: string;
  name: string;
  input?: string[];
  context_window?: number;
  max_tokens?: number;
  reasoning?: boolean;
  reasoning_config?: ProviderModel["reasoning_config"];
}

export interface MagpieSyncPlan {
  models: ProviderModel[];
  added: string[];
  removed: string[];
}

export function isMagpieDefaultBaseUrl(
  baseUrl: string | null | undefined,
): boolean {
  if (!baseUrl) return false;
  try {
    const parsed = new URL(baseUrl.trim());
    const path = parsed.pathname.replace(/\/$/, "") || "/";
    return (
      parsed.protocol === "http:" &&
      parsed.hostname === "127.0.0.1" &&
      parsed.port === "3425" &&
      path === "/v1"
    );
  } catch {
    return false;
  }
}

export function isMagpieProvider(input: {
  name?: string | null;
  base_url?: string | null;
  integration?: string | null;
}): boolean {
  if ((input.integration || "").trim().toLowerCase() === MAGPIE_INTEGRATION) {
    return true;
  }
  const name = (input.name || "").trim().toLowerCase();
  if (name === MAGPIE_PRESET_ID || name === MAGPIE_PRESET_NAME.toLowerCase()) {
    return true;
  }
  return isMagpieDefaultBaseUrl(input.base_url);
}

export function magpieIntegrationExtra(): string {
  return JSON.stringify({ integration: MAGPIE_INTEGRATION });
}

function catalogModel(item: MagpieCatalogModel): ProviderModel {
  const model: ProviderModel = {
    id: item.id,
    name: item.name || item.id,
    enabled: false,
    input: item.input?.length ? item.input : ["text"],
    thinking: null,
  };
  if (item.context_window) model.context_window = item.context_window;
  if (item.max_tokens) model.max_tokens = item.max_tokens;
  if (item.reasoning) model.reasoning = true;
  if (item.reasoning_config) model.reasoning_config = item.reasoning_config;
  return model;
}

/** Same capability mapping as one-click add. New rows stay disabled. */
export function magpieModelFromCatalog(
  item: MagpieCatalogModel,
  enabled = false,
): ProviderModel {
  return { ...catalogModel(item), enabled };
}

export interface MagpieRefreshBody {
  models: ProviderModel[];
  base_url?: string;
  api_key?: string;
}

/**
 * Catalog refresh must persist the address and key that produced it.
 * An empty key means "keep the saved key" and is omitted.
 */
export function magpieRefreshBody(args: {
  models: ProviderModel[];
  savedBaseUrl?: string | null;
  draftBaseUrl?: string | null;
  draftApiKey?: string | null;
}): MagpieRefreshBody {
  const body: MagpieRefreshBody = { models: args.models };
  const nextBase = (args.draftBaseUrl ?? "").trim();
  const savedBase = (args.savedBaseUrl ?? "").trim();
  if (nextBase && nextBase !== savedBase) body.base_url = nextBase;
  const key = (args.draftApiKey ?? "").trim();
  if (key) body.api_key = key;
  return body;
}

export function magpieRefreshConnectionChanged(
  body: MagpieRefreshBody,
): boolean {
  return body.base_url !== undefined || body.api_key !== undefined;
}

/** Fields this refresh did not write stay dirty so Save is not disabled. */
export function magpieRefreshLeavesDirty(
  body: MagpieRefreshBody,
  saved: {
    base_url?: string | null;
    note?: string | null;
    model?: string | null;
    kind?: string | null;
    stream_usage?: boolean | null;
  },
  current: {
    base_url?: string | null;
    api_key?: string | null;
    note?: string | null;
    model?: string | null;
    kind?: string | null;
    stream_usage?: boolean | null;
  },
): boolean {
  const persistedBase = body.base_url ?? (saved.base_url ?? "").trim();
  if ((current.base_url ?? "").trim() !== persistedBase) return true;
  const currentKey = (current.api_key ?? "").trim();
  if (currentKey && currentKey !== (body.api_key ?? "")) return true;
  if ((current.note ?? "") !== (saved.note ?? "")) return true;
  if ((current.model ?? "").trim() !== (saved.model ?? "").trim()) return true;
  if (
    current.kind != null &&
    saved.kind != null &&
    current.kind !== saved.kind
  ) {
    return true;
  }
  if (
    current.stream_usage != null &&
    Boolean(current.stream_usage) !== (saved.stream_usage !== false)
  ) {
    return true;
  }
  return false;
}

/** Enabled catalog for a confirmed first add. Empty input returns null. */
export function initialMagpieModels(
  fetched: MagpieCatalogModel[],
): ProviderModel[] | null {
  const models: ProviderModel[] = [];
  const seen = new Set<string>();
  for (const item of fetched) {
    const id = item.id?.trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    models.push(magpieModelFromCatalog({ ...item, id }, true));
  }
  return models.length > 0 ? models : null;
}

/**
 * Keep saved rows, append new ids as disabled, and list removals.
 * Callers must confirm before writing. An empty catalog removes every row.
 */
export function planMagpieSync(
  existing: ProviderModel[],
  fetched: MagpieCatalogModel[],
): MagpieSyncPlan {
  const saved = new Map<string, ProviderModel>();
  for (const model of existing) {
    const id = model.id?.trim();
    if (id && !saved.has(id)) saved.set(id, model);
  }
  const order: string[] = [];
  const incoming = new Map<string, MagpieCatalogModel>();
  for (const item of fetched) {
    const id = item.id?.trim();
    if (!id || incoming.has(id)) continue;
    incoming.set(id, { ...item, id });
    order.push(id);
  }
  const added = order.filter((id) => !saved.has(id));
  const removed = [...saved.keys()].filter((id) => !incoming.has(id));
  const models = order.map((id) => {
    const kept = saved.get(id);
    if (kept) return kept;
    return magpieModelFromCatalog(incoming.get(id)!);
  });
  return { models, added, removed };
}
