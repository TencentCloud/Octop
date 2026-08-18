import { request } from "../request";

export interface MediaGenerationSettings {
  enabled: boolean;
  provider: "volcengine";
  base_url: string;
  image_enabled: boolean;
  video_enabled: boolean;
  image_model: string;
  video_model: string;
  api_key_set: boolean;
  configured: boolean;
}

export interface MediaGenerationSettingsInput {
  enabled: boolean;
  image_enabled: boolean;
  video_enabled: boolean;
  image_model: string;
  video_model: string;
  api_key?: string | null;
}

export interface MediaGenerationTestInput {
  kind: "credentials" | "image" | "video";
  api_key?: string | null;
  image_model?: string;
  video_model?: string;
}

export const mediaGenerationApi = {
  get: () => request<MediaGenerationSettings>("/admin/media-generation"),

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
