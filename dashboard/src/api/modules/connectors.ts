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
  credential_fields?: ConnectorCredentialField[];
}

export interface ConnectorCredentialField {
  key: string;
  label: string;
  field_type: "text" | "password" | "url" | "tags";
  required: boolean;
  placeholder?: string | null;
  help?: string | null;
  secret: boolean;
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
  /** When true, chat composer pre-selects this connector. */
  default_open?: boolean;
  created_at: number;
  updated_at: number;
}

export interface ConnectorCredentialsPreview {
  [key: string]: unknown;
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
  bot_id?: string;
  app_secret_configured?: boolean;
  bot_secret_configured?: boolean;
  default_as?: string;
  user_auth_configured?: boolean;
  user_auth_valid?: boolean;
  user_auth_needs_reauth?: boolean;
  user_token_status?: string | null;
  user_token_expires_at?: string | null;
  user_refresh_expires_at?: string | null;
  search_docs_scope?: boolean;
  cli_config_key?: string;
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
  error_type?: string;
  status_code?: number;
  oauth?: {
    available: boolean;
    issuer?: string;
    resource?: string;
  };
}

export interface WeKnoraLocalDetection {
  found: boolean;
  base_url?: string;
  console_url?: string;
}

export type CustomMcpTransport = "streamable_http" | "stdio";

export interface CustomMcpOAuthPreview {
  configured?: boolean;
  required?: boolean;
  expires_at?: number;
}

export interface CustomMcpServerSpec {
  transport: CustomMcpTransport;
  url?: string;
  headers?: Record<string, string>;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  enabled?: boolean;
  /** Friendly label shown in chat / connector lists (optional). */
  display_name?: string;
  /** When true, chat composer pre-selects this MCP server. */
  default_open?: boolean;
  oauth?: CustomMcpOAuthPreview;
}

export type OAuthStartTarget =
  | { type: "catalog"; kind: string }
  | { type: "custom_mcp"; server_name: string };

export type CustomMcpServers = Record<string, CustomMcpServerSpec>;

export interface ConnectorCliInstallResult {
  ok: boolean;
  already_installed?: boolean;
  kind: string;
  binary: string;
  npm_package: string;
  install_command: string;
  doc_url: string;
  guide_url?: string | null;
  installed: boolean;
  binary_path?: string | null;
  version?: string | null;
  error?: string;
}

export interface FeishuUserAuthStartResult {
  device_code: string;
  verification_url: string;
  expires_in?: number | null;
  user_code?: string | null;
  hint?: string | null;
  cli_config_key: string;
}

export interface FeishuUserAuthCompleteResult {
  ok: boolean;
  identity: string;
  default_as: string;
  user_available: boolean;
  bot_available?: boolean;
  search_docs_scope?: boolean;
  warning?: string | null;
  cli_config_key: string;
}

export const connectorsApi = {
  catalog: () => request<ConnectorCatalogEntry[]>("/connectors/catalog"),

  detectLocalWeKnora: () =>
    request<WeKnoraLocalDetection>("/connectors/weknora/detect-local"),

  listInstances: () => request<ConnectorInstance[]>("/connector-instances"),

  getInstance: (instanceId: string) =>
    request<ConnectorInstanceDetail>(
      `/connector-instances/${encodeURIComponent(instanceId)}`,
    ),

  createInstance: (body: {
    kind: string;
    display_name: string;
    credentials: Record<string, unknown>;
    default_open?: boolean;
  }) =>
    request<ConnectorInstance>("/connector-instances", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  deleteInstance: (instanceId: string) =>
    request<void>(`/connector-instances/${encodeURIComponent(instanceId)}`, {
      method: "DELETE",
    }),

  patchInstance: (
    instanceId: string,
    body: { status?: "active" | "disabled"; default_open?: boolean },
  ) =>
    request<ConnectorInstance>(
      `/connector-instances/${encodeURIComponent(instanceId)}`,
      {
        method: "PATCH",
        body: JSON.stringify(body),
      },
    ),

  testInstance: (instanceId: string) =>
    request<ConnectorProbeResult>(
      `/connector-instances/${encodeURIComponent(instanceId)}/test`,
      {
        method: "POST",
      },
    ),

  oauthStart: (target: OAuthStartTarget, redirectAfter?: string) =>
    request<{ authorize_url: string; state_id: string }>(
      "/connectors/oauth/start",
      {
        method: "POST",
        body: JSON.stringify({ target, redirect_after: redirectAfter }),
      },
    ),

  /** @deprecated Prefer oauthStart with `{ type: "catalog", kind }`. */
  oauthStartCatalog: (kind: string, redirectAfter?: string) =>
    request<{ authorize_url: string; state_id: string }>(
      `/connectors/oauth/${kind}/start`,
      {
        method: "POST",
        body: JSON.stringify({ redirect_after: redirectAfter }),
      },
    ),

  oauthPending: (stateId: string) =>
    request<{
      kind: string;
      tokens: Record<string, unknown>;
      server_name?: string;
      applied?: boolean;
    }>(`/connectors/oauth/pending/${stateId}`),

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

  cliStatus: (kind: string) =>
    request<ConnectorCliInstallResult>(
      `/connectors/${encodeURIComponent(kind)}/cli-status`,
    ),

  installCli: (kind: string) =>
    request<ConnectorCliInstallResult>(
      `/connectors/${encodeURIComponent(kind)}/install-cli`,
      { method: "POST" },
    ),

  feishuUserAuthStart: (body: {
    app_id: string;
    app_secret: string;
    cli_config_key?: string;
    domains?: string[];
  }) =>
    request<FeishuUserAuthStartResult>(
      "/connectors/feishu-cli/user-auth/start",
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),

  feishuUserAuthComplete: (body: {
    app_id: string;
    app_secret: string;
    device_code: string;
    cli_config_key: string;
  }) =>
    request<FeishuUserAuthCompleteResult>(
      "/connectors/feishu-cli/user-auth/complete",
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),

  feishuUserAuthStartInstance: (instanceId: string) =>
    request<FeishuUserAuthStartResult>(
      `/connector-instances/${encodeURIComponent(
        instanceId,
      )}/feishu-user-auth/start`,
      { method: "POST" },
    ),

  feishuUserAuthCompleteInstance: (
    instanceId: string,
    body: { device_code: string; cli_config_key?: string },
  ) =>
    request<FeishuUserAuthCompleteResult>(
      `/connector-instances/${encodeURIComponent(
        instanceId,
      )}/feishu-user-auth/complete`,
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),

  getCustomMcp: () =>
    request<{ servers: CustomMcpServers }>("/connectors/custom-mcp"),

  putCustomMcp: (servers: CustomMcpServers) =>
    request<{ servers: CustomMcpServers }>("/connectors/custom-mcp", {
      method: "PUT",
      body: JSON.stringify({ servers }),
    }),

  patchCustomMcpServer: (
    name: string,
    body: { enabled?: boolean; default_open?: boolean },
  ) =>
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
