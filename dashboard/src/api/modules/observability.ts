import { request } from "../request";

export interface LangfuseConfig {
  enabled: boolean;
  public_key: string;
  host: string;
  secret_key_set: boolean;
  configured: boolean;
}

export interface ClsTopicItem {
  topic_id: string;
  flag: string;
}

export interface ClsApplicationItem {
  application_id: string;
  application_name: string;
  access_type: string;
  region: string;
  topic_id: string;
  logset_id: string;
  log_topics: ClsTopicItem[];
  created: boolean;
}

export interface ClsConfig {
  enabled: boolean;
  region: string;
  topic_id: string;
  application_id: string;
  application_name: string;
  access_type: string;
  use_internal_endpoint: boolean;
  mask_content: boolean;
  secret_id_masked: string;
  secret_id_set: boolean;
  secret_key_set: boolean;
  configured: boolean;
  endpoint: string;
  active_backend: "cls" | "langfuse" | "cls_env" | "none" | string;
  application_created?: boolean;
}

export interface ClsSavePayload {
  enabled: boolean;
  region: string;
  topic_id?: string;
  application_id?: string;
  application_name?: string;
  access_type?: string;
  use_internal_endpoint?: boolean;
  mask_content?: boolean;
  secret_id?: string | null;
  secret_key?: string | null;
  auto_create_app?: boolean;
  logset_id?: string | null;
  reuse_existing?: boolean;
}

export interface ClsTestResult {
  ok: boolean;
  error?: string;
  api_ok?: boolean | null;
  otlp_ok?: boolean | null;
  endpoint?: string;
}

export const observabilityApi = {
  getLangfuse: () => request<LangfuseConfig>("/admin/observability/langfuse"),
  saveLangfuse: (body: {
    enabled: boolean;
    public_key: string;
    host: string;
    secret_key?: string | null;
  }) =>
    request<LangfuseConfig>("/admin/observability/langfuse", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  testLangfuse: (body?: {
    public_key?: string | null;
    host?: string | null;
    secret_key?: string | null;
  }) =>
    request<{ ok: boolean; error?: string }>(
      "/admin/observability/langfuse/test",
      {
        method: "POST",
        body: JSON.stringify(body ?? {}),
      },
    ),

  getCls: () => request<ClsConfig>("/admin/observability/cls"),
  saveCls: (body: ClsSavePayload) =>
    request<ClsConfig>("/admin/observability/cls", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  listClsApplications: (body?: {
    region?: string | null;
    access_type?: string | null;
    application_name?: string | null;
    secret_id?: string | null;
    secret_key?: string | null;
  }) =>
    request<{ applications: ClsApplicationItem[] }>(
      "/admin/observability/cls/applications/list",
      {
        method: "POST",
        body: JSON.stringify(body ?? {}),
      },
    ),
  createClsApplication: (body: {
    region?: string | null;
    application_name: string;
    access_type?: string;
    logset_id?: string | null;
    reuse_existing?: boolean;
    secret_id?: string | null;
    secret_key?: string | null;
  }) =>
    request<ClsApplicationItem>("/admin/observability/cls/applications", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  testCls: (body?: {
    region?: string | null;
    topic_id?: string | null;
    use_internal_endpoint?: boolean | null;
    secret_id?: string | null;
    secret_key?: string | null;
  }) =>
    request<ClsTestResult>("/admin/observability/cls/test", {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    }),
};
