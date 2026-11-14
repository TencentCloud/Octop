import { request } from "../request";

export interface ProviderKeyStatus {
  provider_name: string;
  has_own_key: boolean;
  updated_at: number | null;
  user_key_required: boolean;
  keyless: boolean;
}

export const userProviderKeysApi = {
  list: () => request<ProviderKeyStatus[]>("/me/provider-keys"),

  set: (providerName: string, apiKey: string) =>
    request<ProviderKeyStatus>(
      `/me/provider-keys/${encodeURIComponent(providerName)}`,
      {
        method: "PUT",
        body: JSON.stringify({ api_key: apiKey }),
      },
    ),

  remove: (providerName: string) =>
    request<void>(`/me/provider-keys/${encodeURIComponent(providerName)}`, {
      method: "DELETE",
    }),
};
