import { request } from "../request";

export type MediaProviderName =
  | "volcengine"
  | "dashscope"
  | "minimax"
  | "tencent-tokenhub";

export interface MediaProviderPreset {
  provider: MediaProviderName;
  display_name: string;
  base_url: string;
  image_models: string[];
  video_models: string[];
  three_d_models: string[];
}

export interface MediaProviderSettings {
  id: string;
  provider: MediaProviderName;
  display_name: string;
  enabled: boolean;
  base_url: string;
  image_enabled: boolean;
  video_enabled: boolean;
  three_d_enabled: boolean;
  image_model: string;
  video_model: string;
  three_d_model: string;
  api_key_set: boolean;
  configured: boolean;
}

export interface MediaProviderInput {
  id: string;
  provider: MediaProviderName;
  display_name: string;
  enabled: boolean;
  base_url: string;
  image_enabled: boolean;
  video_enabled: boolean;
  three_d_enabled: boolean;
  image_model: string;
  video_model: string;
  three_d_model: string;
  api_key?: string | null;
  clear_api_key?: boolean;
}

export interface MediaGenerationSettings {
  enabled: boolean;
  providers: MediaProviderSettings[];
  default_image_provider: string | null;
  default_video_provider: string | null;
  default_three_d_provider: string | null;
  configured: boolean;
}

export interface MediaGenerationSettingsInput {
  enabled: boolean;
  providers: MediaProviderInput[];
  default_image_provider: string | null;
  default_video_provider: string | null;
  default_three_d_provider: string | null;
}

export interface MediaGenerationTestInput {
  kind: "credentials" | "image" | "video" | "3d";
  provider: MediaProviderInput;
}

export interface MediaGenerationFetchModelsResponse {
  ok: boolean;
  image_models: string[];
  video_models: string[];
  three_d_models: string[];
  total_remote: number;
  error?: string | null;
}

export const mediaGenerationApi = {
  get: () => request<MediaGenerationSettings>("/admin/media-generation"),

  getPresets: () =>
    request<MediaProviderPreset[]>("/admin/media-generation/presets"),

  save: (body: MediaGenerationSettingsInput) =>
    request<MediaGenerationSettings>("/admin/media-generation", {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  test: (body: MediaGenerationTestInput) =>
    request<{ ok: boolean; error?: string | null }>(
      "/admin/media-generation/test",
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),

  fetchModels: (provider: MediaProviderInput) =>
    request<MediaGenerationFetchModelsResponse>(
      "/admin/media-generation/fetch-models",
      {
        method: "POST",
        body: JSON.stringify({ provider }),
      },
    ),
};
