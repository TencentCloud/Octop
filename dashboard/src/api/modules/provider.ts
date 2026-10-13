import { bridgeAgentHeaders, request } from "../request";
import type {
  ProviderInfo,
  ProviderConfigRequest,
  ActiveModelsInfo,
  ModelSlotRequest,
  CreateCustomProviderRequest,
  AddModelRequest,
  ModelCost,
  ResolvedModel,
  TestModelResponse,
  TestModelDirectRequest,
  TestSearchResponse,
} from "../types";

export interface ModelTemplate {
  contextWindow?: number;
  maxTokens?: number;
  reasoning?: boolean;
  input?: string[];
  cost?: ModelCost;
}

export const providerApi = {
  listProviders: () => request<ProviderInfo[]>("/models"),

  listResolvedModels: (agentId?: string | null) =>
    request<ResolvedModel[]>("/providers/resolved", {
      headers: bridgeAgentHeaders(agentId),
    }),

  getActiveModel: (agentId?: string | null) =>
    request<{ provider_name: string; model: string }>(
      "/providers/active-model",
      { headers: bridgeAgentHeaders(agentId) },
    ),

  configureProvider: (providerId: string, body: ProviderConfigRequest) =>
    request<ProviderInfo>(`/models/${encodeURIComponent(providerId)}/config`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  getActiveModels: () => request<ActiveModelsInfo>("/models/active"),

  setActiveLlm: (body: ModelSlotRequest) =>
    request<ActiveModelsInfo>("/models/active", {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  /* ---- Bundled model metadata templates ---- */

  getModelTemplate: (providerId: string, modelId: string) =>
    request<ModelTemplate>(
      `/models/${encodeURIComponent(providerId)}/models/${encodeURIComponent(
        modelId,
      )}/template`,
    ).catch(() => null as ModelTemplate | null), // 404 is expected when no template exists

  /* ---- Custom provider CRUD ---- */

  createCustomProvider: (body: CreateCustomProviderRequest) =>
    request<ProviderInfo>("/models/custom-providers", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  deleteCustomProvider: (providerId: string) =>
    request<ProviderInfo[]>(
      `/models/custom-providers/${encodeURIComponent(providerId)}`,
      { method: "DELETE" },
    ),

  /* ---- Model CRUD (works for both built-in and custom providers) ---- */

  addModel: (providerId: string, body: AddModelRequest) =>
    request<ProviderInfo>(`/models/${encodeURIComponent(providerId)}/models`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  removeModel: (providerId: string, modelId: string) =>
    request<ProviderInfo>(
      `/models/${encodeURIComponent(providerId)}/models/${encodeURIComponent(
        modelId,
      )}`,
      { method: "DELETE" },
    ),

  toggleModelEnabled: (providerId: string, modelId: string, enabled: boolean) =>
    request<ProviderInfo>(
      `/models/${encodeURIComponent(providerId)}/models/${encodeURIComponent(
        modelId,
      )}/enabled`,
      {
        method: "PUT",
        body: JSON.stringify({ enabled }),
      },
    ),

  /* ---- Test model connectivity ---- */

  testModel: (providerId: string, modelId?: string) =>
    request<TestModelResponse>(
      `/models/${encodeURIComponent(providerId)}/test`,
      {
        method: "POST",
        body: JSON.stringify(modelId ? { model_id: modelId } : {}),
      },
    ),

  testModelDirect: (params: TestModelDirectRequest) =>
    request<TestModelResponse>(`/models/test-direct`, {
      method: "POST",
      body: JSON.stringify(params),
    }),

  /* ---- Test search connectivity ---- */

  testSearch: (providerId: string, envVars: Record<string, string>) =>
    request<TestSearchResponse>(
      `/search/${encodeURIComponent(providerId)}/test`,
      {
        method: "POST",
        body: JSON.stringify({ env_vars: envVars }),
      },
    ),
};
