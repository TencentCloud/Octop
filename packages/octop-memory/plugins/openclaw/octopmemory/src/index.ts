// octopmemory — OpenClaw native memory plugin entry.
//
// kind: "memory" — occupies `plugins.slots.memory` exclusively (D3
// Replace mode of the host memory design, locked 2026-06-04).
//
// Architecture:
//   ┌─────────────────────────────────────────────────────────────┐
//   │ OpenClaw host                                               │
//   │  ├── promptBuilder ─────► sync prompt section               │
//   │  ├── flushPlanResolver ─► static (flush-plan.ts, sync)      │
//   │  ├── memory_search tool ─► Python bridge (search recall)    │
//   │  ├── memory_get tool ────► Python bridge (path projection)  │
//   │  └── agent_end hook ────► Python bridge (D52-C capture)     │
//   └─────────────────────────────────────────────────────────────┘
//                                  │ stdin/stdout JSON-RPC
//                                  ▼
//                       octopmemory-bridge (Python)
//                                  │
//                                  ▼
//                       octop-memory SQLite store
//
// The bridge subprocess starts lazily on the first tool/hook call so
// plugin registration does not block on Python. The optional host_files
// watcher is enabled by configuration and runs inside the bridge process.

import { homedir } from "node:os";

import { makeHybridRecallPrefetcher } from "./auto-recall.js";
import { BridgeClient } from "./bridge.js";
import { registerChatCommand } from "./chat-command.js";
import { type OctopMemoryPluginConfig, resolveEffectiveConfig } from "./config.js";
import { makeFlushPlanResolver } from "./flush-plan.js";
import { makePromptSectionBuilder } from "./prompt-section.js";
import {
  type AnyAgentTool,
  type OpenClawPluginApi,
  type OpenClawPluginToolContext,
  type ToolJsonSchema,
  definePluginEntry,
} from "./sdk-shim.js";

// ---------------------------------------------------------------------------
// Tool schemas — verbatim copies of memory-core's MemorySearchSchema /
// MemoryGetSchema (extensions/memory-core/index.ts) so any host that
// already supports memory-core's contract keeps working with us.
// ---------------------------------------------------------------------------

const MEMORY_SEARCH_SCHEMA: ToolJsonSchema = {
  type: "object",
  properties: {
    query: { type: "string" },
    maxResults: { type: "integer", minimum: 1 },
    minScore: { type: "number" },
    corpus: { type: "string", enum: ["memory", "wiki", "all", "sessions"] },
  },
  required: ["query"],
  additionalProperties: false,
};

const MEMORY_GET_SCHEMA: ToolJsonSchema = {
  type: "object",
  properties: {
    path: { type: "string" },
    from: { type: "integer", minimum: 1 },
    lines: { type: "integer", minimum: 1 },
    corpus: { type: "string", enum: ["memory", "wiki", "all"] },
  },
  required: ["path"],
  additionalProperties: false,
};

// ---------------------------------------------------------------------------
// Plugin config helpers
// ---------------------------------------------------------------------------

function readPluginCfg(api: OpenClawPluginApi): OctopMemoryPluginConfig {
  return (api.pluginConfig ?? {}) as OctopMemoryPluginConfig;
}

function namespaceFor(api: OpenClawPluginApi): string {
  const cfg = resolveEffectiveConfig(readPluginCfg(api));
  if (cfg.namespace) return cfg.namespace;
  // Fallback: when the host doesn't supply a namespace, derive it
  // from the plugin id. The OpenClaw shell can override via config
  // when it has a stable user identity.
  return `openclaw__${api.id ?? "default"}`;
}

function defaultOpenClawWorkspace(): string {
  const profile = process.env.OPENCLAW_PROFILE?.trim();
  if (profile && profile !== "default") {
    return `${homedir()}/.openclaw/workspace-${profile}`;
  }
  return `${homedir()}/.openclaw/workspace`;
}

// ---------------------------------------------------------------------------
// Lazy bridge — one per plugin instance, started on first need.
// ---------------------------------------------------------------------------

function makeBridgeFactory(api: OpenClawPluginApi): () => Promise<BridgeClient> {
  let cached: BridgeClient | null = null;
  let pending: Promise<BridgeClient> | null = null;

  return async () => {
    if (cached) {
      await cached.start();
      return cached;
    }
    if (pending) return pending;

    const cfg = resolveEffectiveConfig(readPluginCfg(api));
    const client = new BridgeClient({
      namespace: namespaceFor(api),
      backend: cfg.backend,
      command: cfg.bridge.command,
      python: cfg.bridge.python,
      logLevel: cfg.bridge.log_level,
      spawnTimeoutMs: cfg.bridge.spawn_timeout_ms,
      dbPath: cfg.db_path,
      hostFilesRoot: cfg.capture.host_files_watcher ? (cfg.host_files_root ?? defaultOpenClawWorkspace()) : undefined,
      hostFilesAllow: cfg.host_files_allow,
      config: {
        profile: cfg.profile,
        mode: cfg.mode,
        recall: cfg.recall,
        capture: cfg.capture,
        privacy: cfg.privacy,
        llm: cfg.llm,
        extraction: cfg.extraction,
      },
      // Single-argument form: some hosts treat logger.info printf-style and
      // drop extra args, which swallowed bridge tracebacks entirely.
      onStderr: (line) => api.logger?.info?.(`[octopmemory-bridge] ${line}`),
    });
    pending = client.start().then(() => {
      cached = client;
      return client;
    });
    try {
      return await pending;
    } finally {
      pending = null;
    }
  };
}

