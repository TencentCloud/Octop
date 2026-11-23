import { request } from "../request";

export interface DatabaseConfigInput {
  driver: "sqlite" | "postgresql";
  sqlite_path: string;
  host: string;
  port: number;
  database: string;
  user: string;
  password?: string | null;
  url?: string | null;
}

export interface TlsConfigInput {
  enabled: boolean;
  mode: string;
  domains: string[];
  cert_file: string;
  key_file: string;
  issued_at: string;
  expires_at: string;
  acme_staging: boolean;
  http_port: number;
}

export interface AppConfigInput {
  bind_host: string;
  port: number;
  log_level: string;
  access_token_ttl_seconds: number;
  login_max_attempts: number;
  login_lockout_seconds: number;
  cors_origins: string[];
  default_timezone: string;
  enable_dashboard: boolean;
  enable_api_docs: boolean;
  require_setup_password: boolean;
  max_upload_mb: number;
  database: DatabaseConfigInput;
  tls: TlsConfigInput;
}

export interface AppConfigView {
  path: string;
  raw: string;
  valid: boolean;
  error: string | null;
  config: AppConfigInput | null;
  has_database_password: boolean;
  overrides: string[];
  service_mode: string | null;
  restart_available: boolean;
}

export const appConfigApi = {
  get: () => request<AppConfigView>("/admin/app-config"),
  save: (body: AppConfigInput) =>
    request<AppConfigView>("/admin/app-config", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  saveRaw: (raw: string) =>
    request<AppConfigView>("/admin/app-config/raw", {
      method: "PUT",
      body: JSON.stringify({ raw }),
    }),
};
