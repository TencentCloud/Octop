import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { BridgeClient } from "./bridge.js";
import pluginEntry from "./index.js";
import { attachAgentEndHook, flattenMessageContent } from "./index.js";
import type { OpenClawPluginApi, RegisterMemoryCapabilityOptions } from "./sdk-shim.js";

describe("flattenMessageContent", () => {
  it("passes plain strings through", () => {
    assert.equal(flattenMessageContent("你好，记住我用pnpm"), "你好，记住我用pnpm");
  });

  it("returns null for empty string", () => {
    assert.equal(flattenMessageContent(""), null);
  });

  it("extracts text blocks from block arrays", () => {
    const blocks = [
      { type: "text", text: "用户决定改用裸机部署" },
      { type: "tool_use", id: "t1", name: "bash", input: {} },
      { type: "text", text: "原因是性能问题" },
    ];
    assert.equal(flattenMessageContent(blocks), "用户决定改用裸机部署\n原因是性能问题");
  });

  it("accepts string items inside arrays", () => {
    assert.equal(flattenMessageContent(["part one", "part two"]), "part one\npart two");
  });

  it("returns null when the array has no text", () => {
    const blocks = [{ type: "image", source: {} }, { type: "tool_use" }];
    assert.equal(flattenMessageContent(blocks), null);
  });

  it("returns null for non-string non-array content", () => {
    assert.equal(flattenMessageContent({ unexpected: true }), null);
    assert.equal(flattenMessageContent(undefined), null);
    assert.equal(flattenMessageContent(null), null);
  });
});

// ---------------------------------------------------------------------------
// attachAgentEndHook — capture + extraction trigger wiring
// ---------------------------------------------------------------------------

type Handler = (ctx: unknown) => unknown | Promise<unknown>;

function makeFakeApi(pluginConfig: Record<string, unknown>): {
  api: OpenClawPluginApi;
  handlers: Map<string, Handler>;
  warnings: unknown[][];
} {
  const handlers = new Map<string, Handler>();
  const warnings: unknown[][] = [];
  const api = {
    id: "octopmemory",
    name: "OctopMemory",
    pluginConfig,
    logger: {
      debug: () => undefined,
      info: () => undefined,
      warn: (...args: unknown[]) => warnings.push(args),
    },
    on: (eventName: string, handler: Handler) => {
      handlers.set(eventName, handler);
    },
  } as unknown as OpenClawPluginApi;
  return { api, handlers, warnings };
}

function makeFakeBridge(failOn?: string): {
  bridge: BridgeClient;
  calls: Array<{ method: string; params: Record<string, unknown> }>;
} {
  const calls: Array<{ method: string; params: Record<string, unknown> }> = [];
  const bridge = {
    call: async (method: string, params: Record<string, unknown>) => {
      calls.push({ method, params });
      if (method === failOn) throw new Error(`${method} failed`);
      return {};
    },
  } as unknown as BridgeClient;
  return { bridge, calls };
}

const AGENT_END_CTX = {
  sessionId: "sess-42",
  threadId: "thread-1",
  messages: [
    { role: "user", content: "记住：部署用裸机，不用容器" },
    { role: "assistant", content: "好的，已记录" },
  ],
};

describe("attachAgentEndHook", () => {
  it("captures then triggers extract when llm endpoint is configured", async () => {
    const { api, handlers } = makeFakeApi({
      llm: { endpoint: "https://api.example.com/v1", model: "small" },
    });
    const { bridge, calls } = makeFakeBridge();
    attachAgentEndHook(api, async () => bridge);

    await handlers.get("agent_end")?.(AGENT_END_CTX);

    assert.deepEqual(
      calls.map((c) => c.method),
      ["capture", "extract"],
    );
    assert.equal(calls[1].params.session_id, "sess-42");
  });

  it("does not trigger extract without llm endpoint", async () => {
    const { api, handlers } = makeFakeApi({});
    const { bridge, calls } = makeFakeBridge();
    attachAgentEndHook(api, async () => bridge);

    await handlers.get("agent_end")?.(AGENT_END_CTX);

    assert.deepEqual(
      calls.map((c) => c.method),
      ["capture"],
    );
  });

  it("respects capture.extract_on_agent_end=false", async () => {
    const { api, handlers } = makeFakeApi({
      llm: { endpoint: "https://api.example.com/v1", model: "small" },
      capture: { extract_on_agent_end: false },
    });
    const { bridge, calls } = makeFakeBridge();
    attachAgentEndHook(api, async () => bridge);

    await handlers.get("agent_end")?.(AGENT_END_CTX);

    assert.deepEqual(
      calls.map((c) => c.method),
      ["capture"],
    );
  });

  it("skips extract when sessionId is missing", async () => {
    const { api, handlers } = makeFakeApi({
      llm: { endpoint: "https://api.example.com/v1", model: "small" },
    });
    const { bridge, calls } = makeFakeBridge();
    attachAgentEndHook(api, async () => bridge);

    await handlers.get("agent_end")?.({ ...AGENT_END_CTX, sessionId: undefined });

    assert.deepEqual(
      calls.map((c) => c.method),
      ["capture"],
    );
  });

  it("does not extract when capture fails", async () => {
    const { api, handlers, warnings } = makeFakeApi({
      llm: { endpoint: "https://api.example.com/v1", model: "small" },
    });
    const { bridge, calls } = makeFakeBridge("capture");
    attachAgentEndHook(api, async () => bridge);

    await handlers.get("agent_end")?.(AGENT_END_CTX);

    assert.deepEqual(
      calls.map((c) => c.method),
      ["capture"],
    );
    assert.equal(warnings.length, 1);
  });

  it("extraction failure only warns and does not throw", async () => {
    const { api, handlers, warnings } = makeFakeApi({
      llm: { endpoint: "https://api.example.com/v1", model: "small" },
    });
    const { bridge, calls } = makeFakeBridge("extract");
    attachAgentEndHook(api, async () => bridge);

    await handlers.get("agent_end")?.(AGENT_END_CTX);

    assert.deepEqual(
      calls.map((c) => c.method),
      ["capture", "extract"],
    );
    assert.equal(warnings.length, 1);
  });
});

describe("plugin registration", () => {
  it("registers a hybrid recall prefetcher on the memory capability", () => {
    let capability: RegisterMemoryCapabilityOptions | null = null;
    const api = {
      id: "octopmemory",
      name: "OctopMemory",
      pluginConfig: { recall: { mode: "hybrid" } },
      logger: {
        debug: () => undefined,
        info: () => undefined,
        warn: () => undefined,
        error: () => undefined,
      },
      registerMemoryCapability: (opts: RegisterMemoryCapabilityOptions) => {
        capability = opts;
      },
      registerTool: () => undefined,
      registerCli: () => undefined,
      on: () => undefined,
    } as unknown as OpenClawPluginApi;

    pluginEntry.register(api);

    assert.equal(typeof capability?.promptBuilder, "function");
    assert.equal(typeof capability?.recallPrefetcher, "function");
  });
});
