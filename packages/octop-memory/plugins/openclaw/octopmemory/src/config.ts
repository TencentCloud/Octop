export type OctopMemoryProfile = "balanced" | "low_latency" | "proactive" | "privacy" | "archive" | "eval";
export type RecallMode = "off" | "tool_hint" | "hybrid";
export type DefaultCorpus = "all" | "memory" | "sessions" | "wiki";
export type RawPolicy = "never" | "fallback" | "always";
export type HostFilesPolicy = "off" | "include" | "only";
export type CitationPolicy = "off" | "auto" | "always";
export type CaptureRole = "user" | "assistant" | "tool";
export type LayerName = "atom" | "host_file" | "page" | "raw";
export type MemoryBackend = "sqlite" | "postgres";

export interface RecallConfig {
  mode?: RecallMode;
  default_max_results?: number;
  default_corpus?: DefaultCorpus;
  raw_policy?: RawPolicy;
  host_files_policy?: HostFilesPolicy;
  citation_policy?: CitationPolicy;
  max_prompt_chars?: number;
  layer_order?: LayerName[];
  /** Legacy alias kept for v0.2 compatibility. Prefer default_max_results. */
  limit?: number;
  /** Legacy soft cap kept for v0.2 compatibility. Prefer max_prompt_chars. */
  total_chars?: number;
}

export interface CaptureConfig {
  agent_end_hook?: boolean;
  host_files_watcher?: boolean;
  min_message_chars?: number;
  include_roles?: CaptureRole[];
  include_tool_calls?: boolean;
  include_tool_results?: boolean;
  skip_memory_echo?: boolean;
  /**
   * Trigger bridge `extract` (L0→L1 candidate extraction + promotion +
   * page regen) after each agent_end capture. Only takes effect when
   * `llm.endpoint` is configured — without an LLM the bridge can't
   * extract anyway. The bridge tracks already-extracted events per
   * session, so repeat triggers on a quiet session are no-ops.
   */
  extract_on_agent_end?: boolean;
}

/**
 * OpenAI-compatible endpoint the Python bridge uses for extraction /
 * promotion escalation / page regen. Forwarded verbatim inside
 * `--config-json`. Prefer `api_key_env` (an env var name, default
 * OCTOPMEMORY_LLM_API_KEY) over inline `api_key`: the config JSON is
 * passed via argv and shows up in process listings.
 */
export interface LlmConfig {
  endpoint?: string;
  model?: string;
  /** Stronger model for heavy-tier work (page regen). Defaults to `model`. */
  model_heavy?: string;
  api_key?: string;
  api_key_env?: string;
  timeout_seconds?: number;
  max_retries?: number;
}

/** Knobs for the bridge `extract` pipeline. Forwarded inside `--config-json`. */
export interface ExtractionConfig {
  promote?: boolean;
  regen_pages?: boolean;
  max_candidates?: number;
  page_regen_limit?: number;
}

export interface PrivacyConfig {
  redact_secrets?: boolean;
  redact_patterns?: string[];
  store_raw_content?: boolean;
  store_tool_payloads?: boolean;
}

export interface CompactionConfig {
  enabled?: boolean;
  soft_threshold_tokens?: number;
  force_flush_transcript_bytes?: number;
  model?: string;
  host_file_index_after_flush?: boolean;
}

export interface BridgeConfig {
  /**
   * Explicit `octopmemory-bridge` console-script path (preferred).
   * Set by `setup` from the resolved uv/pipx tool env. When present it
   * is spawned directly; `python` is ignored.
   */
  command?: string;
  python?: string;
  log_level?: "debug" | "info" | "warning" | "error";
  spawn_timeout_ms?: number;
}

export interface OctopMemoryPluginConfig {
  profile?: OctopMemoryProfile;
  mode?: "self-hosted";
  /**
   * Memory storage backend (default: sqlite). Postgres requires the
   * connection string to be set via the `OCTOP_MEMORY_DSN` environment
   * variable in the process that spawns this plugin — never put a DSN
   * (which embeds a password) here, it would be forwarded to the bridge
   * subprocess via argv/config-json and show up in process listings.
   */
  backend?: MemoryBackend;
  db_path?: string;
  namespace?: string;
  host_files_root?: string;
  host_files_allow?: string[];
  bridge?: BridgeConfig;
  recall?: RecallConfig;
  capture?: CaptureConfig;
  privacy?: PrivacyConfig;
  compaction?: CompactionConfig;
  llm?: LlmConfig;
  extraction?: ExtractionConfig;
}

export interface EffectiveOctopMemoryConfig extends Required<Pick<OctopMemoryPluginConfig, "profile" | "mode">> {
  backend: MemoryBackend;
  db_path?: string;
  namespace?: string;
  host_files_root?: string;
  host_files_allow: string[];
  bridge: BridgeConfig;
  recall: Required<Omit<RecallConfig, "limit" | "total_chars">> & Pick<RecallConfig, "limit" | "total_chars">;
  capture: Required<CaptureConfig>;
  privacy: Required<PrivacyConfig>;
  compaction: Required<CompactionConfig>;
  llm?: LlmConfig;
  extraction?: ExtractionConfig;
}

type ProfileDefaults = Omit<
  EffectiveOctopMemoryConfig,
  "profile" | "backend" | "db_path" | "namespace" | "host_files_root"
>;
type DeepPartial<T> = {
  [K in keyof T]?: T[K] extends Array<infer U>
    ? U[]
    : T[K] extends Record<string, unknown>
      ? DeepPartial<T[K]>
      : T[K];
};

