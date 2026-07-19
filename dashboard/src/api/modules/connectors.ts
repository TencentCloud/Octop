import { request } from "../request";

export interface ConnectorCatalogEntry {
  kind: string;
  name: string;
  description: string;
  auth_kind: string;
  doc_url: string;
  icon: string;
  color: string;
  phase: "available" | "coming_soon";
  mcp_mode: "remote" | "gateway";
  quick_auth_url?: string | null;
  login_url?: string | null;
  guide_url?: string | null;
  manual_url?: string | null;
  auth_hint?: string | null;
  supports_quick_auth?: boolean;
  oauth_mode?: "dynamic" | "configured" | null;
  oauth_ready?: boolean;
}

export interface ConnectorAuthInfo {
  authorize_url: string | null;
  login_url: string | null;
  guide_url: string | null;
  manual_url: string | null;
  auth_hint: string | null;
}

export interface ConnectorInstance {
  instance_id: string;
  kind: string;
  display_name: string;
  status: string;
  mcp_server_name: string;
  has_credentials: boolean;
  created_at: number;
  updated_at: number;
}

export interface ConnectorCredentialsPreview {
  token_configured?: boolean;
  oauth_configured?: boolean;
  expires_at?: number;
  auth_configured?: boolean;
  bkn?: string;
  knowledge_base_id?: string;
  api_key_configured?: boolean;
  client_id?: string;
  email?: string;
  mail_provider?: string;
  imap_host?: string;
  smtp_host?: string;
  password_configured?: boolean;
  app_id?: string;
  sdk_id?: string;
  secret_key_configured?: boolean;
}

export interface ConnectorInstanceDetail extends ConnectorInstance {
  config: Record<string, unknown>;
  credentials_preview: ConnectorCredentialsPreview;
}

export interface ConnectorProbeResult {
  ok: boolean;
  tool_count?: number;
  tools?: { name: string; description: string }[];
  error?: string;
  status_code?: number;
}

export type CustomMcpTransport = "streamable_http" | "stdio";

export interface CustomMcpServerSpec {
  transport: CustomMcpTransport;
  url?: string;
  headers?: Record<string, string>;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  enabled?: boolean;
}

export type CustomMcpServers = Record<string, CustomMcpServerSpec>;

export const connectorsApi = {
  catalog: () => request<ConnectorCatalogEntry[]>("/connectors/catalog"),

  listInstances: () => request<ConnectorInstance[]>("/connector-instances"),

  getInstance: (instanceId: string) =>
    request<ConnectorInstanceDetail>(`/connector-instances/${instanceId}`),

  createInstance: (body: {
    kind: string;
    display_name: string;
    credentials: Record<string, unknown>;
  }) =>
    request<ConnectorInstance>("/connector-instances", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  deleteInstance: (instanceId: string) =>
    request<void>(`/connector-instances/${instanceId}`, { method: "DELETE" }),

  patchInstance: (
    instanceId: string,
    body: { status?: "active" | "disabled" },
  ) =>
    request<ConnectorInstance>(`/connector-instances/${instanceId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  testInstance: (instanceId: string) =>
    request<ConnectorProbeResult>(`/connector-instances/${instanceId}/test`, {
      method: "POST",
    }),

  oauthStart: (kind: string, redirectAfter?: string) =>
    request<{ authorize_url: string; state_id: string }>(
      `/connectors/oauth/${kind}/start`,
      {
        method: "POST",
        body: JSON.stringify({ redirect_after: redirectAfter }),
      },
    ),

  oauthPending: (stateId: string) =>
    request<{ kind: string; tokens: Record<string, unknown> }>(
      `/connectors/oauth/pending/${stateId}`,
    ),

  authorizeUrl: (kind: string) =>
    request<{ authorize_url: string | null }>(
      `/connectors/auth/${kind}/authorize-url`,
    ),

  authInfo: (kind: string) =>
    request<ConnectorAuthInfo>(`/connectors/auth/${kind}/info`),

  exchangeAuthCode: (
    kind: string,
    body: { code: string; bkn?: string; knowledge_base_id?: string },
  ) =>
    request<{ credentials: Record<string, unknown> }>(
      `/connectors/auth/${kind}/exchange-code`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  testCredentials: (body: {
    kind: string;
    credentials: Record<string, unknown>;
  }) =>
    request<ConnectorProbeResult>("/connectors/test-credentials", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getCustomMcp: () =>
    request<{ servers: CustomMcpServers }>("/connectors/custom-mcp"),

  putCustomMcp: (servers: CustomMcpServers) =>
    request<{ servers: CustomMcpServers }>("/connectors/custom-mcp", {
      method: "PUT",
      body: JSON.stringify({ servers }),
    }),

  patchCustomMcpServer: (name: string, body: { enabled: boolean }) =>
    request<{ servers: CustomMcpServers }>(
      `/connectors/custom-mcp/servers/${encodeURIComponent(name)}`,
      {
        method: "PATCH",
        body: JSON.stringify(body),
      },
    ),

  testCustomMcp: (body: { name?: string; server?: CustomMcpServerSpec }) =>
    request<ConnectorProbeResult>("/connectors/custom-mcp/test", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
