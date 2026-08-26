import { request } from "../request";

export interface OctopTimezoneSettings {
  timezone: string;
}

export interface OctopUploadSettings {
  max_upload_mb: number;
  max_upload_bytes: number;
}

export interface OctopCapabilitiesSettings {
  mobile: { enabled: boolean; backend: string };
}

export const octopSettingsApi = {
  timezone: () => request<OctopTimezoneSettings>("/settings/timezone"),
  upload: () => request<OctopUploadSettings>("/settings/upload"),
  capabilities: () =>
    request<OctopCapabilitiesSettings>("/settings/capabilities", {
      cache: "no-store",
    }),
};
