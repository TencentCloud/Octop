export interface ModelCost {
  input?: number;
  output?: number;
  cacheRead?: number;
  cacheWrite?: number;
}

export interface ModelInfo {
  id: string;
  name: string;
  enabled?: boolean;
  // Optional extended metadata (openclaw-compatible)
  context_window?: number;
  max_tokens?: number;
  reasoning?: boolean;
  reasoning_config?: ReasoningCapability | null;
  input?: string[];
  cost?: ModelCost;
}

export interface ReasoningCapability {
  supported: boolean;
  toggle: boolean;
  default_mode: "auto" | "enabled" | "disabled";
  efforts: string[];
  default_effort?: string | null;
  effort_type: "enum" | "token_budget";
  adapter:
    | "status_only"
    | "thinking"
    | "thinking_nested_effort"
    | "openai_reasoning_effort"
    | "anthropic_adaptive"
    | "anthropic_budget"
    | "dashscope"
    | "openrouter";
}

export interface ProviderInfo {
  id: string;
  name: string;
  api_key_prefix: string;
  /** Built-in models (for built-in providers) or all models (for custom). */
  models: ModelInfo[];
  /** User-added models (deletable). Only populated for built-in providers. */
  extra_models: ModelInfo[];
  is_custom: boolean;
  has_api_key: boolean;
  current_api_key: string;
  current_base_url: string;
  current_headers: Record<string, string>;
  current_auth_header: boolean;
  current_request?: ProviderRequestConfig;
  current_api: string;
  thinking?: boolean | null;
}

export interface ProviderRequestConfig {
  headers?: Record<string, string>;
}

export interface ProviderConfigRequest {
  api_key?: string;
  base_url?: string;
  headers?: Record<string, string>;
  authHeader?: boolean;
  request?: ProviderRequestConfig;
  apiProtocol?: string;
  thinking?: boolean | null;
}

export interface ModelSlotConfig {
  provider_id: string;
  model: string;
}

export interface ActiveModelsInfo {
  active_llm: ModelSlotConfig;
}

export interface ModelSlotRequest {
  provider_id: string;
  model: string;
}

/* ---- Custom provider CRUD ---- */

export interface CreateCustomProviderRequest {
  id: string;
  name: string;
  default_base_url?: string;
  api_key_prefix?: string;
  api_key?: string;
  models?: ModelInfo[];
  apiProtocol?: string;
}

export interface AddModelRequest {
  id: string;
  name: string;
  // Advanced / optional metadata
  context_window?: number;
  max_tokens?: number;
  reasoning?: boolean;
  input?: string[];
  cost?: ModelCost;
}

/* ---- Resolved models (auto-routing candidates) ---- */

export interface ResolvedModel {
  provider_id: number;
  provider_name: string;
  provider_kind: string;
  model: string;
  name: string;
  context_window?: number | null;
  max_tokens?: number | null;
  max_input_tokens?: number | null;
  reasoning?: boolean | null;
  reasoning_config?: ReasoningCapability | null;
  input?: string[];
  /** @deprecated use context_window */
  contextWindow?: number;
}

/* ---- Ollama models ---- */

export interface OllamaModelResponse {
  name: string;
  size: number;
  digest?: string | null;
  modified_at?: string | null;
}

export interface OllamaDownloadRequest {
  name: string;
}

/* ---- Test model connectivity ---- */

export interface TestModelResponse {
  success: boolean;
  provider_id: string;
  model_id?: string | null;
  response_time_ms: number;
  message?: string;
  error?: string;
  error_type?: string; // "auth_error" | "timeout" | "network_error" | "model_not_found" | "no_enabled_model" | "unknown"
}

export interface TestModelDirectRequest {
  base_url: string;
  api_key?: string;
  model_id: string;
  headers?: Record<string, string>;
}

export interface OllamaDownloadTaskResponse {
  task_id: string;
  status: "pending" | "downloading" | "completed" | "failed" | "cancelled";
  name: string;
  error: string | null;
  result: OllamaModelResponse | null;
}

/* ---- Test search connectivity ---- */

export interface TestSearchResponse {
  success: boolean;
  provider_id: string;
  response_time_ms: number;
  result_count?: number;
  message?: string;
  error?: string;
  error_type?: string; // "auth_error" | "timeout" | "network_error" | "invalid_config" | "unknown"
}