const BALANCED_DEFAULTS: ProfileDefaults = {
  mode: "self-hosted",
  host_files_allow: ["topics/*.md", "projects/*.md"],
  bridge: {
    python: "python3",
    log_level: "info",
    spawn_timeout_ms: 5000,
  },
  recall: {
    mode: "tool_hint",
    default_max_results: 5,
    default_corpus: "all",
    raw_policy: "fallback",
    host_files_policy: "include",
    citation_policy: "auto",
    max_prompt_chars: 1200,
    layer_order: ["atom", "host_file", "page", "raw"],
  },
  capture: {
    agent_end_hook: true,
    host_files_watcher: true,
    min_message_chars: 50,
    include_roles: ["user", "assistant"],
    include_tool_calls: false,
    include_tool_results: false,
    skip_memory_echo: true,
    extract_on_agent_end: true,
  },
  privacy: {
    redact_secrets: true,
    redact_patterns: [],
    store_raw_content: true,
    store_tool_payloads: false,
  },
  compaction: {
    enabled: true,
    soft_threshold_tokens: 4000,
    force_flush_transcript_bytes: 2 * 1024 * 1024,
    model: "",
    host_file_index_after_flush: true,
  },
};

const PROFILE_OVERRIDES: Record<OctopMemoryProfile, DeepPartial<ProfileDefaults>> = {
  balanced: {},
  low_latency: {
    recall: {
      mode: "tool_hint",
      default_max_results: 3,
      default_corpus: "memory",
      raw_policy: "never",
      host_files_policy: "off",
      citation_policy: "off",
      max_prompt_chars: 400,
      layer_order: ["atom", "page"],
    },
    capture: {
      agent_end_hook: true,
      host_files_watcher: false,
      min_message_chars: 100,
      include_roles: ["user"],
      include_tool_calls: false,
      include_tool_results: false,
      skip_memory_echo: true,
    },
    compaction: { enabled: false },
  },
  proactive: {
    recall: {
      mode: "hybrid",
      default_max_results: 5,
      default_corpus: "all",
      raw_policy: "fallback",
      host_files_policy: "include",
      citation_policy: "always",
      max_prompt_chars: 1200,
      layer_order: ["atom", "host_file", "page", "raw"],
    },
    capture: { min_message_chars: 30 },
  },
  privacy: {
    recall: {
      mode: "tool_hint",
      default_max_results: 5,
      default_corpus: "memory",
      raw_policy: "never",
      host_files_policy: "off",
      citation_policy: "off",
      max_prompt_chars: 800,
      layer_order: ["atom", "page"],
    },
    capture: {
      agent_end_hook: true,
      host_files_watcher: false,
      min_message_chars: 120,
      include_roles: ["user"],
      include_tool_calls: false,
      include_tool_results: false,
      skip_memory_echo: true,
    },
    privacy: {
      redact_secrets: true,
      store_raw_content: false,
      store_tool_payloads: false,
    },
  },
  archive: {
    recall: {
      mode: "tool_hint",
      default_max_results: 10,
      default_corpus: "all",
      raw_policy: "always",
      host_files_policy: "include",
      citation_policy: "always",
      max_prompt_chars: 2000,
      layer_order: ["atom", "raw", "host_file", "page"],
    },
    capture: {
      agent_end_hook: true,
      host_files_watcher: true,
      min_message_chars: 0,
      include_roles: ["user", "assistant", "tool"],
      include_tool_calls: true,
      include_tool_results: true,
      skip_memory_echo: true,
    },
    compaction: {
      enabled: true,
      soft_threshold_tokens: 3000,
      host_file_index_after_flush: true,
    },
  },
  eval: {
    recall: {
      mode: "tool_hint",
      default_max_results: 5,
      default_corpus: "all",
      raw_policy: "fallback",
      host_files_policy: "include",
      citation_policy: "always",
      max_prompt_chars: 1200,
      layer_order: ["atom", "page", "raw", "host_file"],
    },
    capture: {
      agent_end_hook: true,
      host_files_watcher: true,
      min_message_chars: 0,
      include_roles: ["user", "assistant"],
      include_tool_calls: false,
      include_tool_results: false,
      skip_memory_echo: true,
    },
  },
};

export const PROFILE_NAMES = Object.freeze(Object.keys(PROFILE_OVERRIDES) as OctopMemoryProfile[]);

export function resolveEffectiveConfig(input: OctopMemoryPluginConfig = {}): EffectiveOctopMemoryConfig {
  const profile = input.profile ?? "balanced";
  const profileDefaults = deepMerge(BALANCED_DEFAULTS, PROFILE_OVERRIDES[profile] ?? {});
  const merged = deepMerge(profileDefaults, stripUndefined(input) as DeepPartial<ProfileDefaults>);

  return {
    ...merged,
    profile,
    mode: merged.mode ?? "self-hosted",
    backend: input.backend ?? "sqlite",
    bridge: merged.bridge ?? {},
    recall: merged.recall,
    capture: merged.capture,
    privacy: merged.privacy,
    compaction: merged.compaction,
  } as EffectiveOctopMemoryConfig;
}

function deepMerge<T>(base: T, override: DeepPartial<T>): T {
  if (!isPlainObject(base) || !isPlainObject(override)) {
    return (override === undefined ? base : override) as T;
  }

  const out: Record<string, unknown> = { ...(base as Record<string, unknown>) };
  for (const [key, value] of Object.entries(override)) {
    if (value === undefined) continue;
    const previous = out[key];
    out[key] = isPlainObject(previous) && isPlainObject(value) ? deepMerge(previous, value) : value;
  }
  return out as T;
}

function stripUndefined<T>(value: T): T {
  if (Array.isArray(value) || !isPlainObject(value)) {
    return value;
  }
  const out: Record<string, unknown> = {};
  for (const [key, child] of Object.entries(value)) {
    if (child === undefined) continue;
    out[key] = stripUndefined(child);
  }
  return out as T;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
