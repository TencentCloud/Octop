import { request } from "../request";

export interface OctopTimezoneSettings {
  timezone: string;
}

export interface OctopCapabilitiesSettings {
  mobile: { enabled: boolean; backend: string };
}

export const octopSettingsApi = {
  timezone: () => request<OctopTimezoneSettings>("/settings/timezone"),
  capabilities: () =>
    request<OctopCapabilitiesSettings>("/settings/capabilities", {
      cache: "no-store",
    }),
};
