// Local type stubs for the OpenClaw plugin SDK.
//
// In a real install these come from `openclaw/plugin-sdk/*` peer-dep
// resolution. We mirror only the surface our plugin uses, narrowed to
// concrete types. Where the SDK is `unknown`, we keep `unknown` —
// runtime calls flow through to the real SDK.
//
// Source-of-truth signatures verified against:
// - extensions/memory-core/index.ts                (registerMemoryCapability + registerTool + registerCli)
// - extensions/memory-core/src/prompt-section.ts   (MemoryPromptSectionBuilder shape)
// - extensions/memory-core/src/flush-plan.ts       (MemoryFlushPlan shape)
// - https://docs.openclaw.ai/plugins/sdk-overview  (OpenClawPluginApi members)

export interface OpenClawConfig {
  agents?: {
    defaults?: {
      compaction?: {
        memoryFlush?: {
          enabled?: boolean;
          softThresholdTokens?: number;
          forceFlushTranscriptBytes?: number | string;
          model?: string;
          prompt?: string;
          systemPrompt?: string;
        };
        reserveTokensFloor?: number;
      };
    };
  };
}

export type CitationsMode = "off" | "on" | "auto";

export interface MemoryPromptMessage {
  role?: string;
  content?: string;
}

export interface MemoryPromptRecallResult {
  path?: string;
  layer?: string;
  title?: string;
  snippet?: string;
  excerpt?: string;
  text?: string;
  score?: number;
  source_id?: string;
  metadata?: Record<string, unknown>;
}

export interface MemoryPromptBuilderCtx {
  availableTools: Set<string>;
  citationsMode: CitationsMode;
  /**
   * Optional query-aware context for future host SDKs. Older OpenClaw
   * builds only pass tool/citation metadata; prompt builders must treat
   * these fields as best-effort and stay compatible when they are absent.
   */
  query?: string;
  latestUserMessage?: string;
  threadId?: string;
  sessionId?: string;
  userId?: string;
  agentId?: string;
  recentMessages?: MemoryPromptMessage[];
  /**
   * Optional prefetch results produced by the host before the synchronous
   * promptBuilder runs. This is the compatibility path for auto-recall
   * without requiring promptBuilder itself to await the Python bridge.
   */
  recallResults?: MemoryPromptRecallResult[];
}

export type MemoryPromptSectionBuilder = (ctx: MemoryPromptBuilderCtx) => string[];

/**
 * Optional async prefetch hook for hosts that can run memory work before
 * calling the synchronous promptBuilder. Older OpenClaw builds may ignore
 * this property and continue to rely on the memory_search tool path.
 */
export type MemoryRecallPrefetcher = (ctx: MemoryPromptBuilderCtx) => Promise<MemoryPromptRecallResult[]>;

export interface MemoryFlushPlan {
  softThresholdTokens: number;
  forceFlushTranscriptBytes: number;
  reserveTokensFloor: number;
  model?: string;
  prompt: string;
  systemPrompt: string;
  relativePath: string;
}

export type MemoryFlushPlanResolver = (
  params: { cfg?: OpenClawConfig; nowMs?: number },
) => MemoryFlushPlan | null;

export interface MemoryRuntimeShape {
  // The host calls these to lazily build a search/get manager. We
  // delegate to the Python bridge instead, but the surface is opaque
  // to OpenClaw — it only invokes our promptBuilder + tools.
  // Using `unknown` here keeps us forward-compatible with SDK changes.
  [key: string]: unknown;
}

export interface RegisterMemoryCapabilityOptions {
  promptBuilder: MemoryPromptSectionBuilder;
  recallPrefetcher?: MemoryRecallPrefetcher;
  flushPlanResolver: MemoryFlushPlanResolver;
  runtime?: MemoryRuntimeShape;
  publicArtifacts?: {
    listArtifacts?: (params: unknown) => Promise<unknown>;
  };
}

