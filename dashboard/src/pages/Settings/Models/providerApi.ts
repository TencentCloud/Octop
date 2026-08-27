import { request } from "../../../api/request";
import type { ProviderModel } from "./useProviders";

export type ProviderProbeModel = Omit<ProviderModel, "max_tokens"> & {
  max_output_tokens?: number;
};

/** Convert the persisted model shape into the metadata shape used by probes. */
export function toProviderProbeModel(model: ProviderModel): ProviderProbeModel {
  const { max_tokens, ...probeModel } = model;
  return {
    ...probeModel,
    ...(probeModel.max_output_tokens != null || max_tokens == null
      ? {}
      : { max_output_tokens: max_tokens }),
  };
}

export interface TestProviderDraftParams {
  name: string;
  kind: string;
  api_key?: string;
  base_url?: string | null;
  model_id: string;
  model: ProviderProbeModel;
  extra_json?: string | null;
  embedding?: boolean;
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
      model: params.model,
      extra_json: params.extra_json ?? null,
      embedding: params.embedding === true,
    }),
  });
}

export interface FetchProviderModelsParams {
  kind: string;
  api_key?: string;
  base_url?: string | null;
  extra_json?: string | null;
}

export interface FetchedProviderModel {
  id: string;
  name: string;
}

export interface FetchProviderModelsResult {
  ok: boolean;
  models?: FetchedProviderModel[];
  error?: string;
}

export async function fetchProviderModels(
  params: FetchProviderModelsParams,
): Promise<FetchProviderModelsResult> {
  return request<FetchProviderModelsResult>("/admin/providers/fetch-models", {
    method: "POST",
    body: JSON.stringify({
      kind: params.kind,
      api_key: params.api_key?.trim() || null,
      base_url: params.base_url?.trim() || null,
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