// ---------------------------------------------------------------------------
// Tool factories
// ---------------------------------------------------------------------------

function makeMemorySearchTool(getBridge: () => Promise<BridgeClient>, threadId?: string): AnyAgentTool {
  return {
    label: "Memory Search",
    name: "memory_search",
    description:
      "Search octopmemory's structured atoms, manual tree notes, raw events, and indexed host memory files. " +
      "Returns ranked snippets with source paths; atom, raw, and indexed host-file paths can be opened via memory_get.",
    parameters: MEMORY_SEARCH_SCHEMA,
    execute: async (_toolCallId, params) => {
      const bridge = await getBridge();
      // thread_id rides along so the Python side can resolve
      // co-references against the thread's active-entity stack and
      // use the per-thread recall cache. Not part of the agent-facing
      // schema — injected from the tool-registration context.
      return await bridge.call("memory_search", {
        ...(params as Record<string, unknown>),
        thread_id: threadId ?? null,
      });
    },
  };
}

function makeMemoryGetTool(getBridge: () => Promise<BridgeClient>): AnyAgentTool {
  return {
    label: "Memory Get",
    name: "memory_get",
    description:
      "Read a specific memory document by path. Paths are virtual (atom/<id>.md, " +
      "page/<entity>.md, raw/<date>/<id>.md) or real host files (memory/<date>.md, " +
      "MEMORY.md). Optional `from` / `lines` slice the document; the response " +
      "includes truncation + continuation hints.",
    parameters: MEMORY_GET_SCHEMA,
    execute: async (_toolCallId, params) => {
      const bridge = await getBridge();
      return await bridge.call("memory_get", params as Record<string, unknown>);
    },
  };
}

// ---------------------------------------------------------------------------
// agent_end auto-capture (D52-C path B; default on) + light extraction (D26)
// ---------------------------------------------------------------------------

export function attachAgentEndHook(api: OpenClawPluginApi, getBridge: () => Promise<BridgeClient>): void {
  const cfg = resolveEffectiveConfig(readPluginCfg(api));
  if (cfg.capture.agent_end_hook === false) {
    api.logger?.info?.("[octopmemory] agent_end auto-capture disabled by config");
    return;
  }
  // Extraction needs an LLM on the Python side; without `llm.endpoint`
  // the bridge would return failure_reason every turn, so skip the call
  // entirely.
  const extractEnabled = cfg.capture.extract_on_agent_end !== false && Boolean(cfg.llm?.endpoint);
  api.on("agent_end", async (rawCtx) => {
    const ctx = (rawCtx ?? {}) as Record<string, unknown>;
    try {
      const messages = Array.isArray(ctx.messages) ? (ctx.messages as Array<Record<string, unknown>>) : [];
      if (messages.length === 0) return;

      const events = messages
        .map((m) => {
          const role = typeof m.role === "string" ? m.role : "user";
          const content = flattenMessageContent(m.content);
          if (!content) return null;
          return {
            event_type: roleToEventType(role),
            content,
            payload: { role },
          };
        })
        .filter((x): x is { event_type: string; content: string; payload: { role: string } } => x !== null);

      if (events.length === 0) return;

      const bridge = await getBridge();
      await bridge.call("capture", {
        session_id: ctx.sessionId ?? null,
        thread_id: ctx.threadId ?? null,
        user: ctx.userId ?? null,
        host: "openclaw",
        events,
      });
    } catch (err) {
      // Capture failure must never block the agent's reply.
      api.logger?.warn?.("[octopmemory] agent_end capture failed:", err);
      return;
    }

    // D26 light extraction: candidates land within the same turn so the
    // user's "remember this" instruction is recallable next turn. Failures only log —
    // the bridge keeps the events for retry on the next agent_end.
    const sessionId = typeof ctx.sessionId === "string" && ctx.sessionId ? ctx.sessionId : null;
    if (!extractEnabled || !sessionId) return;
    try {
      const bridge = await getBridge();
      await bridge.call("extract", { session_id: sessionId });
    } catch (err) {
      api.logger?.warn?.("[octopmemory] agent_end extraction failed:", err);
    }
  });
}

