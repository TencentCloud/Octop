import { request } from "../request";

export interface OidcConfig {
  enabled: boolean;
  display_name: string;
  issuer: string;
  client_id: string;
  scopes: string;
  dashboard_origin: string | null;
  has_client_secret: boolean;
  redirect_uri?: string;
}

export interface OidcConfigPut {
  enabled: boolean;
  display_name: string;
  issuer: string;
  client_id: string;
  client_secret?: string;
  scopes: string;
  dashboard_origin?: string | null;
}

export interface OidcConfigTestResult {
  ok: boolean;
  detail?: string;
}

export const ssoApi = {
  getOidcConfig(): Promise<OidcConfig> {
    return request<OidcConfig>("/auth/oidc/config");
  },
  putOidcConfig(body: OidcConfigPut): Promise<OidcConfig> {
    return request<OidcConfig>("/auth/oidc/config", {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },
  testOidcConfig(): Promise<OidcConfigTestResult> {
    return request<OidcConfigTestResult>("/auth/oidc/config/test", {
      method: "POST",
    });
  },
};
