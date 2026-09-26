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
  enabled?: boolean;
  display_name?: string;
  issuer?: string;
  client_id?: string;
  client_secret?: string;
  scopes?: string;
  dashboard_origin?: string | null;
}

export interface OidcConfigTestResult {
  ok: boolean;
  detail?: string;
}

export interface LdapConfig {
  enabled: boolean;
  display_name: string;
  server_url: string;
  start_tls: boolean;
  verify_tls: boolean;
  bind_dn: string;
  has_bind_password: boolean;
  user_base_dn: string;
  user_filter: string;
  username_attribute: string;
  email_attribute: string;
  display_name_attribute: string;
  group_attribute: string;
  admin_groups: string;
  auto_provision: boolean;
  timeout_seconds: number;
}

export interface LdapConfigPut {
  enabled?: boolean;
  display_name?: string;
  server_url?: string;
  start_tls?: boolean;
  verify_tls?: boolean;
  bind_dn?: string;
  bind_password?: string;
  user_base_dn?: string;
  user_filter?: string;
  username_attribute?: string;
  email_attribute?: string;
  display_name_attribute?: string;
  group_attribute?: string;
  admin_groups?: string;
  auto_provision?: boolean;
  timeout_seconds?: number;
}

export interface LdapConfigTestResult {
  ok: boolean;
  detail: string;
}

export interface OauthAppConfig {
  kind: string;
  enabled: boolean;
  display_name: string;
  client_id: string;
  has_client_secret: boolean;
  redirect_uri?: string;
  extra: { region?: string; agent_id?: string };
}

export interface OauthAppConfigPut {
  enabled?: boolean;
  display_name?: string;
  client_id?: string;
  client_secret?: string;
  extra?: { region?: string; agent_id?: string };
}

/** @deprecated Prefer OauthAppConfig */
export type FeishuConfig = OauthAppConfig;
/** @deprecated Prefer OauthAppConfigPut */
export type FeishuConfigPut = OauthAppConfigPut;

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
  getLdapConfig(): Promise<LdapConfig> {
    return request<LdapConfig>("/auth/ldap/config");
  },
  putLdapConfig(body: LdapConfigPut): Promise<LdapConfig> {
    return request<LdapConfig>("/auth/ldap/config", {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },
  testLdapConfig(): Promise<LdapConfigTestResult> {
    return request<LdapConfigTestResult>("/auth/ldap/config/test", {
      method: "POST",
    });
  },
  getOauthProvider(kind: string): Promise<OauthAppConfig> {
    return request<OauthAppConfig>(`/auth/oauth/providers/${kind}`);
  },
  putOauthProvider(
    kind: string,
    body: OauthAppConfigPut,
  ): Promise<OauthAppConfig> {
    return request<OauthAppConfig>(`/auth/oauth/providers/${kind}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },
  testOauthProvider(kind: string): Promise<OidcConfigTestResult> {
    return request<OidcConfigTestResult>(`/auth/oauth/providers/${kind}/test`, {
      method: "POST",
    });
  },
  /** @deprecated Prefer getOauthProvider("feishu") */
  getFeishuConfig(): Promise<OauthAppConfig> {
    return ssoApi.getOauthProvider("feishu");
  },
  /** @deprecated Prefer putOauthProvider("feishu", body) */
  putFeishuConfig(body: OauthAppConfigPut): Promise<OauthAppConfig> {
    return ssoApi.putOauthProvider("feishu", body);
  },
  /** @deprecated Prefer testOauthProvider("feishu") */
  testFeishuConfig(): Promise<OidcConfigTestResult> {
    return ssoApi.testOauthProvider("feishu");
  },
};