/**
 * Normalize a message `content` field to plain text.
 *
 * OpenClaw / Claude-style transcripts carry either a plain string or an
 * array of content blocks (`{ type: "text", text }`, tool blocks, image
 * blocks, ...). Only text is durable memory material — other block
 * types are skipped rather than dropping the whole message.
 */
export function flattenMessageContent(content: unknown): string | null {
  if (typeof content === "string") {
    return content || null;
  }
  if (!Array.isArray(content)) return null;
  const parts: string[] = [];
  for (const block of content) {
    if (typeof block === "string") {
      if (block) parts.push(block);
      continue;
    }
    if (block && typeof block === "object") {
      const rec = block as Record<string, unknown>;
      if (typeof rec.text === "string" && rec.text) {
        parts.push(rec.text);
      }
    }
  }
  const joined = parts.join("\n").trim();
  return joined || null;
}

function roleToEventType(role: string): string {
  switch (role) {
    case "user":
      return "user_message";
    case "assistant":
      return "assistant_message";
    case "tool":
      return "tool_result";
    default:
      return "user_message";
  }
}

// ---------------------------------------------------------------------------
// CLI registration — native commands + admin Python fallback.
// ---------------------------------------------------------------------------

function registerCli(api: OpenClawPluginApi, getBridge: () => Promise<BridgeClient>): void {
  api.registerCli(
    async ({ program: _program }) => {
      // Implementation lives in cli.ts and is loaded lazily so plugin
      // startup doesn't import commander unless the CLI is actually used.
      const { registerOctopmemoryCli } = await import("./cli.js");
      registerOctopmemoryCli(_program, api, getBridge);
    },
    {
      descriptors: [
        {
          name: "octopmemory",
          description: "Inspect, search, show, reindex, and maintain OctopMemory.",
          hasSubcommands: true,
        },
      ],
    },
  );
}

// ---------------------------------------------------------------------------
// Plugin entry
// ---------------------------------------------------------------------------

export default definePluginEntry({
  id: "octopmemory",
  name: "OctopMemory",
  description: "Pluggable memory for OpenClaw (atom + tree + raw recall, FTS5-backed).",
  kind: "memory",
  register(api: OpenClawPluginApi) {
    const cfg = resolveEffectiveConfig(readPluginCfg(api));
    const getBridge = makeBridgeFactory(api);

    // Core capability — the slot-occupying registration.
    //
    // Why all four runtime methods intentionally return null/no-op:
    //
    // OpenClaw's bundled `memory-core` plugin owns its own
    // SQLite-on-disk store and exposes the runtime so the host can
    // *manage* that store (open/close indices, resolve backend
    // config). Our model is the inverse: we delegate everything to
    // the Python bridge subprocess, so the host has nothing to
    // manage on our behalf. We MUST still provide the four methods
    // (host calls them unconditionally) but they intentionally
    // return null / no-op — the host's "no backend to manage" path
    // is what we want.
    api.registerMemoryCapability({
      promptBuilder: makePromptSectionBuilder({
        mode: cfg.recall?.mode,
        maxPromptChars: cfg.recall?.max_prompt_chars,
      }),
      recallPrefetcher: makeHybridRecallPrefetcher(cfg, getBridge, api.logger),
      flushPlanResolver: makeFlushPlanResolver({
        pluginOverrides: cfg.compaction,
      }),
      runtime: {
        // No file-shaped backend the host can introspect — point at
        // the bridge instead.
        resolveMemoryBackendConfig: () => null,
        // Host won't run a search manager — `memory_search` tool is
        // our path. Returning null tells the host "nothing to wire".
        getMemorySearchManager: async () => null,
        closeAllMemorySearchManagers: async () => undefined,
        closeMemorySearchManager: async () => undefined,
      },
    });

    // Tools — the agent-facing surface.
    api.registerTool((ctx: OpenClawPluginToolContext) => makeMemorySearchTool(getBridge, ctx?.sessionKey), {
      names: ["memory_search"],
    });
    api.registerTool((_ctx: OpenClawPluginToolContext) => makeMemoryGetTool(getBridge), {
      names: ["memory_get"],
    });

    // Auto-capture (D52-C path B).
    attachAgentEndHook(api, getBridge);

    // CLI bridge.
    registerCli(api, getBridge);

    // Chat slash command (/octopmemory ...). The manifest commandAlias
    // only covers CLI routing; chat dispatch needs this runtime surface.
    registerChatCommand(api, getBridge);

    api.logger?.info?.(
      `[octopmemory] registered (profile=${cfg.profile}, mode=${cfg.mode}, recall=${cfg.recall.mode}, ` +
        `capture.agent_end=${cfg.capture.agent_end_hook}, ` +
        `capture.host_files=${cfg.capture.host_files_watcher})`,
    );
  },
});
