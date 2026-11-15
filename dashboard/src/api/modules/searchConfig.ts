import { request } from "../request";

export interface SearchProviderInfo {
  id: string;
  env_vars: string[];
  optional_env_vars: string[];
  personal_key: boolean;
  endpoint_env?: string | null;
  label_key: string;
}

export interface SearchProvidersResponse {
  providers: SearchProviderInfo[];
}

export interface SearchEndpointResponse {
  provider_id: string;
  endpoint_env: string;
  endpoint: string | null;
}

export const searchConfigApi = {
  listProviders: () => request<SearchProvidersResponse>("/search/providers"),

  setEndpoint: (providerId: string, endpoint: string | null) =>
    request<SearchEndpointResponse>(
      `/search/${encodeURIComponent(providerId)}/endpoint`,
      {
        method: "PUT",
        body: JSON.stringify({ endpoint }),
      },
    ),
};
