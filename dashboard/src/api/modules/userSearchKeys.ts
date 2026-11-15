import { request } from "../request";

export interface SearchKeyStatus {
  provider_id: string;
  label_key: string;
  env_vars: string[];
  optional_env_vars: string[];
  personal_key: boolean;
  has_own_key: boolean;
  updated_at: number | null;
  user_key_required: boolean;
}

export interface SearchProbeResult {
  success: boolean;
  provider_id: string;
  response_time_ms: number;
  result_count?: number | null;
  message?: string | null;
  error?: string | null;
  error_type?: string | null;
}

export const userSearchKeysApi = {
  list: () => request<SearchKeyStatus[]>("/me/search-keys"),

  set: (providerId: string, env: Record<string, string>) =>
    request<SearchKeyStatus>(
      `/me/search-keys/${encodeURIComponent(providerId)}`,
      {
        method: "PUT",
        body: JSON.stringify({ env }),
      },
    ),

  remove: (providerId: string) =>
    request<void>(`/me/search-keys/${encodeURIComponent(providerId)}`, {
      method: "DELETE",
    }),

  test: (providerId: string, env?: Record<string, string>) =>
    request<SearchProbeResult>(
      `/me/search-keys/${encodeURIComponent(providerId)}/test`,
      {
        method: "POST",
        body: JSON.stringify(env ? { env } : {}),
      },
    ),
};
