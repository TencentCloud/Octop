import { readNumber } from "./readNumber";

export const AGENT_RUNTIME_NUMBER_KEYS = [
  "max_iters",
  "max_input_length",
  "temperature",
  "top_p",
  "max_tokens",
  "tool_call_run_limit",
  "model_retry_max_retries",
  "model_retry_initial_delay",
  "model_retry_max_delay",
  "tool_retry_max_retries",
  "tool_retry_initial_delay",
  "tool_retry_max_delay",
] as const;

export const AGENT_RUNTIME_FLAG_KEYS = [
  "tool_call_limit_enabled",
  "model_retry_enabled",
  "tool_retry_enabled",
] as const;

export const AGENT_RUNTIME_CONFIG_KEYS = [
  ...AGENT_RUNTIME_NUMBER_KEYS,
  ...AGENT_RUNTIME_FLAG_KEYS,
] as const;

export type AgentRuntimeConfigKey = (typeof AGENT_RUNTIME_CONFIG_KEYS)[number];
export type AgentRuntimeNumberKey = (typeof AGENT_RUNTIME_NUMBER_KEYS)[number];
export type AgentRuntimeFlagKey = (typeof AGENT_RUNTIME_FLAG_KEYS)[number];

export type AgentRuntimeApiFields = Partial<
  Record<AgentRuntimeNumberKey, number | null>
> &
  Partial<Record<AgentRuntimeFlagKey, boolean | null>>;

export type AgentCompactionFormValues = {
  enabled?: boolean;
  trigger_fraction?: number | null;
  keep_fraction?: number | null;
  trim_tokens?: number | null;
};

export type AgentCompactionRequest = {
  enabled?: boolean | null;
  trigger_fraction?: number | null;
  keep_fraction?: number | null;
  trim_tokens?: number | null;
};

export type AgentRuntimeFormValues = Partial<
  Record<AgentRuntimeNumberKey, number | null>
> &
  Partial<Record<AgentRuntimeFlagKey, boolean>> & {
    compaction?: AgentCompactionFormValues;
  };
export type AgentRuntimeRequest = Partial<
  Record<AgentRuntimeNumberKey, number | null>
> &
  Partial<Record<AgentRuntimeFlagKey, boolean | null>> & {
    compaction?: AgentCompactionRequest | null;
  };

function readCompaction(value: unknown): AgentCompactionFormValues {
  const record =
    value && typeof value === "object"
      ? (value as Record<string, unknown>)
      : {};
  return {
    enabled: record.enabled !== false,
    trigger_fraction: readNumber(record.trigger_fraction) ?? null,
    keep_fraction: readNumber(record.keep_fraction) ?? null,
    trim_tokens: readNumber(record.trim_tokens) ?? null,
  };
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function compactionRequest(
  values: AgentRuntimeFormValues,
  clearMissing: boolean,
): AgentCompactionRequest | null | undefined {
  const current = values.compaction;
  if (!current && !clearMissing) return undefined;
  const enabled =
    typeof current?.enabled === "boolean" ? current.enabled : true;
  const trigger = finiteNumber(current?.trigger_fraction);
  const keep = finiteNumber(current?.keep_fraction);
  const trim = finiteNumber(current?.trim_tokens);
  if (!clearMissing) {
    const request: AgentCompactionRequest = {};
    if (enabled === false) request.enabled = false;
    if (trigger != null) request.trigger_fraction = trigger;
    if (keep != null) request.keep_fraction = keep;
    if (trim != null) request.trim_tokens = trim;
    return Object.keys(request).length > 0 ? request : undefined;
  }
  return {
    enabled,
    trigger_fraction: trigger,
    keep_fraction: keep,
    trim_tokens: trim,
  };
}

function readFlag(value: unknown): boolean {
  return value !== false;
}

export function readAgentRuntimeFormValues(
  cfg: object,
): AgentRuntimeFormValues {
  const record = cfg as Record<string, unknown>;
  const numbers = Object.fromEntries(
    AGENT_RUNTIME_NUMBER_KEYS.map((key) => [key, readNumber(record[key])]),
  ) as Record<AgentRuntimeNumberKey, number | undefined>;
  const flags = Object.fromEntries(
    AGENT_RUNTIME_FLAG_KEYS.map((key) => [key, readFlag(record[key])]),
  ) as Record<AgentRuntimeFlagKey, boolean>;
  return {
    ...numbers,
    ...flags,
    compaction: readCompaction(record.compaction),
  };
}

export function emptyAgentRuntimeFormValues(): AgentRuntimeFormValues {
  const numbers = Object.fromEntries(
    AGENT_RUNTIME_NUMBER_KEYS.map((key) => [key, null]),
  ) as Record<AgentRuntimeNumberKey, null>;
  const flags = Object.fromEntries(
    AGENT_RUNTIME_FLAG_KEYS.map((key) => [key, true]),
  ) as Record<AgentRuntimeFlagKey, boolean>;
  return {
    ...numbers,
    ...flags,
    compaction: {
      enabled: true,
      trigger_fraction: null,
      keep_fraction: null,
      trim_tokens: null,
    },
  };
}

export function buildAgentRuntimeRequest(
  values: AgentRuntimeFormValues,
  options?: { clearMissing?: boolean },
): AgentRuntimeRequest {
  const request: AgentRuntimeRequest = {};
  for (const key of AGENT_RUNTIME_NUMBER_KEYS) {
    const val = values[key];
    if (typeof val === "number" && Number.isFinite(val)) {
      request[key] = val;
    } else if (options?.clearMissing) {
      request[key] = null;
    }
  }
  for (const key of AGENT_RUNTIME_FLAG_KEYS) {
    if (values[key] === false) {
      request[key] = false;
    } else if (options?.clearMissing) {
      request[key] = null;
    }
  }
  const compaction = compactionRequest(values, options?.clearMissing === true);
  if (compaction !== undefined) request.compaction = compaction;
  return request;
}

export function omitAgentRuntimeConfig(
  config: Record<string, unknown>,
): Record<string, unknown> {
  const cleaned = { ...config };
  for (const key of AGENT_RUNTIME_CONFIG_KEYS) {
    delete cleaned[key];
  }
  delete cleaned.compaction;
  return cleaned;
}
