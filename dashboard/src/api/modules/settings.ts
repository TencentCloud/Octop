import { request } from "../request";

export interface OctopTimezoneSettings {
  timezone: string;
}

export const octopSettingsApi = {
  timezone: () => request<OctopTimezoneSettings>("/settings/timezone"),
};