export interface ToolJsonSchema {
  type: "object";
  properties: Record<string, unknown>;
  required?: string[];
  additionalProperties?: boolean;
}

export interface AnyAgentTool {
  label: string;
  name: string;
  description: string;
  parameters: ToolJsonSchema;
  execute: (
    toolCallId: string,
    params: Record<string, unknown>,
    signal: AbortSignal,
    onUpdate?: (chunk: unknown) => void,
  ) => Promise<unknown>;
}

export interface OpenClawPluginToolContext {
  agentId?: string;
  sessionKey?: string;
  sandboxed?: boolean;
  config?: OpenClawConfig;
  runtimeConfig?: OpenClawConfig;
  getRuntimeConfig?: () => OpenClawConfig | undefined;
}

export interface RegisterToolOptions {
  names: string[];
  optional?: boolean;
}

export interface RegisterCliDescriptor {
  name: string;
  description: string;
  hasSubcommands?: boolean;
}

export interface RegisterCliOptions {
  descriptors: RegisterCliDescriptor[];
  parentPath?: string[];
}

// Chat slash-command registration — mirrors the surface bundled plugins
// use (memory-core's /dreaming). Verified against OpenClaw 2026.6.11.
export interface ChatCommandContext {
  /** Raw argument string after the command name (when acceptsArgs). */
  args?: string;
  /** Gateway client scopes, e.g. for operator.admin checks. */
  gatewayClientScopes?: string[];
  [k: string]: unknown;
}

export interface ChatCommandReply {
  text: string;
}

export interface RegisterChatCommandOptions {
  name: string;
  description?: string;
  acceptsArgs?: boolean;
  handler: (ctx: ChatCommandContext) => Promise<ChatCommandReply | void> | ChatCommandReply | void;
}

// Hook payload shapes. We only describe the ones we actually consume.
export interface AgentEndHookCtx {
  sessionId?: string | null;
  threadId?: string | null;
  userId?: string | null;
  // The full conversation slice for this turn. Field names follow
  // serenichron-mem0 + ClawMem common patterns; the real SDK may
  // differ on details, so we treat unknown extra fields as opaque.
  messages?: Array<{
    role: string;
    content: string;
    toolCalls?: unknown;
    [k: string]: unknown;
  }>;
  [k: string]: unknown;
}

export interface OpenClawPluginApi {
  // Identity
  readonly id: string;
  readonly name: string;
  readonly pluginConfig: Record<string, unknown>;

  // Logging
  readonly logger?: {
    debug: (...args: unknown[]) => void;
    info: (...args: unknown[]) => void;
    warn: (...args: unknown[]) => void;
    error: (...args: unknown[]) => void;
  };

  // Capability registration
  registerMemoryCapability(opts: RegisterMemoryCapabilityOptions): void;
  registerTool(
    factory: (ctx: OpenClawPluginToolContext) => AnyAgentTool | null,
    opts: RegisterToolOptions,
  ): void;
  registerCli(
    registrar: (args: { program: unknown }) => Promise<void> | void,
    opts: RegisterCliOptions,
  ): void;
  /**
   * Chat slash-command registration. Optional: hosts predating the
   * surface don't expose it — callers must feature-test with `typeof`.
   */
  registerCommand?(opts: RegisterChatCommandOptions): void;

  // Lifecycle hooks
  on(eventName: string, handler: (ctx: unknown) => unknown | Promise<unknown>): void;
}

export interface PluginEntryDefinition {
  id: string;
  name: string;
  description: string;
  kind?: string;
  register: (api: OpenClawPluginApi) => void;
}

// Entry-point factory — mirrors `openclaw/plugin-sdk/plugin-entry`.
//
// In a real install this comes from the SDK package. For typecheck
// inside this repo we expose it as a typed identity function so
// `export default definePluginEntry({ ... })` works without runtime
// dependency on the full SDK build.
export function definePluginEntry(def: PluginEntryDefinition): PluginEntryDefinition {
  return def;
}
