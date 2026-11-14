import { request } from "../request";

export interface MagpieDiscovery {
  available: boolean;
  base_url: string;
  version: string | null;
}

export function discoverMagpie(): Promise<MagpieDiscovery> {
  return request<MagpieDiscovery>("/admin/providers/magpie/discovery");
}
