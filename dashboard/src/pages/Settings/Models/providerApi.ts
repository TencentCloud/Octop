import { request } from "../../../api/request";

export interface TestProviderDraftParams {
  name: string;
  kind: string;
  api_key?: string;
  base_url?: string | null;
  model_id: string;
  extra_json?: string | null;
}

export interface TestProviderResult {
  ok: boolean;
  latency_ms?: number;
  error?: string;
}

export async function testProviderDraft(
  params: TestProviderDraftParams,
): Promise<TestProviderResult> {
  return request<TestProviderResult>("/admin/providers/test-draft", {
    method: "POST",
    body: JSON.stringify({
      name: params.name,
      kind: params.kind,
      api_key: params.api_key?.trim() || null,
      base_url: params.base_url?.trim() || null,
      model_id: params.model_id,
      extra_json: params.extra_json ?? null,
    }),
  });
}

export async function startCodexOAuth() {
  return request<{
    state_id: string;
    user_code: string;
    verification_url: string;
  }>("/admin/providers/codex-oauth/start", { method: "POST" });
}

export async function pollCodexOAuth(stateId: string) {
  return request<{
    status: string;
    error?: string;
    provider_id?: number;
    provider_name?: string;
  }>(`/admin/providers/codex-oauth/pending/${encodeURIComponent(stateId)}`);
}
