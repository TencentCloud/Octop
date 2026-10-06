import { request } from "../request";

export type MediaProviderName = "volcengine" | "dashscope" | "minimax";

export interface MediaProviderPreset {
  provider: MediaProviderName;
  display_name: string;
  base_url: string;
  image_models: string[];
  video_models: string[];
}

export interface MediaProviderSettings {
  id: string;
  provider: MediaProviderName;
  display_name: string;
  enabled: boolean;
  base_url: string;
  image_enabled: boolean;
  video_enabled: boolean;
  image_model: string;
  video_model: string;
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
  image_model: string;
  video_model: string;
  api_key?: string | null;
  clear_api_key?: boolean;
}

export interface MediaGenerationSettings {
  enabled: boolean;
  providers: MediaProviderSettings[];
  default_image_provider: string | null;
  default_video_provider: string | null;
  configured: boolean;
}

export interface MediaGenerationSettingsInput {
  enabled: boolean;
  providers: MediaProviderInput[];
  default_image_provider: string | null;
  default_video_provider: string | null;
}

export interface MediaGenerationTestInput {
  kind: "credentials" | "image" | "video";
  provider: MediaProviderInput;
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
};
