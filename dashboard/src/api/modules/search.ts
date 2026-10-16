import { request } from "../request";
import type { TestSearchResponse } from "../types";

export interface CustomSearchProvider {
  id: string;
  name: string;
  url: string;
  method: "GET" | "POST";
  headers: Record<string, string>;
  params: Record<string, string>;
  body: Record<string, unknown>;
  results_path: string;
  title_path: string;
  url_path: string;
  content_path: string;
  api_key_set: boolean;
}

export type CustomSearchProviderUpdate = Omit<
  CustomSearchProvider,
  "api_key_set"
> & { api_key?: string | null };

export interface CustomSearchConfig {
  providers: CustomSearchProvider[];
  /** Custom provider ID, "preset:<provider>" for a preset, or null for built-in search. */
  active_provider_id: string | null;
  /** Configured preset IDs, including credentials supplied by the server environment. */
  configured_preset_ids?: string[];
}

export interface CustomSearchConfigUpdate {
  providers: CustomSearchProviderUpdate[];
  /** Select one third-party engine; null explicitly disables all third-party engines. */
  active_provider_id: string | null;
}

export const searchApi = {
  getCustom: () => request<CustomSearchConfig>("/search/custom"),
  saveCustom: (config: CustomSearchConfigUpdate) =>
    request<CustomSearchConfig>("/search/custom", {
      method: "PUT",
      body: JSON.stringify(config),
    }),
  testCustom: (provider: CustomSearchProviderUpdate) =>
    request<TestSearchResponse>("/search/custom/test", {
      method: "POST",
      body: JSON.stringify({ provider }),
    }),
};
